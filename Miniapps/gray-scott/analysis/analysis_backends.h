#pragma once

#include <mpi.h>
#include <adios2.h>
#include <conduit.hpp>
#include <conduit_blueprint.hpp>
#include <conduit_relay.hpp>
#include <ascent.hpp>

#include <nlohmann/json.hpp>

#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <optional>
#include <array>
#include <memory>
#include <chrono>
#include <thread>
#include <numeric>
#include <functional>
#include <type_traits>
#include <algorithm>
#include <stdexcept>
#include <unistd.h>
#include "common/perf_logger.hpp"

// Structs to hold data for the two different read strategies
struct RepartitionInfo
{
    std::vector<size_t> global_dims;
    std::vector<size_t> local_start;
    std::vector<size_t> local_dims;
};

template <typename T>
struct BlockData
{
    std::vector<T> buffer;
    std::vector<size_t> start;
    std::vector<size_t> dims;
};

// ---------- Options ----------
struct BackendOptions
{
    std::string adios_file;
    std::string adios_engine = "BP5";
    std::string u_var = "U";
    std::string v_var = "V";
    std::string block_mode = "preserve"; // preserve | repartition
    std::optional<std::array<double, 3>> origin;
    std::optional<std::array<double, 3>> spacing;
    std::string sst_wait_mode = "block";
    double sst_timeout_seconds = 0.0;
    int adios_verbose = 0;
    bool debug_verify_blueprint = false;
    MPI_Comm comm = MPI_COMM_WORLD;

    static BackendOptions FromSettingsFile(const std::string &settings_path)
    {
        BackendOptions opts;
        nlohmann::json js;
        std::ifstream ifs(settings_path);
        if (!ifs.is_open())
            throw std::runtime_error("Cannot open settings file: " + settings_path);
        ifs >> js;

        if (js.contains("adios_file"))
            opts.adios_file = js["adios_file"].get<std::string>();
        if (js.contains("output_file_name") && opts.adios_file.empty())
            opts.adios_file = js["output_file_name"].get<std::string>();

        if (js.contains("Fides_Origin"))
        {
            auto arr = js["Fides_Origin"];
            if (arr.is_array() && arr.size() >= 3)
                opts.origin = {arr[0].get<double>(), arr[1].get<double>(), arr[2].get<double>()};
        }
        if (js.contains("Fides_Spacing"))
        {
            auto arr = js["Fides_Spacing"];
            if (arr.is_array() && arr.size() >= 3)
                opts.spacing = {arr[0].get<double>(), arr[1].get<double>(), arr[2].get<double>()};
        }

        if (js.contains("adios_engine"))
            opts.adios_engine = js["adios_engine"].get<std::string>();
        if (js.contains("block_mode"))
            opts.block_mode = js["block_mode"].get<std::string>();
        if (js.contains("sst_wait_mode"))
            opts.sst_wait_mode = js["sst_wait_mode"].get<std::string>();
        if (js.contains("sst_timeout_seconds"))
            opts.sst_timeout_seconds = js["sst_timeout_seconds"].get<double>();
        if (js.contains("adios_verbose"))
            opts.adios_verbose = js["adios_verbose"].get<int>(); // ADDED
        if (js.contains("debug_verify_blueprint"))
            opts.debug_verify_blueprint = js["debug_verify_blueprint"].get<bool>();

        return opts;
    }
};

// ---------- Processor interface ----------
struct ProcessorInterface
{
    virtual ~ProcessorInterface() = default;
    virtual void Initialize(MPI_Comm comm, const BackendOptions &opts) = 0;
    virtual void Publish(const conduit::Node &mesh) = 0;
    virtual void ExecuteActions(const conduit::Node &actions) = 0;
    virtual void Finalize() = 0;
};

// ---------- ProcessorAscent example ----------
struct ProcessorAscent : public ProcessorInterface
{
    void Initialize(MPI_Comm comm, const BackendOptions &opts) override
    {
        m_comm = comm;
        m_opts = opts;
        conduit::Node open_opts;
        open_opts["mpi_comm"] = MPI_Comm_c2f(m_comm);
        m_ascent.open(open_opts);
    }

    void Publish(const conduit::Node &mesh) override { m_ascent.publish(mesh); }
    void ExecuteActions(const conduit::Node &actions) override { m_ascent.execute(actions); }
    void Finalize() override { m_ascent.close(); }

private:
    ascent::Ascent m_ascent;
    MPI_Comm m_comm = MPI_COMM_WORLD;
    BackendOptions m_opts;
};

// ---------- Templated Adios2 -> Conduit backend ----------
template <typename ProcessorT>
class Adios2ConduitBackend
{
public:
    static_assert(std::is_base_of<ProcessorInterface, ProcessorT>::value,
                  "ProcessorT must derive from ProcessorInterface");

    Adios2ConduitBackend() = default;
    ~Adios2ConduitBackend() = default;

    void Initialize(const BackendOptions &opts)
    {
        m_opts = opts;
        m_comm = opts.comm;

        // --- Initialize PerfLogger unconditionally ---
        const std::string timers_dir = "reader_timers";
        int rank;
        char hostname[256];
        MPI_Comm_rank(m_comm, &rank);
        gethostname(hostname, sizeof(hostname));
        std::vector<std::string> timer_names = {"ADIOS_Time", "Blueprint_Time", "Vis_Time", "total_step"};
        m_perf_logger = std::make_unique<PerfLogger>(timers_dir, rank, std::string(hostname), timer_names);
        // --- End PerfLogger Init ---

        m_adios = std::make_unique<adios2::ADIOS>(m_comm);
        m_io = std::make_unique<adios2::IO>(m_adios->DeclareIO("AnalysisIO"));

        if (m_opts.adios_verbose > 0)
        {
            m_io->SetParameter("verbose", std::to_string(m_opts.adios_verbose));
        }

        if (!m_opts.adios_engine.empty())
        {
            try
            {
                m_io->SetEngine(m_opts.adios_engine);
            }
            catch (const std::exception &e)
            {
                std::cerr << "Warning: Failed to set ADIOS2 engine to '" << m_opts.adios_engine << "': " << e.what() << std::endl;
            }
        }

        m_engine = std::make_unique<adios2::Engine>(m_io->Open(m_opts.adios_file, adios2::Mode::Read));
        if (!m_engine)
            throw std::runtime_error("Failed to open ADIOS2 engine: " + m_opts.adios_file);

        m_processor = std::make_unique<ProcessorT>();
        m_processor->Initialize(m_comm, m_opts);

        ReadFidesAttributes();
    }

    void Run(std::function<void(const conduit::Node &, size_t)> step_callback)
    {
        size_t step = 0;

        // Main loop for processing steps
        while (true)
        {
            m_perf_logger->start("total_step");

            // Determine the timeout for the BeginStep call based on user options.
            float step_timeout = -1.0f; // Default to block indefinitely.
            if (m_opts.sst_wait_mode == "timeout")
            {
                step_timeout = static_cast<float>(m_opts.sst_timeout_seconds);
            }

            // Make a single, efficient call to BeginStep with the correct timeout.
            const adios2::StepStatus status = m_engine->BeginStep(adios2::StepMode::Read, step_timeout);

            if (status == adios2::StepStatus::OK)
            {
                // Step is ready, proceed to process data.
            }
            else if (status == adios2::StepStatus::EndOfStream)
            {
                // Simulation has ended.
                m_processor->Finalize();
                return;
            }
            else if (status == adios2::StepStatus::NotReady)
            {
                // This status is only returned if a timeout was used.
                std::cerr << "SST timeout of " << step_timeout
                          << "s reached while waiting for step " << step << ". Exiting.\n";
                m_processor->Finalize();
                return;
            }

            // --- I/O Phase ---
            m_perf_logger->start("ADIOS_Time");
            bool data_ok = false;
            if (m_opts.block_mode == "repartition")
            {
                data_ok = Read_Repartition<double>(m_opts.u_var, m_u_buf_d, m_read_info_u);
                if (data_ok)
                    Read_Repartition<double>(m_opts.v_var, m_v_buf_d, m_read_info_v);
            }
            else
            { // preserve
                data_ok = Read_Preserve<double>(m_opts.u_var, m_blocks_u);
                if (data_ok)
                    Read_Preserve<double>(m_opts.v_var, m_blocks_v);
            }
            m_perf_logger->stop("ADIOS_Time");
            if (!data_ok)
                throw std::runtime_error("Failed to read variable '" + m_opts.u_var + "'.");

            // --- Blueprint Creation Phase ---
            m_perf_logger->start("Blueprint_Time");
            conduit::Node mesh;
            if (m_opts.block_mode == "repartition")
            {
                mesh = Build_Repartitioned<double>(m_read_info_u, m_u_buf_d, m_v_buf_d.empty() ? nullptr : &m_v_buf_d, step);
            }
            else
            { // preserve
                mesh = Build_MultiBlock<double>(m_blocks_u, m_blocks_v.empty() ? nullptr : &m_blocks_v, step);
            }
            m_perf_logger->stop("Blueprint_Time");

            if (m_opts.debug_verify_blueprint)
                DebugPrint(mesh, step);

            m_perf_logger->start("Vis_Time");
            m_processor->Publish(mesh);
            m_processor->ExecuteActions(conduit::Node());
            m_perf_logger->stop("Vis_Time");

            if (step_callback)
                step_callback(mesh, step);

            m_engine->EndStep();

            m_perf_logger->stop("total_step");
            m_perf_logger->logStep(step);

            ++step;
        }
    }

    void Finalize()
    {
        if (m_processor)
            m_processor->Finalize();
        if (m_engine)
        {
            m_engine->Close();
            m_engine.reset();
        }
        m_io.reset();
        m_adios.reset();
    }

private:
    void DebugPrint(const conduit::Node &mesh, size_t step)
    {
        int rank = 0;
        int size = 1;
        MPI_Comm_rank(m_comm, &rank);
        MPI_Comm_size(m_comm, &size);

        for (int i = 0; i < size; ++i)
        {
            MPI_Barrier(m_comm);
            if (i == rank)
            {
                std::cout << "\n---------- Conduit Mesh Blueprint (Step " << step << ", Rank " << rank << ") ----------\n";
                mesh.print();
                std::cout << "--------------------------------------------------------------------------------------\n\n";
                std::cout.flush();
            }
        }
        MPI_Barrier(m_comm);
    }

    void ReadFidesAttributes()
    {
        try
        {
            auto attr_o = m_io->InquireAttribute<double>("Fides_Origin");
            if (attr_o)
            {
                auto data = attr_o.Data();
                if (data.size() >= 3)
                    m_opts.origin = {data[0], data[1], data[2]};
            }
        }
        catch (const std::exception &e)
        { /* Ignore */
        }
        try
        {
            auto attr_s = m_io->InquireAttribute<double>("Fides_Spacing");
            if (attr_s)
            {
                auto data = attr_s.Data();
                if (data.size() >= 3)
                    m_opts.spacing = {data[0], data[1], data[2]};
            }
        }
        catch (const std::exception &e)
        { /* Ignore */
        }
    }

    template <typename T>
    bool Read_Preserve(const std::string &var_name, std::vector<BlockData<T>> &blocks_out)
    {
        blocks_out.clear();
        if (var_name.empty())
            return true;

        try
        {
            auto var = m_io->InquireVariable<T>(var_name);
            if (var)
            {
                int rank = 0;
                int size = 1;
                MPI_Comm_rank(m_comm, &rank);
                MPI_Comm_size(m_comm, &size);

                auto adios_blocks = m_engine->BlocksInfo(var, m_engine->CurrentStep());
                if (adios_blocks.empty())
                    return true;

                for (size_t i = 0; i < adios_blocks.size(); ++i)
                {
                    if (i % size == rank)
                    {
                        BlockData<T> block;
                        block.start = adios_blocks[i].Start;
                        block.dims = adios_blocks[i].Count;

                        var.SetBlockSelection(i);
                        size_t count = productDims(block.dims);
                        block.buffer.resize(count);
                        m_engine->Get(var, block.buffer.data(), adios2::Mode::Sync);
                        blocks_out.push_back(std::move(block));
                    }
                }
                return true;
            }
        }
        catch (const std::exception &e)
        {
            std::cerr << "Exception in Read_Preserve for variable '" << var_name << "': " << e.what() << std::endl;
            return false;
        }
        return false;
    }

    template <typename T>
    conduit::Node Build_MultiBlock(const std::vector<BlockData<T>> &blocks_u, const std::vector<BlockData<T>> *blocks_v, size_t step)
    {
        conduit::Node multi_mesh(conduit::DataType::list());

        std::array<double, 3> global_origin_vals = {0.0, 0.0, 0.0};
        std::array<double, 3> spacing_vals = {0.1, 0.1, 0.1};
        if (m_opts.origin)
            global_origin_vals = *m_opts.origin;
        if (m_opts.spacing)
            spacing_vals = *m_opts.spacing;

        for (size_t i = 0; i < blocks_u.size(); ++i)
        {
            const auto &block = blocks_u[i];

            conduit::Node &domain = multi_mesh.append();

            domain["state/step"] = static_cast<long long>(step);

            std::array<double, 3> local_origin_vals = global_origin_vals;
            for (size_t d = 0; d < block.start.size(); ++d)
            {
                size_t dim_idx = block.start.size() - 1 - d;
                size_t start_offset = block.start[d];
                size_t block_dim = block.dims[d];

                double physical_origin = start_offset * spacing_vals[dim_idx];
                if (block_dim > 0)
                {
                    double correction = (start_offset / block_dim) * spacing_vals[dim_idx];
                    local_origin_vals[dim_idx] += (physical_origin - correction);
                }
                else
                {
                    local_origin_vals[dim_idx] += physical_origin;
                }
            }

            conduit::Node &c = domain["coordsets/coords"];
            c["type"] = "uniform";
            c["origin/x"] = local_origin_vals[0];
            c["origin/y"] = local_origin_vals[1];
            c["origin/z"] = local_origin_vals[2];
            c["spacing/dx"] = spacing_vals[0];
            c["spacing/dy"] = spacing_vals[1];
            c["spacing/dz"] = spacing_vals[2];

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

    template <typename T>
    bool Read_Repartition(const std::string &var_name, std::vector<T> &buffer, RepartitionInfo &read_info)
    {
        if (var_name.empty())
        {
            buffer.clear();
            return false;
        }
        try
        {
            auto var = m_io->InquireVariable<T>(var_name);
            if (var)
            {
                int rank = 0;
                int size = 1;
                MPI_Comm_rank(m_comm, &rank);
                MPI_Comm_size(m_comm, &size);
                read_info.global_dims = var.Shape();
                const size_t n_dims = read_info.global_dims.size();
                read_info.local_start.assign(n_dims, 0);
                read_info.local_dims = read_info.global_dims;
                if (n_dims > 0)
                {
                    size_t slab_size = read_info.global_dims[0] / size;
                    size_t remainder = read_info.global_dims[0] % size;
                    read_info.local_start[0] = rank * slab_size + std::min((size_t)rank, remainder);
                    read_info.local_dims[0] = slab_size + (rank < remainder ? 1 : 0);
                }
                if (productDims(read_info.local_dims) > 0)
                {
                    var.SetSelection({read_info.local_start, read_info.local_dims});
                    size_t local_count = productDims(read_info.local_dims);
                    if (buffer.size() != local_count)
                        buffer.resize(local_count);
                    m_engine->Get(var, buffer.data(), adios2::Mode::Sync);
                }
                else
                {
                    buffer.clear();
                }
                return true;
            }
        }
        catch (const std::exception &e)
        {
            std::cerr << "Exception in Read_Repartition for variable '" << var_name << "': " << e.what() << std::endl;
        }
        return false;
    }

    template <typename T>
    conduit::Node Build_Repartitioned(const RepartitionInfo &read_info, std::vector<T> &bufU, std::vector<T> *bufV, size_t step)
    {
        conduit::Node out;
        std::array<double, 3> global_origin = {0.0, 0.0, 0.0};
        std::array<double, 3> spacing = {0.1, 0.1, 0.1};
        if (m_opts.origin)
            global_origin = *m_opts.origin;
        if (m_opts.spacing)
            spacing = *m_opts.spacing;
        std::array<double, 3> local_origin_vals = global_origin;
        for (size_t i = 0; i < read_info.local_start.size(); ++i)
        {
            size_t dim_idx = read_info.local_start.size() - 1 - i;
            local_origin_vals[dim_idx] += read_info.local_start[i] * spacing[dim_idx];
        }
        conduit::Node &c = out["coordsets/coords"];
        c["type"] = "uniform";
        c["origin/x"] = local_origin_vals[0];
        c["origin/y"] = local_origin_vals[1];
        c["origin/z"] = local_origin_vals[2];
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
        out["topologies/mesh/type"] = "uniform";
        out["topologies/mesh/coordset"] = "coords";
        out["fields/u/association"] = "vertex";
        out["fields/u/topology"] = "mesh";
        out["fields/u/values"].set_external(bufU);
        if (bufV && !bufV->empty())
        {
            out["fields/v/association"] = "vertex";
            out["fields/v/topology"] = "mesh";
            out["fields/v/values"].set_external(*bufV);
        }
        out["state/step"] = static_cast<long long>(step);
        return out;
    }

    static size_t product(const std::vector<size_t> &v)
    {
        if (v.empty())
            return 0;
        return std::accumulate(v.begin(), v.end(), size_t{1}, std::multiplies<size_t>());
    }

    template <typename Vec>
    static size_t productDims(const Vec &v)
    {
        if (v.empty())
            return 0;
        size_t p = 1;
        for (auto &x : v)
            p *= static_cast<size_t>(x);
        return p;
    }

private:
    BackendOptions m_opts;
    MPI_Comm m_comm = MPI_COMM_WORLD;
    std::unique_ptr<adios2::ADIOS> m_adios;
    std::unique_ptr<adios2::IO> m_io;
    std::unique_ptr<adios2::Engine> m_engine;
    std::unique_ptr<ProcessorT> m_processor;
    std::unique_ptr<PerfLogger> m_perf_logger;

    // Buffers and info structs for I/O and data handling
    std::vector<double> m_u_buf_d, m_v_buf_d;
    std::vector<float> m_u_buf_f, m_v_buf_f;
    RepartitionInfo m_read_info_u, m_read_info_v;
    std::vector<BlockData<double>> m_blocks_u, m_blocks_v;
};