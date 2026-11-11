#include "adios_writer_backend.h"

#include <filesystem>
#include <unistd.h>

namespace
{
    adios2::ADIOS MakeAdios(MPI_Comm comm)
    {
        if (std::filesystem::exists("adios2.xml"))
            return adios2::ADIOS("adios2.xml", comm);
        return adios2::ADIOS(comm);
    }
} // end anonymous namespace

AdiosWriterBackend::AdiosWriterBackend(const BackendOptions &opts)
    : m_opts(opts),
      m_perf_logger("reader_timers",
                    [&]() { int rank; MPI_Comm_rank(opts.comm, &rank); return rank; }(),
                    [&]() { char hostname[256]; gethostname(hostname, sizeof(hostname)); return std::string(hostname); }(),
                    {"ADIOS_Wait", "ADIOS_Read_U", "ADIOS_Read_V", "ADIOS_EndStep", "ADIOS_Write_Time", "total_step"}),
      m_reader(m_opts, m_perf_logger),
      m_adios(MakeAdios(m_reader.GetComm()))
{
    m_io_out = m_adios.DeclareIO("AnalysisOutput");
    if (m_io_out.EngineType().empty())
        m_io_out.SetEngine("BP5");
    m_writer = m_io_out.Open(m_opts.adios_output_file, adios2::Mode::Write);
    m_writer_open = true;
}

AdiosWriterBackend::~AdiosWriterBackend()
{
    if (m_writer_open)
    {
        try { m_writer.Close(); } catch (...) {}
    }
}

void AdiosWriterBackend::Run()
{
    const auto &opts = m_reader.GetOptions();
    int rank, size;
    MPI_Comm_rank(m_reader.GetComm(), &rank);
    MPI_Comm_size(m_reader.GetComm(), &size);

    while (m_reader.NextStep())
    {
        m_perf_logger.start("total_step");
        const size_t step = m_reader.CurrentStep();

        std::vector<double> u_buf, v_buf;
        RepartitionInfo read_info;
        m_reader.ReadRepartition(opts.u_var, u_buf, read_info);
        m_reader.ReadRepartition(opts.v_var, v_buf, read_info);
        // The deferred reads complete at EndStep(); then the simulation can go
        // on while we write (#42).
        m_reader.EndStep();

        // ReadRepartition adds one overlap plane in the slowest dimension on
        // every rank but the last. The owned planes come first in the
        // buffer, so writing one plane fewer writes exactly the owned part.
        auto write_dims = read_info.local_dims;
        if (rank != size - 1 && !write_dims.empty() && write_dims[0] > 0)
            write_dims[0] -= 1;

        m_perf_logger.start("ADIOS_Write_Time");
        m_writer.BeginStep();
        for (auto *field : {&opts.u_var, &opts.v_var})
        {
            if (field->empty())
                continue;
            auto var = m_io_out.InquireVariable<double>(*field);
            if (!var)
                var = m_io_out.DefineVariable<double>(*field, read_info.global_dims, read_info.local_start, write_dims);
            else
                var.SetSelection({read_info.local_start, write_dims});
            m_writer.Put(var, (field == &opts.u_var ? u_buf : v_buf).data());
        }
        m_writer.EndStep(); // the Puts are deferred: the buffers live until here
        m_perf_logger.stop("ADIOS_Write_Time");

        m_perf_logger.stop("total_step");
        m_perf_logger.logStep(step);
    }
    // Write the timings now, before teardown can get stuck (#75). The
    // destructor closes the file; by then main() has armed the guard. BP5
    // has written every step's data and metadata at its EndStep.
    m_perf_logger.finalize();
}
