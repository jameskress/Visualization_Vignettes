#pragma once

#include <mpi.h>
#include <string>
#include <vector>
#include <optional>
#include <array>
#include <memory>
#include <nlohmann/json.hpp>
#include <fstream>
#include <stdexcept>

// Shared data structures
struct RepartitionInfo
{
    std::vector<size_t> global_dims;
    std::vector<size_t> local_start;
    // What was read: the owned points plus, on every piece but the last
    // along an axis, the neighbour's first plane on that axis, so that
    // neighbouring pieces share a plane of points and no cell is lost.
    std::vector<size_t> local_dims;
    // The owned points alone (local_dims without the shared planes).
    std::vector<size_t> owned_dims;
    // Per axis: true when the last plane of local_dims belongs to the next
    // piece (is shared), false at the global boundary.
    std::vector<bool> shared_high;
};
template <typename T>
struct BlockData
{
    std::vector<T> buffer;
    std::vector<size_t> start;
    std::vector<size_t> dims;
};

// Options struct
struct BackendOptions
{
    std::string adios_file;
    std::string adios_engine = "BP5";
    std::string u_var = "U";
    std::string v_var = "V";
    // Only "repartition" is implemented: every backend reads an even slab
    // per rank (ReadRepartition). "preserve" is rejected at startup (#42).
    std::string block_mode = "repartition";
    // How "repartition" divides the domain among the reader ranks:
    //   "slab"  -- even slabs along the slowest axis (the original layout);
    //   "brick" -- a 3D grid of ranks from MPI_Dims_create, axes ordered as
    //              the simulation orders its own, so each reader's brick is a
    //              whole number of writer blocks when the rank counts divide.
    // At 262144 writers and 2048 readers a slab spans at least 4096 writers
    // and a brick exactly 128.
    std::string read_decomposition = "slab";
    // The simulation's ADIOS2 XML (settings "adios_config"). The reader takes
    // its engine parameters from the <io name="AnalysisInput"> block there,
    // so settings such as ControlModule reach the reader as well as the
    // writer. Empty: no XML, built-in defaults only.
    std::string adios_config;
    std::optional<std::array<double, 3>> origin;
    std::optional<std::array<double, 3>> spacing;
    std::string sst_wait_mode = "block";
    double sst_timeout_seconds = 10.0;
    int adios_verbose = 0;
    bool debug = false;
    std::string catalyst_script_path;
    std::string catalyst_lib_path;
    std::string catalyst_output_file;
    std::string output_type;
    std::string adios_output_file = "staged_output.bp"; // adios_writer: output_file_name + ".bp"
    MPI_Comm comm = MPI_COMM_WORLD;
    // Seconds allowed for teardown once the reader has finished (#75).
    double teardown_timeout_s = 300.0;
    // How long the SST reader waits for the writer to appear. The simulation
    // may spend minutes reading a checkpoint first; ADIOS2's default is 60 s (#78).
    double sst_open_timeout_s = 600.0;

    static BackendOptions FromSettingsFile(const std::string &settings_path)
    {
        BackendOptions opts;
        nlohmann::json js;
        std::ifstream ifs(settings_path);
        if (!ifs.is_open())
            throw std::runtime_error("Cannot open settings file: " + settings_path);
        ifs >> js;

        if (js.contains("output_type"))
            opts.output_type = js["output_type"];
        if (js.contains("adios_engine"))
            opts.adios_engine = js["adios_engine"];
        if (js.contains("block_mode"))
            opts.block_mode = js["block_mode"];
        if (js.contains("read_decomposition"))
            opts.read_decomposition = js["read_decomposition"];
        if (js.contains("adios_config"))
            opts.adios_config = js["adios_config"];
        if (js.contains("sst_wait_mode"))
            opts.sst_wait_mode = js["sst_wait_mode"];
        if (js.contains("sst_timeout_seconds"))
            opts.sst_timeout_seconds = js["sst_timeout_seconds"];
        if (js.contains("adios_verbose"))
            opts.adios_verbose = js["adios_verbose"];
        if (js.contains("catalyst_script_path"))
            opts.catalyst_script_path = js["catalyst_script_path"];
        if (js.contains("catalyst_lib_path"))
            opts.catalyst_lib_path = js["catalyst_lib_path"];
        if (js.contains("output_file_name"))
        {
            opts.catalyst_output_file = js["output_file_name"];
            opts.adios_output_file = opts.catalyst_output_file + ".bp";
        }
        if (js.contains("teardown_timeout_s"))
            opts.teardown_timeout_s = js["teardown_timeout_s"];
        if (js.contains("sst_open_timeout_s"))
            opts.sst_open_timeout_s = js["sst_open_timeout_s"];

        return opts;
    }
};

// Abstract base class for all backends
class AnalysisBackend
{
public:
    virtual ~AnalysisBackend() = default;
    virtual void Run() = 0;
};

// Factory function declaration
std::unique_ptr<AnalysisBackend> CreateBackend(const std::string &name, const BackendOptions &opts);
