#include "adios_writer_backend.h"
#include <iostream>
#include <unistd.h>

AdiosWriterBackend::AdiosWriterBackend(const BackendOptions &opts)
    : m_opts(opts),
      m_perf_logger("writer_timers",
                    [&]() { int rank; MPI_Comm_rank(opts.comm, &rank); return rank; }(),
                    [&]() { char hostname[256]; gethostname(hostname, sizeof(hostname)); return std::string(hostname); }(),
                    {"ADIOS_Wait", "ADIOS_Read_Time", "ADIOS_Write_Time", "total_step"}),
      m_reader(opts, m_perf_logger),
      m_adios("adios2.xml", opts.comm)
{
    // Initialize ADIOS2 for writing using the 'AnalysisOutput' IO block
    m_io_out = m_adios.DeclareIO("AnalysisOutput");
    m_writer = m_io_out.Open(opts.adios_output_file, adios2::Mode::Write);
}

void AdiosWriterBackend::Run()
{
    int rank;
    MPI_Comm_rank(m_reader.GetComm(), &rank);

    while (m_reader.BeginStep() == adios2::StepStatus::OK)
    {
        m_perf_logger.start("total_step");
        size_t step = m_reader.CurrentStep();
        
        std::vector<double> u_buf, v_buf; 
        RepartitionInfo read_info;

        // 1. Read data via the official reader policy
        m_perf_logger.start("ADIOS_Read_Time");
        m_reader.ReadRepartition(m_opts.u_var, u_buf, read_info);
        m_reader.ReadRepartition(m_opts.v_var, v_buf, read_info);
        m_perf_logger.stop("ADIOS_Read_Time");

        // 2. Write data to disk
        m_perf_logger.start("ADIOS_Write_Time");
        m_writer.BeginStep();

        // Check if variables are defined; define them if this is the first step
        adios2::Variable<double> var_u = m_io_out.InquireVariable<double>(m_opts.u_var);
        if (!var_u) {
            var_u = m_io_out.DefineVariable<double>(
                m_opts.u_var, read_info.global_dims, read_info.local_start, read_info.local_dims);
        }
        
        adios2::Variable<double> var_v = m_io_out.InquireVariable<double>(m_opts.v_var);
        if (!var_v) {
            var_v = m_io_out.DefineVariable<double>(
                m_opts.v_var, read_info.global_dims, read_info.local_start, read_info.local_dims);
        }

        m_writer.Put(var_u, u_buf.data());
        m_writer.Put(var_v, v_buf.data());

        m_writer.EndStep();
        m_perf_logger.stop("ADIOS_Write_Time");

        m_reader.EndStep();
        m_perf_logger.stop("total_step");
        
        // Log performance metrics identically to the other backends
        m_perf_logger.logStep(step); 
    }
    
    m_writer.Close();
}