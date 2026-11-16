#include "run_metadata.hpp"
#include "run_metadata_string.hpp"

#include <sys/utsname.h>

#include <cctype>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <set>
#include <string>
#include <vector>

#include "gs_build_info.h"

namespace
{
std::string trim(const std::string &s)
{
    const auto b = s.find_first_not_of(" \t\r\n");
    const auto e = s.find_last_not_of(" \t\r\n");
    return b == std::string::npos ? "" : s.substr(b, e - b + 1);
}

// Value after "key ... :" on the first matching line of a /proc style file.
std::string field(const std::string &path, const std::string &key)
{
    std::ifstream in(path);
    std::string line;
    while (std::getline(in, line))
        if (line.compare(0, key.size(), key) == 0)
        {
            const auto colon = line.find(':');
            if (colon != std::string::npos)
                return trim(line.substr(colon + 1));
        }
    return "";
}

std::string cpu_model()
{
    std::string m = field("/proc/cpuinfo", "model name"); // x86
    if (m.empty())
    {
        // aarch64 has no model name in /proc/cpuinfo; the device tree or the
        // implementer/part pair is the best available.
        std::ifstream dt("/sys/firmware/devicetree/base/model");
        std::getline(dt, m);
        m = trim(m);
        if (m.empty())
        {
            const std::string impl = field("/proc/cpuinfo", "CPU implementer");
            const std::string part = field("/proc/cpuinfo", "CPU part");
            if (!impl.empty())
                m = "implementer " + impl + " part " + part;
        }
    }
    return m.empty() ? "unknown" : m;
}

int cpu_count()
{
    int n = 0;
    std::ifstream in("/proc/cpuinfo");
    std::string line;
    while (std::getline(in, line))
        if (line.compare(0, 9, "processor") == 0)
            n++;
    return n;
}

// NVIDIA GPUs from the driver's /proc files (no nvidia-smi subprocess).
std::vector<std::string> gpu_models()
{
    std::vector<std::string> out;
    const std::filesystem::path dir("/proc/driver/nvidia/gpus");
    std::error_code ec;
    if (!std::filesystem::is_directory(dir, ec))
        return out;
    for (const auto &e : std::filesystem::directory_iterator(dir, ec))
    {
        const std::string m = field((e.path() / "information").string(), "Model");
        if (!m.empty())
            out.push_back(m);
    }
    return out;
}

// First line of a small sysfs or /proc file, or "" if it cannot be read.
std::string first_line(const std::string &path)
{
    std::ifstream in(path);
    std::string line;
    std::getline(in, line);
    return trim(line);
}

// The node's platform, as the run saw it on rank 0's node: what could
// change between nodes or between run days and move the timings.
nlohmann::json platform()
{
    nlohmann::json p;
    struct utsname u;
    if (uname(&u) == 0)
        p["kernel"] = std::string(u.release) + " " + u.version;
    std::string os = field("/etc/os-release", "PRETTY_NAME");
    if (os.empty())
    {
        // os-release is key=value, not key: value
        std::ifstream in("/etc/os-release");
        std::string line;
        while (std::getline(in, line))
            if (line.compare(0, 12, "PRETTY_NAME=") == 0)
                os = line.substr(12);
    }
    if (os.size() >= 2 && os.front() == '"' && os.back() == '"')
        os = os.substr(1, os.size() - 2);
    p["os"] = os;
    const std::string cpu = "/sys/devices/system/cpu/cpu0/cpufreq/";
    p["cpu_freq_driver"] = first_line(cpu + "scaling_driver");
    p["cpu_governor"] = first_line(cpu + "scaling_governor");
    p["cpu_max_khz"] = first_line(cpu + "cpuinfo_max_freq");
    p["cpu_boost"] = first_line("/sys/devices/system/cpu/cpufreq/boost");
    int numa = 0;
    std::error_code ec;
    for (const auto &e : std::filesystem::directory_iterator("/sys/devices/system/node", ec))
    {
        const std::string n = e.path().filename().string();
        if (n.size() > 4 && n.compare(0, 4, "node") == 0 && std::isdigit(static_cast<unsigned char>(n[4])))
            numa++;
    }
    p["numa_nodes"] = numa;
    // "263748908 kB" -> 263748908
    const std::string mem = field("/proc/meminfo", "MemTotal");
    p["mem_total_kB"] = mem.empty() ? 0LL : std::atoll(mem.c_str());
    return p;
}

// The shared libraries this process loaded that decide its behaviour
// (MPI, libfabric, ADIOS2, the visualization stacks), by their real paths:
// an install directory names the exact build (for example ADIOS2's commit).
std::vector<std::string> key_libraries()
{
    static const char *keys[] = {"adios2", "mpi", "fabric", "ascent", "conduit", "catalyst",
                                 "vtk",    "viskores", "ospray", "kombyne", "darshan"};
    std::set<std::string> out;
    std::ifstream in("/proc/self/maps");
    std::string line;
    while (std::getline(in, line))
    {
        const auto slash = line.find('/');
        if (slash == std::string::npos)
            continue;
        const std::string path = line.substr(slash);
        const std::string name = std::filesystem::path(path).filename().string();
        if (name.find(".so") == std::string::npos)
            continue;
        for (const char *k : keys)
            if (name.find(k) != std::string::npos)
            {
                std::error_code e2;
                const auto real = std::filesystem::canonical(path, e2);
                out.insert(e2 ? path : real.string());
                break;
            }
    }
    return std::vector<std::string>(out.begin(), out.end());
}

std::string mpi_library_version()
{
    char buf[MPI_MAX_LIBRARY_VERSION_STRING];
    int len = 0;
    MPI_Get_library_version(buf, &len);
    (void)len;
    std::string s(buf); // len counts the terminating NUL in some MPIs
    const auto nl = s.find('\n');
    return trim(nl == std::string::npos ? s : s.substr(0, nl));
}
} // namespace

nlohmann::json collect_run_metadata(MPI_Comm comm)
{
    int rank = 0, procs = 1;
    MPI_Comm_rank(comm, &rank);
    MPI_Comm_size(comm, &procs);

    // Hostnames of all ranks, gathered as fixed-width records.
    char name[MPI_MAX_PROCESSOR_NAME] = {};
    int len = 0;
    MPI_Get_processor_name(name, &len);
    std::vector<char> all(rank == 0 ? static_cast<size_t>(procs) * MPI_MAX_PROCESSOR_NAME : 0);
    MPI_Gather(name, MPI_MAX_PROCESSOR_NAME, MPI_CHAR, all.data(), MPI_MAX_PROCESSOR_NAME,
               MPI_CHAR, 0, comm);

    nlohmann::json m;
    if (rank != 0)
        return m;

    std::set<std::string> hosts;
    for (int r = 0; r < procs; r++)
        hosts.insert(std::string(&all[static_cast<size_t>(r) * MPI_MAX_PROCESSOR_NAME]));

    char stamp[32];
    std::time_t now = std::time(nullptr);
    std::strftime(stamp, sizeof stamp, "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&now));

    m["start_time_utc"] = stamp;
    m["git"] = {{"commit", GS_GIT_COMMIT},
                {"describe", GS_GIT_DESCRIBE},
                {"dirty", GS_GIT_DIRTY == 1},
                {"is_checkout", GS_GIT_DIRTY >= 0}};
    m["build"] = {{"compiler", GS_CXX_COMPILER},
                  {"compiler_id", GS_CXX_COMPILER_ID},
                  {"compiler_version", GS_CXX_COMPILER_VERSION},
                  {"cxx_flags", GS_CXX_FLAGS},
                  {"build_type", GS_BUILD_TYPE},
                  {"enabled_backends", GS_ENABLED_BACKENDS}};
    m["host"] = {{"rank0_hostname", std::string(name)},
                 {"hostnames", std::vector<std::string>(hosts.begin(), hosts.end())},
                 {"nodes", hosts.size()},
                 {"cpu_model", cpu_model()},
                 {"cpus_on_rank0_node", cpu_count()},
                 {"gpu_models", gpu_models()},
                 {"platform", platform()}};
    m["libraries"] = key_libraries();
    m["mpi"] = {{"library_version", mpi_library_version()}, {"ranks", procs}};
    return m;
}

std::string collect_run_metadata_string(MPI_Comm comm)
{
    return collect_run_metadata(comm).dump(-1, ' ', false, nlohmann::json::error_handler_t::replace);
}
