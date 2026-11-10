#pragma once
//
// PerfLogger: the structured performance record of one run (#26).
//
// A run directory holds
//   metadata.json            what ran, where, built how (rank 0)
//   steps/rank_NNNNN.jsonl   one JSON object per step per rank (timers on only)
//   summary.json             per-timer min/mean/max/imbalance across ranks,
//                            fractions of the step, loop wall time (rank 0)
//
// Timers are compiled in only with ENABLE_TIMERS. Without it start/stop/add
// cost nothing, no step records are kept, and only metadata.json and
// summary.json (wall time) are written. The format is a contract for the
// analysis script and for papers: bump kSchemaVersion on any change to it,
// and describe the change in README.md (Performance).
//
// Step records are buffered in memory and written in finalize(), so the
// step loop does no file I/O. finalize() is collective over the logger's
// communicator and must run before MPI_Finalize.

#include <chrono>
#include <cstdint>
#include <map>
#include <string>
#include <utility>
#include <vector>

#include <mpi.h>

class PerfLogger
{
public:
    // 2: allocation counters (#25) added to step and summary records.
    // 2: allocation counters (#25). 3: metadata problem.restart_read_s (#78)
    // and backend.overwrite_last_step, the setting in effect (#85).
    static constexpr int kSchemaVersion = 3;

    // run_dir: directory for this run's files (created if missing).
    // timers: per-step timer names, in record order.
    // counters: per-step counter names (bytes moved and the like).
    // comm: communicator for the summary and the step print. MPI_COMM_NULL
    //       writes the per-rank step files only (no collectives).
    PerfLogger(const std::string &run_dir, int rank, const std::string &hostname,
               const std::vector<std::string> &timers,
               const std::vector<std::string> &counters = {}, MPI_Comm comm = MPI_COMM_NULL);
    ~PerfLogger();

    PerfLogger(const PerfLogger &) = delete;
    PerfLogger &operator=(const PerfLogger &) = delete;

    static constexpr bool timersEnabled()
    {
#ifdef ENABLE_TIMERS
        return true;
#else
        return false;
#endif
    }

    // Create <base>/<UTC yyyymmdd-HHMMSS>_<label> on rank 0 (suffix _2, _3,
    // ... if taken) and return its path on every rank of comm.
    static std::string makeRunDir(const std::string &base, const std::string &label,
                                  MPI_Comm comm);

    void start(const std::string &name);
    void stop(const std::string &name);
    // Add a duration measured elsewhere (seconds) to this step's timer.
    void add(const std::string &name, double seconds);
    // This step's accumulated time for a timer (seconds; 0 with timers off).
    double elapsed(const std::string &name) const;
    void resetTimer(const std::string &name);
    // Set this step's value of a counter.
    void setCounter(const std::string &name, double value);

    // Timers rank 0 prints each step as "[Step N] Label X ms | ...", using
    // the maximum over ranks. Only with timers on and a communicator.
    void setStepPrint(const std::vector<std::pair<std::string, std::string>> &timer_labels);

    // Close the current step: buffer its record and zero the timers.
    void logStep(int step);

    // Rank 0 writes metadata.json from a JSON object given as text, adding
    // schema_version, run_dir and the timer and counter names. (Text, not a
    // json object, keeps nlohmann out of this header: the analysis reader
    // uses its own copy of the library.)
    void writeMetadata(const std::string &meta_json);
    // Wall time of the step loop and the number of steps it ran.
    void setRunTotals(double loop_wall_s, int steps_run);

    // Write step files and summary.json; rank 0 prints the summary when
    // timers are on. Collective over comm. Idempotent.
    void finalize();

    const std::string &runDir() const { return run_dir_; }

private:
    struct Record
    {
        int step;
        double rss_MB;
        double user_s;
        double sys_s;
        std::vector<double> t;
        std::vector<double> c;
    };

    int timerIndex(const std::string &name) const;
    void writeStepFile() const;

    int rank_;
    std::string hostname_;
    std::string run_dir_;
    MPI_Comm comm_;
    std::vector<std::string> timer_names_;
    std::vector<std::string> counter_names_;
    std::map<std::string, int> timer_index_;
    std::map<std::string, int> counter_index_;
    std::vector<std::pair<int, std::string>> step_print_;
    std::vector<double> acc_;
    std::vector<double> cur_counters_;
    std::vector<std::chrono::steady_clock::time_point> started_;
    std::vector<Record> records_;
    double loop_wall_s_ = 0.0;
    int steps_run_ = 0;
    bool finalized_ = false;
};
