#ifndef GS_TEARDOWN_GUARD_HPP
#define GS_TEARDOWN_GUARD_HPP

// Bounded teardown (#75).
//
// In transit runs can finish every step, write every output and the
// performance log, and then never exit: ADIOS2 SST's RDMA data plane can
// hang in its writer teardown (libfabric fi_close spinning on a lock), and
// every other rank then waits in MPI_Finalize. Nothing in SST bounds that.
//
// Arm a TeardownGuard once everything that matters is written, just before
// closing the output and calling MPI_Finalize. If the guard is still armed
// after `seconds`, it logs why and ends the process with status 0: the
// results are on disk, so a stuck shutdown must not cost the job its
// remaining allocation. seconds <= 0 disables it.

#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <string>
#include <thread>

class TeardownGuard
{
public:
    TeardownGuard(double seconds, int rank, std::string who) : who_(std::move(who)), rank_(rank)
    {
        if (seconds <= 0.0)
            return;
        armed_ = true;
        watcher_ = std::thread([this, seconds] {
            std::unique_lock<std::mutex> lock(mutex_);
            const bool disarmed = cv_.wait_for(lock, std::chrono::duration<double>(seconds),
                                               [this] { return !armed_; });
            if (!disarmed)
            {
                std::fprintf(stderr,
                             "[%s rank %d] teardown did not finish within %.0f s (output close or "
                             "MPI_Finalize is stuck); every output and the performance log are "
                             "already written, so exiting now (#75)\n",
                             who_.c_str(), rank_, seconds);
                std::fflush(stderr);
                std::fflush(stdout);
                std::_Exit(0);
            }
        });
    }

    TeardownGuard(const TeardownGuard &) = delete;
    TeardownGuard &operator=(const TeardownGuard &) = delete;

    // Teardown finished in time.
    void disarm()
    {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            armed_ = false;
        }
        cv_.notify_all();
        if (watcher_.joinable())
            watcher_.join();
    }

    ~TeardownGuard() { disarm(); }

private:
    std::string who_;
    int rank_;
    bool armed_ = false;
    std::mutex mutex_;
    std::condition_variable cv_;
    std::thread watcher_;
};

#endif
