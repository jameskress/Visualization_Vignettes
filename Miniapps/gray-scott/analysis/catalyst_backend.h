#pragma once

#include "analysis_backend_interface.h"
#include "adios_reader.h"
#include "common/perf_logger.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <vector>

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
    // The step's fields and the point ghost flags, kept across steps so
    // nothing field-sized is allocated in the step loop (AGENTS.md, zero-copy
    // invariant). ReadRepartition resizes a buffer only when its size
    // changes. Fresh vectors each step zero-filled, page-faulted and freed
    // about 2 GB per field per reader at 64 + 4 nodes (sites/shaheen/README.md,
    // "Catalyst reader performance").
    std::vector<double> m_u_buf, m_v_buf;
    std::vector<std::uint8_t> m_point_ghosts;
    // The shape the flags were filled for: nx, ny, nz and the three
    // shared_high flags. The flags are refilled only when it changes.
    std::array<std::size_t, 6> m_ghost_shape{};
};
