#include "perf_logger.hpp"

#include <sys/resource.h>

#include <algorithm>
#include <cstdio>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <stdexcept>

#include "simulation/json.hpp"

namespace fs = std::filesystem;

namespace
{
struct Usage
{
    double rss_MB, user_s, sys_s;
};

Usage usage_now()
{
    struct rusage u;
    getrusage(RUSAGE_SELF, &u);
    return {u.ru_maxrss / 1024.0, // ru_maxrss is the high-water mark, in KiB on Linux
            u.ru_utime.tv_sec + u.ru_utime.tv_usec / 1e6,
            u.ru_stime.tv_sec + u.ru_stime.tv_usec / 1e6};
}

bool mpi_usable()
{
    int init = 0, fin = 0;
    MPI_Initialized(&init);
    MPI_Finalized(&fin);
    return init && !fin;
}
} // namespace

PerfLogger::PerfLogger(const std::string &run_dir, int rank, const std::string &hostname,
                       const std::vector<std::string> &timers,
                       const std::vector<std::string> &counters, MPI_Comm comm)
    : rank_(rank), hostname_(hostname), run_dir_(run_dir), comm_(comm), timer_names_(timers),
      counter_names_(counters)
{
    for (size_t i = 0; i < timer_names_.size(); i++)
        timer_index_[timer_names_[i]] = static_cast<int>(i);
    for (size_t i = 0; i < counter_names_.size(); i++)
        counter_index_[counter_names_[i]] = static_cast<int>(i);
    acc_.assign(timer_names_.size(), 0.0);
    cur_counters_.assign(counter_names_.size(), 0.0);
    started_.resize(timer_names_.size());

    std::error_code ec;
    fs::create_directories(run_dir_, ec);
    if (ec)
        throw std::runtime_error("PerfLogger: cannot create " + run_dir_ + ": " + ec.message());
}

PerfLogger::~PerfLogger()
{
    // A logger that was never finalized still keeps its step records, but
    // only finalize() may use MPI (the destructor may run after MPI_Finalize).
    if (!finalized_)
        writeStepFile();
}

std::string PerfLogger::makeRunDir(const std::string &base, const std::string &label,
                                   MPI_Comm comm)
{
    int rank = 0;
    MPI_Comm_rank(comm, &rank);
    std::string dir;
    if (rank == 0)
    {
        char stamp[32];
        std::time_t now = std::time(nullptr);
        std::strftime(stamp, sizeof stamp, "%Y%m%d-%H%M%S", std::gmtime(&now));
        const std::string stem = base + "/" + stamp + "_" + label;
        dir = stem;
        for (int n = 2; fs::exists(dir); n++)
            dir = stem + "_" + std::to_string(n);
        fs::create_directories(dir);
    }
    int len = static_cast<int>(dir.size());
    MPI_Bcast(&len, 1, MPI_INT, 0, comm);
    dir.resize(len);
    MPI_Bcast(&dir[0], len, MPI_CHAR, 0, comm);
    return dir;
}

int PerfLogger::timerIndex(const std::string &name) const
{
    auto it = timer_index_.find(name);
    return it == timer_index_.end() ? -1 : it->second;
}

void PerfLogger::start(const std::string &name)
{
#ifdef ENABLE_TIMERS
    const int i = timerIndex(name);
    if (i >= 0)
        started_[i] = std::chrono::steady_clock::now();
#else
    (void)name;
#endif
}

void PerfLogger::stop(const std::string &name)
{
#ifdef ENABLE_TIMERS
    const auto end = std::chrono::steady_clock::now();
    const int i = timerIndex(name);
    if (i >= 0)
        acc_[i] += std::chrono::duration<double>(end - started_[i]).count();
#else
    (void)name;
#endif
}

void PerfLogger::add(const std::string &name, double seconds)
{
#ifdef ENABLE_TIMERS
    const int i = timerIndex(name);
    if (i >= 0)
        acc_[i] += seconds;
#else
    (void)name;
    (void)seconds;
#endif
}

double PerfLogger::elapsed(const std::string &name) const
{
    const int i = timerIndex(name);
    return i >= 0 ? acc_[i] : 0.0;
}

void PerfLogger::resetTimer(const std::string &name)
{
    const int i = timerIndex(name);
    if (i >= 0)
        acc_[i] = 0.0;
}

void PerfLogger::setCounter(const std::string &name, double value)
{
    auto it = counter_index_.find(name);
    if (it != counter_index_.end())
        cur_counters_[it->second] = value;
}

void PerfLogger::setStepPrint(const std::vector<std::pair<std::string, std::string>> &timer_labels)
{
    step_print_.clear();
    for (const auto &tl : timer_labels)
    {
        const int i = timerIndex(tl.first);
        if (i >= 0)
            step_print_.emplace_back(i, tl.second);
    }
}

void PerfLogger::logStep(int step)
{
#ifdef ENABLE_TIMERS
    const Usage u = usage_now();
    records_.push_back({step, u.rss_MB, u.user_s, u.sys_s, acc_, cur_counters_});

    if (!step_print_.empty() && comm_ != MPI_COMM_NULL)
    {
        std::vector<double> local(step_print_.size()), mx(step_print_.size());
        for (size_t k = 0; k < step_print_.size(); k++)
            local[k] = acc_[step_print_[k].first];
        MPI_Reduce(local.data(), mx.data(), static_cast<int>(local.size()), MPI_DOUBLE, MPI_MAX,
                   0, comm_);
        if (rank_ == 0)
        {
            std::string line = "[Step " + std::to_string(step) + "]";
            char buf[96];
            for (size_t k = 0; k < step_print_.size(); k++)
            {
                std::snprintf(buf, sizeof buf, "%s %s %.3f ms", k ? " |" : "",
                              step_print_[k].second.c_str(), mx[k] * 1e3);
                line += buf;
            }
            std::printf("%s\n", line.c_str());
        }
    }
#else
    (void)step;
#endif
    std::fill(acc_.begin(), acc_.end(), 0.0);
    std::fill(cur_counters_.begin(), cur_counters_.end(), 0.0);
}

void PerfLogger::writeMetadata(const std::string &meta_json)
{
    if (rank_ != 0)
        return;
    nlohmann::json meta = nlohmann::json::parse(meta_json, nullptr, false);
    if (meta.is_discarded() || !meta.is_object())
        meta = nlohmann::json::object();
    meta["schema_version"] = kSchemaVersion;
    meta["run_dir"] = run_dir_;
    meta["timers_enabled"] = timersEnabled();
    meta["timer_names"] = timer_names_;
    meta["counter_names"] = counter_names_;
    std::ofstream out(run_dir_ + "/metadata.json");
    out << meta.dump(2) << "\n";
}

void PerfLogger::setRunTotals(double loop_wall_s, int steps_run)
{
    loop_wall_s_ = loop_wall_s;
    steps_run_ = steps_run;
}

void PerfLogger::writeStepFile() const
{
    if (records_.empty())
        return;
    std::error_code ec;
    fs::create_directories(run_dir_ + "/steps", ec);
    char name[40];
    std::snprintf(name, sizeof name, "/steps/rank_%05d.jsonl", rank_);
    std::ofstream out(run_dir_ + name);
    for (const Record &r : records_)
    {
        nlohmann::json t = nlohmann::json::object(), c = nlohmann::json::object();
        for (size_t i = 0; i < timer_names_.size(); i++)
            t[timer_names_[i]] = r.t[i];
        for (size_t i = 0; i < counter_names_.size(); i++)
            c[counter_names_[i]] = r.c[i];
        nlohmann::json j = {{"step", r.step},     {"rank", rank_},     {"host", hostname_},
                            {"rss_MB", r.rss_MB}, {"user_s", r.user_s}, {"sys_s", r.sys_s},
                            {"t", t},             {"c", c}};
        out << j.dump() << "\n";
    }
}

void PerfLogger::finalize()
{
    if (finalized_)
        return;
    finalized_ = true;
    writeStepFile();

    if (comm_ == MPI_COMM_NULL || !mpi_usable())
        return;

    int procs = 1;
    MPI_Comm_size(comm_, &procs);

    // Per-rank totals over all steps, then min/sum/max across ranks.
    const size_t nt = timer_names_.size(), nc = counter_names_.size();
    std::vector<double> local(nt + nc + 1, 0.0);
    for (const Record &r : records_)
    {
        for (size_t i = 0; i < nt; i++)
            local[i] += r.t[i];
        for (size_t i = 0; i < nc; i++)
            local[nt + i] += r.c[i];
    }
    local[nt + nc] = usage_now().rss_MB;
    const int n = static_cast<int>(local.size());
    std::vector<double> mn(n), mx(n), sum(n);
    MPI_Reduce(local.data(), mn.data(), n, MPI_DOUBLE, MPI_MIN, 0, comm_);
    MPI_Reduce(local.data(), mx.data(), n, MPI_DOUBLE, MPI_MAX, 0, comm_);
    MPI_Reduce(local.data(), sum.data(), n, MPI_DOUBLE, MPI_SUM, 0, comm_);

    if (rank_ != 0)
        return;

    const int steps = static_cast<int>(records_.size());
    const int total_i = timerIndex("total_step");
    const double total_mean = total_i >= 0 ? sum[total_i] / procs : 0.0;
    const double per_step_ms = steps_run_ > 0 ? 1e3 * loop_wall_s_ / steps_run_ : 0.0;

    nlohmann::json s;
    s["schema_version"] = kSchemaVersion;
    s["ranks"] = procs;
    s["timers_enabled"] = timersEnabled();
    s["steps_run"] = steps_run_;
    s["loop_wall_s"] = loop_wall_s_;
    s["loop_wall_per_step_ms"] = per_step_ms;
    s["rss_high_water_MB"] = {{"min", mn[n - 1]}, {"mean", sum[n - 1] / procs}, {"max", mx[n - 1]}};

    if (timersEnabled())
    {
        // Imbalance: max/mean - 1 across ranks of the per-rank total.
        // Fraction: mean total over the mean total_step.
        nlohmann::json timers = nlohmann::json::object();
        for (size_t i = 0; i < nt; i++)
        {
            const double mean = sum[i] / procs;
            timers[timer_names_[i]] = {
                {"total_s", {{"min", mn[i]}, {"mean", mean}, {"max", mx[i]}}},
                {"per_step_ms_mean", steps > 0 ? 1e3 * mean / steps : 0.0},
                {"imbalance", mean > 0 ? mx[i] / mean - 1.0 : 0.0},
                {"fraction_of_step", total_mean > 0 ? mean / total_mean : 0.0}};
        }
        s["timers"] = timers;
        nlohmann::json counters = nlohmann::json::object();
        for (size_t i = 0; i < nc; i++)
            counters[counter_names_[i]] = {{"total_all_ranks", sum[nt + i]},
                                           {"per_rank_min", mn[nt + i]},
                                           {"per_rank_max", mx[nt + i]}};
        s["counters"] = counters;
    }

    std::ofstream out(run_dir_ + "/summary.json");
    out << s.dump(2) << "\n";

    if (timersEnabled())
    {
        std::printf("\n==== Performance summary: %d ranks, %d steps, loop %.3f s (%.3f ms/step)\n",
                    procs, steps, loop_wall_s_, per_step_ms);
        std::printf("%-18s %12s %12s %12s %10s %9s\n", "timer", "min s", "mean s", "max s",
                    "imbalance", "of step");
        for (size_t i = 0; i < nt; i++)
        {
            if (mx[i] == 0.0)
                continue;
            const double mean = sum[i] / procs;
            std::printf("%-18s %12.6f %12.6f %12.6f %9.1f%% %8.1f%%\n", timer_names_[i].c_str(),
                        mn[i], mean, mx[i], mean > 0 ? 100.0 * (mx[i] / mean - 1.0) : 0.0,
                        total_mean > 0 ? 100.0 * mean / total_mean : 0.0);
        }
        std::printf("rss high water: max %.1f MB per rank\n", mx[n - 1]);
        std::printf("run directory: %s\n\n", run_dir_.c_str());
    }
}
