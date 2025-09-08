#pragma once
#include <chrono>
#include <fstream>
#include <map>
#include <string>
#include <vector>

class PerfLogger {
public:
    PerfLogger(const std::string &filename, int rank, const std::string &hostname,
               const std::vector<std::string> &timers);
    ~PerfLogger();

    void start(const std::string &name);
    void stop(const std::string &name);
    void logStep(int step);
    void resetTimer(const std::string &name);
    void finalize();

private:
    int rank_;
    std::string hostname_;
    std::ofstream log_;
    std::vector<std::string> header_names_;

#ifdef ENABLE_TIMERS
    std::map<std::string,std::chrono::high_resolution_clock::time_point> start_times_;
    std::map<std::string,double> accumulated_;
#endif
    std::string output_dir_ = "."; 
};
