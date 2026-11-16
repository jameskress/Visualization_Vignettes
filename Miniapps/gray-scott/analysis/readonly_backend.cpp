#include "readonly_backend.h"

#include <mpi.h>
#include <unistd.h>

ReadOnlyBackend::ReadOnlyBackend(const BackendOptions &opts)
    : m_opts(opts),
      m_perf_logger("reader_timers",
                    [&]() { int rank; MPI_Comm_rank(opts.comm, &rank); return rank; }(),
                    [&]() { char hostname[256]; gethostname(hostname, sizeof(hostname)); return std::string(hostname); }(),
                    // The same timers as the Ascent and Catalyst backends, so
                    // reduce_timers.py and comparisons need no special case;
                    // Vis_Time is always zero here.
                    {"ADIOS_Wait", "ADIOS_Read_U", "ADIOS_Read_V", "ADIOS_EndStep", "Halo_Exchange", "Blueprint_Time", "Vis_Time", "total_step"}),
      m_reader(opts, m_perf_logger)
{
}

void ReadOnlyBackend::Run()
{
    while (m_reader.NextStep())
    {
        m_perf_logger.start("total_step");
        const size_t step = m_reader.CurrentStep();
        RepartitionInfo read_info;
        m_perf_logger.start("Blueprint_Time");
        m_reader.ReadRepartition(m_reader.GetOptions().u_var, m_u, read_info);
        m_reader.ReadRepartition(m_reader.GetOptions().v_var, m_v, read_info);
        // The deferred reads complete here; nothing else is done with them.
        m_reader.EndStep();
        m_perf_logger.stop("Blueprint_Time");
        m_perf_logger.start("Vis_Time");
        m_perf_logger.stop("Vis_Time");
        m_perf_logger.stop("total_step");
        m_perf_logger.logStep(step);
    }
    // Write the timings now, before teardown can get stuck (#75).
    m_perf_logger.finalize();
}
