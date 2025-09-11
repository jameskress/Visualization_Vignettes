#include "ascent_backend.h"
#include <conduit.hpp>
#include <conduit_blueprint.hpp>
#include <iostream>
#include <unistd.h>
#include <numeric>
#include <algorithm>

namespace
{
    // Helper for building a single-domain mesh from repartitioned data
    template <typename T>
    conduit::Node BuildRepartitionedBlueprint(
        const RepartitionInfo &read_info,
        const std::vector<T> &buf_u,
        const std::vector<T> *buf_v,
        size_t step,
        const BackendOptions &opts)
    {
        conduit::Node domain;
        domain["state/step"] = static_cast<long long>(step);

        std::array<double, 3> global_origin = opts.origin.value_or(std::array<double, 3>{0.0, 0.0, 0.0});
        std::array<double, 3> spacing = opts.spacing.value_or(std::array<double, 3>{0.1, 0.1, 0.1});

        std::array<double, 3> local_origin = global_origin;
        if (read_info.local_start.size() >= 3)
        {
            for (size_t i = 0; i < read_info.local_start.size(); ++i)
            {
                size_t dim_idx = read_info.local_start.size() - 1 - i;
                local_origin[dim_idx] += read_info.local_start[i] * spacing[dim_idx];
            }
        }

        conduit::Node &c = domain["coordsets/coords"];
        c["type"] = "uniform";
        c["origin/x"] = local_origin[0];
        c["origin/y"] = local_origin[1];
        c["origin/z"] = local_origin[2];
        c["spacing/dx"] = spacing[0];
        c["spacing/dy"] = spacing[1];
        c["spacing/dz"] = spacing[2];

        size_t nx = 1, ny = 1, nz = 1;
        if (read_info.local_dims.size() == 3)
        {
            nx = read_info.local_dims[2];
            ny = read_info.local_dims[1];
            nz = read_info.local_dims[0];
        }
        else if (read_info.local_dims.size() == 2)
        {
            nx = read_info.local_dims[1];
            ny = read_info.local_dims[0];
        }
        else if (read_info.local_dims.size() == 1)
        {
            nx = read_info.local_dims[0];
        }
        c["dims/i"] = (long long)nx;
        c["dims/j"] = (long long)ny;
        c["dims/k"] = (long long)nz;

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

        // For Ascent, even a single domain should be in a list
        conduit::Node multi_mesh(conduit::DataType::list());
        multi_mesh.append().set(domain);
        return multi_mesh;
    }

    // Helper for building a multi-block mesh from preserved data
    template <typename T>
    conduit::Node BuildMultiBlockBlueprint(
        const std::vector<BlockData<T>> &blocks_u,
        const std::vector<BlockData<T>> *blocks_v,
        size_t step,
        const BackendOptions &opts)
    {
        conduit::Node multi_mesh(conduit::DataType::list());
        std::array<double, 3> global_origin = opts.origin.value_or(std::array<double, 3>{0.0, 0.0, 0.0});
        std::array<double, 3> spacing = opts.spacing.value_or(std::array<double, 3>{0.1, 0.1, 0.1});

        for (size_t i = 0; i < blocks_u.size(); ++i)
        {
            const auto &block = blocks_u[i];
            conduit::Node &domain = multi_mesh.append();
            domain["state/step"] = static_cast<long long>(step);

            std::array<double, 3> local_origin = global_origin;
            if (block.start.size() >= 3)
            {
                for (size_t d = 0; d < block.start.size(); ++d)
                {
                    size_t dim_idx = block.start.size() - 1 - d;
                    size_t start_offset = block.start[d];
                    size_t block_dim = block.dims[d];
                    double physical_origin = start_offset * spacing[dim_idx];
                    if (block_dim > 0)
                    {
                        double correction = (start_offset / block_dim) * spacing[dim_idx];
                        local_origin[dim_idx] += (physical_origin - correction);
                    }
                    else
                    {
                        local_origin[dim_idx] += physical_origin;
                    }
                }
            }

            conduit::Node &c = domain["coordsets/coords"];
            c["type"] = "uniform";
            c["origin/x"] = local_origin[0];
            c["origin/y"] = local_origin[1];
            c["origin/z"] = local_origin[2];
            c["spacing/dx"] = spacing[0];
            c["spacing/dy"] = spacing[1];
            c["spacing/dz"] = spacing[2];

            size_t nx = 1, ny = 1, nz = 1;
            if (block.dims.size() == 3)
            {
                nx = block.dims[2];
                ny = block.dims[1];
                nz = block.dims[0];
            }
            else if (block.dims.size() == 2)
            {
                nx = block.dims[1];
                ny = block.dims[0];
            }
            else if (block.dims.size() == 1)
            {
                nx = block.dims[0];
            }
            c["dims/i"] = (long long)nx;
            c["dims/j"] = (long long)ny;
            c["dims/k"] = (long long)nz;

            domain["topologies/mesh/type"] = "uniform";
            domain["topologies/mesh/coordset"] = "coords";
            domain["fields/u/association"] = "vertex";
            domain["fields/u/topology"] = "mesh";
            domain["fields/u/values"].set_external(const_cast<T *>(block.buffer.data()), block.buffer.size());

            if (blocks_v && i < blocks_v->size())
            {
                const auto &block_v = (*blocks_v)[i];
                domain["fields/v/association"] = "vertex";
                domain["fields/v/topology"] = "mesh";
                domain["fields/v/values"].set_external(const_cast<T *>(block_v.buffer.data()), block_v.buffer.size());
            }
        }
        return multi_mesh;
    }
} // end anonymous namespace

AscentBackend::AscentBackend(const BackendOptions &opts)
    : m_opts(opts),
      m_perf_logger(
          "reader_timers",
          [&]()
          { int rank; MPI_Comm_rank(opts.comm, &rank); return rank; }(),
          [&]()
          { char hostname[256]; gethostname(hostname, sizeof(hostname)); return std::string(hostname); }(),
          {"ADIOS_Wait", "ADIOS_Read_U", "ADIOS_Read_V", "Blueprint_Time", "Vis_Time", "total_step"}),
      m_reader(opts, m_perf_logger)
{
    conduit::Node open_opts;
    open_opts["mpi_comm"] = MPI_Comm_c2f(m_reader.GetComm());
    m_ascent.open(open_opts);
}

void AscentBackend::Run()
{
    int rank, procs;
    MPI_Comm_rank(m_reader.GetComm(), &rank);
    MPI_Comm_size(m_reader.GetComm(), &procs);

    while (m_reader.BeginStep() == adios2::StepStatus::OK)
    {
        m_perf_logger.start("total_step");
        size_t step = m_reader.CurrentStep();
        const auto &current_opts = m_reader.GetOptions();

        if (rank == 0)
        {
            std::cout << "Processing step: " << step << std::endl;
        }

        conduit::Node mesh_blueprint;
        m_perf_logger.start("Blueprint_Time");

        if (current_opts.block_mode == "repartition")
        {
            std::vector<double> u_buf, v_buf;
            RepartitionInfo read_info_u, read_info_v;
            m_reader.ReadRepartition(current_opts.u_var, u_buf, read_info_u);
            m_reader.ReadRepartition(current_opts.v_var, v_buf, read_info_v);
            mesh_blueprint = BuildRepartitionedBlueprint(read_info_u, u_buf, &v_buf, step, current_opts);
        }
        else // preserve mode
        {
            std::cerr << __FILE__ << ":" << __LINE__  << std::endl;    
            std::vector<BlockData<double>> blocks_u, blocks_v;
            std::cerr << __FILE__ << ":" << __LINE__  << std::endl;
            size_t total_blocks_u = m_reader.ReadPreserve(current_opts.u_var, blocks_u);
            std::cerr << __FILE__ << ":" << __LINE__  << std::endl;
            m_reader.ReadPreserve(current_opts.v_var, blocks_v);
std::cerr << __FILE__ << ":" << __LINE__  << std::endl;
            // Add warning for inefficient process count
            if (rank == 0 && total_blocks_u > 0 && procs > total_blocks_u)
            {
                std::cerr << "Warning: Running with " << procs << " processes but only "
                          << total_blocks_u << " data blocks are available. "
                          << (procs - total_blocks_u) << " processes will be idle." << std::endl;
            }

            // If debug is on, print the number of blocks each rank is handling
            if (current_opts.debug)
            {
                std::cout << "[Rank " << rank << "] Processing " << blocks_u.size() << " blocks." << std::endl;
            }

            mesh_blueprint = BuildMultiBlockBlueprint(blocks_u, &blocks_v, step, current_opts);
        }
        m_perf_logger.stop("Blueprint_Time");

        if (current_opts.debug)
        {
            try
            {
                conduit::Node info;
                // This is a collective call, all ranks must participate.
                bool is_valid = conduit::blueprint::verify("mesh", mesh_blueprint, info);

                if (!is_valid && rank == 0)
                {
                    std::cerr << "Blueprint verification failed at step " << step << ":\n";
                    info.print();
                }
            }
            catch (const std::exception &e)
            {
                if (rank == 0)
                {
                    std::cerr << "Exception during blueprint verification at step " << step << ": " << e.what() << "\n";
                }
            }
        }

        m_perf_logger.start("Vis_Time");
        m_ascent.publish(mesh_blueprint);
        m_ascent.execute(conduit::Node());
        m_perf_logger.stop("Vis_Time");

        m_reader.EndStep();
        m_perf_logger.stop("total_step");
        m_perf_logger.logStep(step);
    }
    m_ascent.close();
}