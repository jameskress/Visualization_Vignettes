#pragma once

#include "analysis_backend_interface.h"
#include "adios_reader.h"
#include "common/perf_logger.hpp"
#include <ascent.hpp>
#include <cstdint>
#include <memory>
#include <vector>

class AscentBackend : public AnalysisBackend
{
public:
    AscentBackend(const BackendOptions &opts);
    void Run() override;

private:
    const BackendOptions &m_opts;
    PerfLogger m_perf_logger;
    AdiosReader m_reader;
    ascent::Ascent m_ascent;
    // All zero: every cell of the piece is owned. Kept across steps and
    // passed to Ascent with set_external (BuildRepartitionedBlueprint).
    std::vector<std::int32_t> m_cell_ghosts;
    // The step's fields and mesh, kept across steps so nothing field-sized
    // is allocated in the step loop (AGENTS.md, zero-copy invariant).
    std::vector<double> m_u_buf, m_v_buf;
    conduit::Node m_mesh;
};
