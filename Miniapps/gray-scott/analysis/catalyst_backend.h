#pragma once

#include "analysis_backend_interface.h"
#include "adios_reader.h"
#include "common/perf_logger.hpp"
#include <memory>

class CatalystBackend : public AnalysisBackend
{
public:
    CatalystBackend(const BackendOptions &opts);
    ~CatalystBackend();
    void Run() override;

private:
    const BackendOptions &m_opts;
    PerfLogger m_perf_logger;
    AdiosReader m_reader;
};

