#pragma once

#include "analysis_backend_interface.h"
#include "adios_reader.h"
#include "common/perf_logger.hpp"

#include <vector>

// Reads every staged step with the same repartition as the other backends
// and does nothing else with it: the ADIOS2 transport alone, for measuring
// SST at scale and as the in transit baseline the visualization backends
// add their work to. Its buffers are kept across steps, so a step costs
// only the read.
class ReadOnlyBackend : public AnalysisBackend
{
public:
    explicit ReadOnlyBackend(const BackendOptions &opts);
    void Run() override;

private:
    const BackendOptions &m_opts;
    PerfLogger m_perf_logger;
    AdiosReader m_reader;
    std::vector<double> m_u;
    std::vector<double> m_v;
};
