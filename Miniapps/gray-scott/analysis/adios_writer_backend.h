#pragma once

#include "analysis_backend_interface.h"
#include "adios_reader.h"
#include "common/perf_logger.hpp"
#include <adios2.h>

// Writes each staged step back to disk with ADIOS2 (#76), so in transit
// runs can save data from the staging nodes instead of the simulation's.
// Uses the "AnalysisOutput" IO of ./adios2.xml when that file exists,
// otherwise BP5 with ADIOS2's defaults.
class AdiosWriterBackend : public AnalysisBackend
{
public:
    AdiosWriterBackend(const BackendOptions &opts);
    ~AdiosWriterBackend() override;
    void Run() override;

private:
    BackendOptions m_opts;
    PerfLogger m_perf_logger;
    AdiosReader m_reader;
    adios2::ADIOS m_adios;
    adios2::IO m_io_out;
    adios2::Engine m_writer;
    bool m_writer_open = false;
};
