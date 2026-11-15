#include "adios_writer_backend.h"

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <stdexcept>
#include <unistd.h>

namespace
{
    adios2::ADIOS MakeAdios(MPI_Comm comm)
    {
        if (std::filesystem::exists("adios2.xml"))
            return adios2::ADIOS("adios2.xml", comm);
        return adios2::ADIOS(comm);
    }

    std::string Lower(std::string text)
    {
        std::transform(text.begin(), text.end(), text.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        return text;
    }

    // SST with a marshalling other than BP5 (FFS) ignores a memory selection
    // and sends the first values of the buffer as if they were contiguous
    // (ADIOS2 2.11, SstWriter.tcc). BP5 files and SST's BP5 marshalling
    // honour it.
    bool HonoursMemorySelection(adios2::IO &io)
    {
        const std::string engine = Lower(io.EngineType());
        if (engine != "sst" && engine != "effis") // effis is SST under another name
            return true;
        for (const auto &kv : io.Parameters())
            if (Lower(kv.first) == "marshalmethod")
                return Lower(kv.second) == "bp5";
        return true; // SST marshals with BP5 by default
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
    // A slab's owned points are a prefix of its buffer, so an engine that
    // ignores the memory selection still sends the right values. A brick's
    // are not. Packing them into a contiguous buffer does not help either:
    // with ADIOS2 2.11 an 8-reader brick written through SST with FFS read
    // back wrong even then, while the same packed blocks through BP5
    // marshalling were bitwise identical. Refuse the combination.
    if (m_opts.read_decomposition == "brick" && !HonoursMemorySelection(m_io_out))
        throw std::runtime_error(
            "AnalysisOutput: SST with MarshalMethod other than BP5 cannot carry a "
            "brick decomposition; use MarshalMethod=BP5, a BP5 file, or -D slab");
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

        // ReadRepartition adds the neighbour's first plane on every axis
        // where this piece is not the last. Write only the owned points: the
        // buffer holds local_dims, of which the owned box starts at zero, so
        // a memory selection picks it out on any axis (slab or brick).
        const auto &write_dims = read_info.owned_dims;
        const bool trimmed = read_info.owned_dims != read_info.local_dims;
        size_t owned_count = write_dims.empty() ? 0 : 1;
        for (size_t n : write_dims)
            owned_count *= n;

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
            if (owned_count == 0)
                continue; // more readers than planes: this one owns nothing
            if (trimmed)
                var.SetMemorySelection({adios2::Dims(read_info.local_dims.size(), 0), read_info.local_dims});
            else
                var.SetMemorySelection();
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
