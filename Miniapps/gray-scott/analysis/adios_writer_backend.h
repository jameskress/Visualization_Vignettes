#pragma once

#include "analysis_backend_interface.h"
#include "adios_reader.h"
#include <adios2.h>
#include <vector>

class AdiosWriterBackend : public AnalysisBackend
{
public:
    AdiosWriterBackend(const BackendOptions &opts);
    ~AdiosWriterBackend() override = default;

    void Run() override;

private:
    BackendOptions m_opts;
    PerfLogger m_perf_logger;
    AdiosReader m_reader;
    
    // ADIOS2 Output components
    adios2::ADIOS m_adios;
    adios2::IO m_io_out;
    adios2::Engine m_writer;
};