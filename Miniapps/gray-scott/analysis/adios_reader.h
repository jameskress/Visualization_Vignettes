#pragma once

#include "analysis_backend_interface.h"
#include "common/perf_logger.hpp"
#include <adios2.h>
#include <vector>
#include <string>
#include <memory>

// Forward declarations for data structures
struct RepartitionInfo;
template <typename T> struct BlockData;

class AdiosReader
{
public:
    AdiosReader(const BackendOptions &opts, PerfLogger &logger);
    ~AdiosReader();

    // Stream control
    adios2::StepStatus BeginStep();
    void EndStep();
    size_t CurrentStep() const;

    // Data reading methods
    template <typename T>
    size_t ReadPreserve(const std::string &var_name, std::vector<BlockData<T>> &blocks_out);
    template <typename T>
    void ReadRepartition(const std::string &var_name, std::vector<T> &buffer, RepartitionInfo &read_info);

    // Accessors
    const BackendOptions& GetOptions() const;
    MPI_Comm GetComm() const;

private:
    void ReadFidesAttributes();
    
    template <typename Vec> static size_t productDims(const Vec &v);

    BackendOptions m_opts; // A mutable copy for internal use
    PerfLogger &m_logger;
    MPI_Comm m_comm = MPI_COMM_WORLD;
    std::unique_ptr<adios2::ADIOS> m_adios;
    std::unique_ptr<adios2::IO> m_io;
    std::unique_ptr<adios2::Engine> m_engine;
};

