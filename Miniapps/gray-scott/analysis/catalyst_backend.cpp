#include "catalyst_backend.h"
#include <catalyst.hpp>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <filesystem>
#include <iostream>
#include <unistd.h>
#include <numeric>
#include <algorithm>
#include <cmath>
#include <mpi.h>

namespace fs = std::filesystem;

namespace
{
    // Stop the job at once when Catalyst reports an error. ParaView returns
    // an error status from catalyst_execute when the script fails to import
    // or raises in a step (102 for both), then skips that pipeline on every
    // later step. Carrying on logged a near-zero Vis_Time for steps that drew
    // nothing, so a broken script looked like a very fast run. Every reader
    // rank runs the same script, so every rank gets here. MPI_Abort is called
    // here rather than through an exception: unwinding would first destroy
    // the ADIOS2 reader (an SST Close that can wait for its peers) and call
    // catalyst_finalize, neither of which is time-bounded on that path.
    // srun's --kill-on-bad-exit then stops the simulation.
    [[noreturn]] void AbortOnCatalystError(const std::string &what, catalyst_status err, const std::string &hint)
    {
        int rank = 0;
        MPI_Comm_rank(MPI_COMM_WORLD, &rank);
        std::cerr << "[analysis-reader rank " << rank << "] Fatal error: " << what << " (catalyst_status "
                  << static_cast<int>(err) << "): " << hint << std::endl;
        MPI_Abort(MPI_COMM_WORLD, 1);
        std::abort(); // MPI_Abort does not return; this keeps [[noreturn]] honest
    }

    void BuildRepartitionedCatalystMesh(
        conduit_cpp::Node &mesh_node,
        const RepartitionInfo &read_info,
        const std::vector<double> &buf_u,
        const std::vector<double> *buf_v,
        const BackendOptions &opts,
        std::vector<std::uint8_t> &point_ghosts,
        std::array<std::size_t, 6> &ghost_shape)
    {
        mesh_node["type"] = "uniform";
        std::array<double, 3> global_origin = opts.origin.value_or(std::array<double, 3>{0.0, 0.0, 0.0});
        std::array<double, 3> spacing = opts.spacing.value_or(std::array<double, 3>{0.1, 0.1, 0.1});
        std::array<double, 3> local_origin = global_origin;

        // 1. ORIGIN CALCULATION
        for (size_t i = 0; i < read_info.local_start.size(); ++i)
        {
            size_t dim_idx = read_info.local_start.size() - 1 - i;
            size_t start_offset = read_info.local_start[i];

            // PERFECT CUBE: Standard placement without pull-back/squishing logic
            local_origin[dim_idx] += (static_cast<double>(start_offset) * spacing[dim_idx]);
        }

        mesh_node["coordsets/coords/type"].set_string("uniform");
        mesh_node["coordsets/coords/origin/x"].set_float64(local_origin[0]);
        mesh_node["coordsets/coords/origin/y"].set_float64(local_origin[1]);
        mesh_node["coordsets/coords/origin/z"].set_float64(local_origin[2]);
        mesh_node["coordsets/coords/spacing/dx"].set_float64(spacing[0]);
        mesh_node["coordsets/coords/spacing/dy"].set_float64(spacing[1]);
        mesh_node["coordsets/coords/spacing/dz"].set_float64(spacing[2]);

        // 2. DIMENSION ASSIGNMENT
        size_t nx = 1, ny = 1, nz = 1;
        if (read_info.local_dims.size() == 3)
        {
            nx = read_info.local_dims[2];
            ny = read_info.local_dims[1];
            nz = read_info.local_dims[0];
        }

        mesh_node["coordsets/coords/dims/i"].set_int64(static_cast<long long>(nx));
        mesh_node["coordsets/coords/dims/j"].set_int64(static_cast<long long>(ny));
        mesh_node["coordsets/coords/dims/k"].set_int64(static_cast<long long>(nz));

        mesh_node["topologies/mesh/type"].set_string("uniform");
        mesh_node["topologies/mesh/coordset"].set_string("coords");
        mesh_node["fields/u/association"].set_string("vertex");
        mesh_node["fields/u/topology"].set_string("mesh");
        mesh_node["fields/u/values"].set_external(const_cast<double *>(buf_u.data()), buf_u.size());

        if (buf_v && !buf_v->empty())
        {
            mesh_node["fields/v/association"].set_string("vertex");
            mesh_node["fields/v/topology"].set_string("mesh");
            mesh_node["fields/v/values"].set_external(const_cast<double *>(buf_v->data()), buf_v->size());
        }

        // ReadRepartition adds the neighbour's first plane on every axis
        // where this piece is not the last (shared_high), so neighbouring
        // pieces share that plane of points (no cell is duplicated). Flag
        // those points DUPLICATEPOINT (vtkDataSetAttributes) so point-based
        // analysis in a Catalyst script does not count them twice (#42).
        // With slabs only z is shared; with bricks any of the three.
        const bool shared_z = read_info.shared_high.size() == 3 && read_info.shared_high[0];
        const bool shared_y = read_info.shared_high.size() == 3 && read_info.shared_high[1];
        const bool shared_x = read_info.shared_high.size() == 3 && read_info.shared_high[2];
        // The flags depend only on the piece's shape, which is the same every
        // step: fill them when it changes (the first step), not every step.
        // The fill visits every point, 268 million per reader at 64 + 4 nodes.
        const std::array<std::size_t, 6> shape{nx, ny, nz, shared_x, shared_y, shared_z};
        if (point_ghosts.size() != nx * ny * nz || shape != ghost_shape)
        {
            point_ghosts.assign(nx * ny * nz, 0);
            if (shared_x || shared_y || shared_z)
            {
                for (size_t k = 0; k < nz; ++k)
                    for (size_t j = 0; j < ny; ++j)
                        for (size_t i = 0; i < nx; ++i)
                            if ((shared_z && k == nz - 1) || (shared_y && j == ny - 1) || (shared_x && i == nx - 1))
                                point_ghosts[(k * ny + j) * nx + i] = std::uint8_t{1};
            }
            ghost_shape = shape;
        }
        mesh_node["fields/vtkGhostType/association"].set_string("vertex");
        mesh_node["fields/vtkGhostType/topology"].set_string("mesh");
        mesh_node["fields/vtkGhostType/values"].set_external(point_ghosts.data(), point_ghosts.size());
    }
} // end anonymous namespace

CatalystBackend::CatalystBackend(const BackendOptions &opts)
    : m_opts(opts),
      m_perf_logger("reader_timers",
                    [&]() { int rank; MPI_Comm_rank(opts.comm, &rank); return rank; }(),
                    [&]() { char hostname[256]; gethostname(hostname, sizeof(hostname)); return std::string(hostname); }(),
                    {"ADIOS_Wait", "ADIOS_Read_U", "ADIOS_Read_V", "ADIOS_EndStep", "Halo_Exchange", "Blueprint_Time", "Vis_Time", "total_step",
                     "Mesh_Build"}),
      m_reader(opts, m_perf_logger)
{
    conduit_cpp::Node init_params;
    init_params["catalyst/mpi_comm"] = MPI_Comm_c2f(m_reader.GetComm());
    const auto &current_opts = m_reader.GetOptions();
    if (current_opts.output_type == "catalyst_io")
    {
        if (current_opts.catalyst_output_file.empty()) {
            throw std::runtime_error("'catalyst_output_file' must be set in settings for catalyst_io mode.");
        }
        init_params["catalyst/pipelines/0/type"].set("io");
        init_params["catalyst/pipelines/0/filename"].set(current_opts.catalyst_output_file);
        init_params["catalyst/pipelines/0/channel"].set("grid");
    }
    else if (current_opts.output_type == "catalyst_insitu")
    {
        const std::string path_str = current_opts.catalyst_script_path;
        const fs::path script_path(path_str);
        const std::string name = "catalyst/scripts/script_" + script_path.filename().string();
        init_params[name + "/filename"].set_string(path_str);
        init_params[name + "/args"].append().set_string("--channel-name=grid");
    }
    else
    {
        throw std::runtime_error("Unknown output type for Catalyst backend: " + current_opts.output_type);
    }
    init_params["catalyst_load/implementation"] = "paraview";
    if (!current_opts.catalyst_lib_path.empty())
        init_params["catalyst_load/search_paths/paraview"] = current_opts.catalyst_lib_path;
    const catalyst_status err = catalyst_initialize(conduit_cpp::c_node(&init_params));
    if (err != catalyst_status_ok)
        AbortOnCatalystError("catalyst_initialize failed", err,
                             "check catalyst_lib_path and the Catalyst script");
}

CatalystBackend::~CatalystBackend()
{
    conduit_cpp::Node final_params;
    catalyst_finalize(conduit_cpp::c_node(&final_params));
}

void CatalystBackend::Run()
{
    while (m_reader.NextStep())
    {
        m_perf_logger.start("total_step");
        size_t step = m_reader.CurrentStep();
        const auto &current_opts = m_reader.GetOptions();

        conduit_cpp::Node exec_params;
        exec_params["catalyst/state/timestep"].set_int64(static_cast<long long>(step));
        exec_params["catalyst/state/time"].set_float64(static_cast<double>(step));
        exec_params["catalyst/channels/grid/type"].set_string("mesh");

        // Members, kept across steps (catalyst_backend.h).
        std::vector<double> &u_buf = m_u_buf;
        std::vector<double> &v_buf = m_v_buf;
        RepartitionInfo read_info;

        m_perf_logger.start("Blueprint_Time");
        m_reader.ReadRepartition(current_opts.u_var, u_buf, read_info);
        m_reader.ReadRepartition(current_opts.v_var, v_buf, read_info);
        // The reads are deferred and complete at EndStep(), into buffers the
        // reader owns: end the step now, then use them, so the simulation
        // goes on while we render (#76, #42).
        m_reader.EndStep();

        m_perf_logger.start("Mesh_Build");
        auto data_node = exec_params["catalyst/channels/grid/data"];
        BuildRepartitionedCatalystMesh(data_node, read_info, u_buf, &v_buf, current_opts, m_point_ghosts,
                                       m_ghost_shape);
        m_perf_logger.stop("Mesh_Build");
        m_perf_logger.stop("Blueprint_Time");

        m_perf_logger.start("Vis_Time");
        const catalyst_status err = catalyst_execute(conduit_cpp::c_node(&exec_params));
        m_perf_logger.stop("Vis_Time");
        // Stop the run on a failed execute (AbortOnCatalystError).
        if (err != catalyst_status_ok)
            AbortOnCatalystError("catalyst_execute failed at step " + std::to_string(step), err,
                                 "the Catalyst script or pipeline failed; see ParaView's error and any "
                                 "Python traceback above");
        m_perf_logger.stop("total_step");
        m_perf_logger.logStep(step);
    }
    // Write the timings now, before teardown can get stuck (#75).
    m_perf_logger.finalize();
}
