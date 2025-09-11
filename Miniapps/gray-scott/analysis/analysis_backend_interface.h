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
    std::vector<size_t> local_dims;
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
    std::string block_mode = "preserve";
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
    MPI_Comm comm = MPI_COMM_WORLD;

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
            opts.catalyst_output_file = js["output_file_name"];

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