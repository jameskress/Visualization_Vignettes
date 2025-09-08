#include "perf_logger.hpp"
#include <sys/resource.h>
#include <iostream>
#include <stdexcept>

PerfLogger::PerfLogger(const std::string &output_dir, int rank, const std::string &hostname,
                       const std::vector<std::string> &timers)
{
    rank_ = rank;
    hostname_ = hostname;
    header_names_ = timers;
    output_dir_ = output_dir;

#ifdef ENABLE_TIMERS
    for (auto &t : timers)
        accumulated_[t] = 0.0;
#endif

    // Build file path: output_dir/rank_<rank>.csv
    std::string file_path = output_dir_ + "/rank_" + std::to_string(rank_) + ".csv";

    // Optional: create directory if it doesn't exist (POSIX)
    system(("mkdir -p " + output_dir_).c_str());

    log_.open(file_path);
    if (!log_.is_open())
        throw std::runtime_error("Failed to open log file: " + file_path);

    // Write CSV header
    log_ << "step,rank,hostname,rss_MB,user_s,sys_s";
    for (auto &name : header_names_)
        log_ << "," << name;
    log_ << std::endl;
}

PerfLogger::~PerfLogger() { finalize(); }

void PerfLogger::start(const std::string &name)
{
#ifdef ENABLE_TIMERS
    start_times_[name] = std::chrono::high_resolution_clock::now();
#endif
}

void PerfLogger::stop(const std::string &name)
{
#ifdef ENABLE_TIMERS
    auto end = std::chrono::high_resolution_clock::now();
    double duration = std::chrono::duration<double>(end - start_times_[name]).count();
    accumulated_[name] += duration;
#endif
}

void PerfLogger::logStep(int step)
{
    struct rusage usage;
    getrusage(RUSAGE_SELF, &usage);
    double rss_MB = usage.ru_maxrss / 1024.0;
    double user_s = usage.ru_utime.tv_sec + usage.ru_utime.tv_usec / 1e6;
    double sys_s = usage.ru_stime.tv_sec + usage.ru_stime.tv_usec / 1e6;

    log_ << step << "," << rank_ << "," << hostname_ << "," << rss_MB << "," << user_s << "," << sys_s;

    for (auto &name : header_names_)
    {
#ifdef ENABLE_TIMERS
        log_ << "," << accumulated_[name];
        accumulated_[name] = 0.0;
#else
        log_ << ",0.0"; // timers disabled
#endif
    }
    log_ << std::endl;
}

void PerfLogger::resetTimer(const std::string &name)
{
#ifdef ENABLE_TIMERS
    accumulated_[name] = 0.0;
#endif
}

void PerfLogger::finalize()
{
    if (log_.is_open())
        log_.close();
}
