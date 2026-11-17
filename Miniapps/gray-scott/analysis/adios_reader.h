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
    // Begins the next step: true when one is ready, false at the end of the
    // stream. A step that is not ready yet (the timeout wait mode) is waited
    // for again, not taken as the end; an ADIOS2 error throws (#42).
    bool NextStep();
    // Ends the step; the deferred reads of ReadRepartition complete here,
    // and with reader_shared_planes "exchange" the shared planes are then
    // taken from the neighbouring readers (collective over the reader
    // communicator: every reader must call it, as every backend does).
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
    // Minor page faults taken while sizing the read buffers since the last
    // call (ReadRepartition's Read_Alloc), then reset.
    double TakeAllocFaults();

private:
    void ReadFidesAttributes();

    template <typename Vec> static size_t productDims(const Vec &v);
    // Fills the shared planes of the step's ReadRepartition buffers from the
    // neighbouring readers.
    void ExchangeSharedPlanes();

    // A ReadRepartition buffer whose shared planes come from the neighbours.
    struct PendingPlanes
    {
        char *data;
        size_t elem_size;
        std::vector<size_t> local_dims; // the buffer's extent
        std::vector<size_t> owned_dims;
        std::vector<bool> shared_high;
    };
    std::vector<PendingPlanes> m_pending_planes;
    // Step_Latency (ADIOS2 #5272): this rank's wall-clock time when
    // BeginStep returned, and the writer's (rank 0) entering EndStep().
    double m_begin_wall = 0.0;
    double m_writer_endstep_wall = 0.0;
    bool m_have_endstep_wall = false;
    // The packed planes, kept across steps so they are not reallocated.
    std::vector<char> m_send_planes;
    std::vector<char> m_recv_planes;
    // This rank's piece in the reader grid, slowest axis first (set by
    // ReadRepartition).
    std::vector<int> m_parts;
    std::vector<int> m_coords;

    BackendOptions m_opts; // A mutable copy for internal use
    PerfLogger &m_logger;
    MPI_Comm m_comm = MPI_COMM_WORLD;
    std::unique_ptr<adios2::ADIOS> m_adios;
    std::unique_ptr<adios2::IO> m_io;
    std::unique_ptr<adios2::Engine> m_engine;
    bool m_attributes_after_first_step = false;
    double m_alloc_faults = 0.0;
};
