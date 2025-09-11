#include "adios_reader.h"
#include "analysis_backend_interface.h"
#include <numeric>
#include <algorithm>
#include <iostream>

AdiosReader::AdiosReader(const BackendOptions &opts, PerfLogger &logger)
    : m_opts(opts), m_logger(logger), m_comm(opts.comm)
{
    m_adios = std::make_unique<adios2::ADIOS>(m_comm);
    m_io = std::make_unique<adios2::IO>(m_adios->DeclareIO("AnalysisIO"));

    if (m_opts.adios_verbose > 0)
        m_io->SetParameter("verbose", std::to_string(m_opts.adios_verbose));

    m_io->SetEngine(m_opts.adios_engine);

    // Automatically set a short OpenTimeout for non-streaming engines.
    // This prevents the application from hanging indefinitely on corrupt/inaccessible files.
    // For SST, we let it use its default blocking behavior.
    if (m_opts.adios_engine != "SST")
    {
        m_io->SetParameter("OpenTimeoutSecs", "5.0");
    }

    m_engine = std::make_unique<adios2::Engine>(m_io->Open(m_opts.adios_file, adios2::Mode::Read));

    ReadFidesAttributes(); // Read attributes and potentially update m_opts
}

AdiosReader::~AdiosReader()
{
    if (m_engine)
        m_engine->Close();
}

adios2::StepStatus AdiosReader::BeginStep()
{
    m_logger.start("ADIOS_Wait");
    float step_timeout = (m_opts.sst_wait_mode == "timeout") ? static_cast<float>(m_opts.sst_timeout_seconds) : -1.0f;
    const adios2::StepStatus status = m_engine->BeginStep(adios2::StepMode::Read, step_timeout);
    m_logger.stop("ADIOS_Wait");
    return status;
}

void AdiosReader::EndStep()
{
    m_engine->EndStep();
}

size_t AdiosReader::CurrentStep() const
{
    return m_engine->CurrentStep();
}

const BackendOptions &AdiosReader::GetOptions() const
{
    return m_opts;
}

MPI_Comm AdiosReader::GetComm() const
{
    return m_comm;
}

template <typename Vec>
size_t AdiosReader::productDims(const Vec &v)
{
    if (v.empty())
        return 0;
    size_t p = 1;
    for (auto &x : v)
        p *= static_cast<size_t>(x);
    return p;
}

void AdiosReader::ReadFidesAttributes()
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
    catch (const std::exception &)
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
    catch (const std::exception &)
    { /* Ignore */
    }
}

// Method to read data in "preserve" block mode which returns the data to the reader just
// as it was written, with each rank getting a subset of the blocks.
// The blocks_out vector will contain one entry per block assigned to this rank,
// with the block's start indices, dimensions, and data buffer.
template <typename T>
size_t AdiosReader::ReadPreserve(const std::string &var_name, std::vector<BlockData<T>> &blocks_out)
{
    blocks_out.clear();
    if (var_name.empty())
        return 0;

    auto var = m_io->InquireVariable<T>(var_name);
    if (!var)
        return 0;

    int rank, size;
    MPI_Comm_rank(m_comm, &rank);
    MPI_Comm_size(m_comm, &size);

    auto adios_blocks = m_engine->BlocksInfo(var, m_engine->CurrentStep());
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

            std::string timer_name = "ADIOS_Read_" + var_name;
            m_logger.start(timer_name);
            m_engine->Get(var, block.buffer.data(), adios2::Mode::Sync);
            m_logger.stop(timer_name);
            blocks_out.push_back(std::move(block));
        }
    }
    return adios_blocks.size();
}

// Method to read data in "repartition" mode which redistributes the data
// across ranks in a balanced manner. Each rank gets a contiguous slab of the
// global data. The buffer will contain the local data, and read_info will
// provide information about the global and local dimensions and offsets.
template <typename T>
void AdiosReader::ReadRepartition(const std::string &var_name, std::vector<T> &buffer, RepartitionInfo &read_info)
{
    if (var_name.empty())
    {
        buffer.clear();
        return;
    }
    auto var = m_io->InquireVariable<T>(var_name);
    if (!var)
    {
        buffer.clear();
        return;
    }

    int rank, size;
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

    size_t local_count = productDims(read_info.local_dims);
    if (local_count > 0)
    {
        var.SetSelection({read_info.local_start, read_info.local_dims});
        if (buffer.size() != local_count)
            buffer.resize(local_count);

        std::string timer_name = "ADIOS_Read_" + var_name;
        m_logger.start(timer_name);
        m_engine->Get(var, buffer.data(), adios2::Mode::Sync);
        m_logger.stop(timer_name);
    }
    else
    {
        buffer.clear();
    }
}

// Explicit template instantiations
template size_t AdiosReader::ReadPreserve<double>(const std::string &, std::vector<BlockData<double>> &);
template void AdiosReader::ReadRepartition<double>(const std::string &, std::vector<double> &, RepartitionInfo &);
