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
    // Builds the domain in place in multi_mesh: u, v and the ghosts are
    // external (no copy), so the buffers must stay valid through
    // publish() and execute().
    template <typename T>
    void BuildRepartitionedBlueprint(
        const RepartitionInfo &read_info,
        const std::vector<T> &buf_u,
        const std::vector<T> *buf_v,
        std::vector<std::int32_t> &cell_ghosts,
        size_t step,
        const BackendOptions &opts,
        conduit::Node &multi_mesh)
    {
        multi_mesh.reset();
        multi_mesh.set(conduit::DataType::list());
        conduit::Node &domain = multi_mesh.append();
        domain["state/cycle"] = static_cast<long long>(step);
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

        // Ghosts, mirroring the Catalyst backend: ReadRepartition adds the
        // neighbour's first plane of points on each shared_high axis, so
        // pieces share points but every cell belongs to exactly one piece.
        // Ascent's ghost field (ascent_ghosts) is element associated only:
        // the shared points cannot be flagged, and no cell is a ghost, so
        // every cell is 0 (owned). This is the convention the simulation's
        // Ascent backend publishes. A point-based query in Ascent still
        // counts the shared planes twice (analysis/README.md). The buffer
        // is reused across steps and only resized, still all zero.
        const size_t cx = nx > 1 ? nx - 1 : 1;
        const size_t cy = ny > 1 ? ny - 1 : 1;
        const size_t cz = nz > 1 ? nz - 1 : 1;
        cell_ghosts.resize(cx * cy * cz, 0);
        domain["fields/ascent_ghosts/association"] = "element";
        domain["fields/ascent_ghosts/topology"] = "mesh";
        domain["fields/ascent_ghosts/values"].set_external(cell_ghosts.data(), cell_ghosts.size());
    }
}

AscentBackend::AscentBackend(const BackendOptions &opts)
    : m_opts(opts),
      m_perf_logger("reader_timers",
                    [&]() { int rank; MPI_Comm_rank(opts.comm, &rank); return rank; }(),
                    [&]() { char hostname[256]; gethostname(hostname, sizeof(hostname)); return std::string(hostname); }(),
                    {"ADIOS_Wait", "ADIOS_Read_U", "ADIOS_Read_V", "ADIOS_EndStep", "Halo_Exchange", "Step_Latency", "Blueprint_Time", "Vis_Time", "total_step",
                     "Read_Setup", "Read_Alloc", "Mesh_Build"},
                    {"minflt_alloc", "minflt_endstep", "minflt_build", "minflt_vis"}),
      m_reader(opts, m_perf_logger)
{
    conduit::Node open_opts;
    open_opts["mpi_comm"] = MPI_Comm_c2f(m_reader.GetComm());
    m_ascent.open(open_opts);
    if (opts.overwrite_last_step)
    {
        std::string error;
        const conduit::Node loaded = gs_ascent::LoadActionsFile(error);
        int rank = 0;
        MPI_Comm_rank(m_reader.GetComm(), &rank);
        if (!error.empty() && rank == 0)
            std::cerr << "analysis-reader: Ascent: " << error << std::endl;
        std::vector<std::string> unsupported;
        gs_ascent::SplitRelayExtracts(loaded, true, m_actions, m_relay_extracts, unsupported);
        // Every rank reads the same files, so every rank stops here alike.
        if (!unsupported.empty())
            throw std::runtime_error("overwrite_last_step: relay parameter " + unsupported.front() +
                                     " is not supported (only path and protocol)");
        // Ascent 0.9.6 replaces the actions passed to execute() with its
        // actions file whenever that file exists, so actions left beside the
        // relay extracts would bring the extracts back, written every step.
        if (!m_relay_extracts.empty() && m_actions.number_of_children() > 0)
            throw std::runtime_error("overwrite_last_step needs an Ascent actions file with relay extracts only: "
                                     "Ascent reloads the file on every execute, extracts included");
    }
}

void AscentBackend::Run()
{
    int rank; MPI_Comm_rank(m_reader.GetComm(), &rank);
    while (m_reader.NextStep())
    {
        m_perf_logger.start("total_step");
        size_t step = m_reader.CurrentStep();
        // The field buffers and the mesh node are members and live across
        // steps: ReadRepartition resizes a buffer only when its size
        // changes, so after the first step no step allocates, zero-fills,
        // page-faults or frees field-sized memory. Fresh buffers each step
        // cost about 1.2 s per step on 2.2 GB fields (sites/shaheen/README.md).
        std::vector<double> &u_buf = m_u_buf;
        std::vector<double> &v_buf = m_v_buf;
        conduit::Node &mesh_blueprint = m_mesh;
        RepartitionInfo read_info;
        m_perf_logger.start("Blueprint_Time");
        m_reader.ReadRepartition(m_reader.GetOptions().u_var, u_buf, read_info);
        m_reader.ReadRepartition(m_reader.GetOptions().v_var, v_buf, read_info);
        // The reads are deferred and complete at EndStep(), into buffers the
        // reader owns: end the step now, then use them, so the simulation
        // goes on while we render (#76, #42).
        double faults = ProcessMinorFaults();
        m_reader.EndStep();
        m_perf_logger.setCounter("minflt_endstep", ProcessMinorFaults() - faults);
        m_perf_logger.setCounter("minflt_alloc", m_reader.TakeAllocFaults());
        m_perf_logger.start("Mesh_Build");
        faults = ProcessMinorFaults();
        BuildRepartitionedBlueprint(read_info, u_buf, &v_buf, m_cell_ghosts, step, m_reader.GetOptions(), mesh_blueprint);
        m_perf_logger.setCounter("minflt_build", ProcessMinorFaults() - faults);
        m_perf_logger.stop("Mesh_Build");
        m_perf_logger.stop("Blueprint_Time");

        m_perf_logger.start("Vis_Time");
        faults = ProcessMinorFaults();
        m_ascent.publish(mesh_blueprint);
        if (!m_opts.overwrite_last_step)
            m_ascent.execute(conduit::Node()); // Ascent runs its actions file
        else
        {
            // No relay extracts: the actions run as they are (Ascent loads its
            // actions file in execute()). With relay extracts there are no
            // other actions (constructor), so Ascent is not executed.
            if (m_relay_extracts.empty())
                m_ascent.execute(conduit::Node());
            for (const auto &rx : m_relay_extracts)
            {
                const std::string error =
                    gs_ascent::SaveMeshAsCycleZero(mesh_blueprint, rx.first, rx.second, m_reader.GetComm());
                if (!error.empty())
                    std::cerr << "analysis-reader: Ascent overwrite save failed: " << error << std::endl;
            }
        }
        m_perf_logger.setCounter("minflt_vis", ProcessMinorFaults() - faults);
        m_perf_logger.stop("Vis_Time");
        m_perf_logger.stop("total_step");
        m_perf_logger.logStep(step);
    }
    // Write the timings now, before teardown can get stuck (#75).
    m_perf_logger.finalize();
    m_ascent.close();
}
