#include "ascent_backend.h"
#include <conduit.hpp>
#include <conduit_blueprint.hpp>
#include <iostream>
#include <unistd.h>
#include <numeric>
#include <algorithm>
#include <cmath>

namespace
{
    template <typename T>
    conduit::Node BuildRepartitionedBlueprint(
        const RepartitionInfo &read_info,
        const std::vector<T> &buf_u,
        const std::vector<T> *buf_v,
        size_t step,
        const BackendOptions &opts)
    {
        conduit::Node domain;
        domain["state/cycle"] = static_cast<long long>(step);

	int rank;
        MPI_Comm_rank(opts.comm, &rank);
        domain["state/domain_id"] = rank;

        std::array<double, 3> global_origin = opts.origin.value_or(std::array<double, 3>{0.0, 0.0, 0.0});
        std::array<double, 3> spacing = opts.spacing.value_or(std::array<double, 3>{0.1, 0.1, 0.1});
        std::array<double, 3> local_origin = global_origin;

        // 1. ORIGIN CALCULATION
        for (size_t i = 0; i < read_info.local_start.size(); ++i)
        {
            size_t dim_idx = read_info.local_start.size() - 1 - i;
            size_t start_offset = read_info.local_start[i];
            // PERFECT CUBE: Standard placement
            local_origin[dim_idx] += (static_cast<double>(start_offset) * spacing[dim_idx]);
        }

        conduit::Node &c = domain["coordsets/coords"];
        c["type"] = "uniform";
        c["origin/x"] = local_origin[0]; c["origin/y"] = local_origin[1]; c["origin/z"] = local_origin[2];
        c["spacing/dx"] = spacing[0]; c["spacing/dy"] = spacing[1]; c["spacing/dz"] = spacing[2];

	// Tell Blueprint the global index offsets for stitching
        c["origin_logical/i"] = (long long)(read_info.local_start[2]);
        c["origin_logical/j"] = (long long)(read_info.local_start[1]);
        c["origin_logical/k"] = (long long)(read_info.local_start[0]);

        // 2. DIMENSION ASSIGNMENT
        size_t nx = 1, ny = 1, nz = 1;
        if (read_info.local_dims.size() == 3)
        {
            nx = read_info.local_dims[2];
            ny = read_info.local_dims[1];
            nz = read_info.local_dims[0];
        }
        c["dims/i"] = (long long)nx; c["dims/j"] = (long long)ny; c["dims/k"] = (long long)nz;

        domain["topologies/mesh/type"] = "uniform";
        domain["topologies/mesh/coordset"] = "coords";
        domain["fields/u/association"] = "vertex";
        domain["fields/u/topology"] = "mesh";
        domain["fields/u/values"].set_external(const_cast<T *>(buf_u.data()), buf_u.size());

        if (buf_v && !buf_v->empty())
        {
            domain["fields/v/association"] = "vertex";
            domain["fields/v/topology"] = "mesh";
            domain["fields/v/values"].set_external(const_cast<T *>(buf_v->data()), buf_v->size());
        }

        conduit::Node multi_mesh(conduit::DataType::list());
        multi_mesh.append().set(domain);
        return multi_mesh;
    }
}

AscentBackend::AscentBackend(const BackendOptions &opts)
    : m_opts(opts),
      m_perf_logger("reader_timers",
                    [&]() { int rank; MPI_Comm_rank(opts.comm, &rank); return rank; }(),
                    [&]() { char hostname[256]; gethostname(hostname, sizeof(hostname)); return std::string(hostname); }(),
                    {"ADIOS_Wait", "ADIOS_Read_U", "ADIOS_Read_V", "Blueprint_Time", "Vis_Time", "total_step"}),
      m_reader(opts, m_perf_logger)
{
    conduit::Node open_opts;
    open_opts["mpi_comm"] = MPI_Comm_c2f(m_reader.GetComm());
    m_ascent.open(open_opts);
}

void AscentBackend::Run()
{
    int rank; MPI_Comm_rank(m_reader.GetComm(), &rank);
    while (m_reader.BeginStep() == adios2::StepStatus::OK)
    {
        m_perf_logger.start("total_step");
        size_t step = m_reader.CurrentStep();
        conduit::Node mesh_blueprint; std::vector<double> u_buf, v_buf; RepartitionInfo read_info;
        m_perf_logger.start("Blueprint_Time");
        m_reader.ReadRepartition(m_reader.GetOptions().u_var, u_buf, read_info);
        m_reader.ReadRepartition(m_reader.GetOptions().v_var, v_buf, read_info);

	//End the step, force the data to be sent
	m_reader.EndStep();

        mesh_blueprint = BuildRepartitionedBlueprint(read_info, u_buf, &v_buf, step, m_reader.GetOptions());
        m_perf_logger.stop("Blueprint_Time");

        m_perf_logger.start("Vis_Time");
        m_ascent.publish(mesh_blueprint);
        m_ascent.execute(conduit::Node());
        m_perf_logger.stop("Vis_Time");     
        m_perf_logger.stop("total_step");
        m_perf_logger.logStep(step);
    }
    m_ascent.close();
}
