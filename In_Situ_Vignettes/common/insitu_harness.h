//
// Visualization Vignettes -- In Situ Vignettes
//
// insitu_harness.h
//
// Minimal, dependency-light support code shared by every in situ vignette.
//
// Design rules this harness enforces (each one exists because the miniapp
// audit found a real defect of that class):
//
//   1. Every check is COLLECTIVE. A rank that fails a check must not return
//      early on its own -- in situ APIs (catalyst_execute, ascent::execute,
//      vtkXMLPWriter::Write) are collective, and a lone early return
//      deadlocks the job. check_all() reduces across the communicator so
//      every rank takes the same branch.
//
//   2. Failures are LOUD. No silent `catch (...) {}`. A vignette that cannot
//      do its job exits non-zero so CTest and the batch script notice.
//
//   3. Memory growth is MEASURED, not assumed. rss_kb() lets a vignette
//      assert that a "zero-copy" path really is zero-copy.
//
#ifndef INSITU_HARNESS_H
#define INSITU_HARNESS_H

#include <mpi.h>

#include <cstdio>
#include <string>
#include <vector>

namespace insitu
{

// ---------------------------------------------------------------------------
// Resident set size in KiB, or 0 if it cannot be determined on this platform.
// Linux reports VmRSS in /proc/self/status; macOS has no equivalent cheap
// read, so vignettes must treat 0 as "unavailable" and skip RSS assertions.
// ---------------------------------------------------------------------------
inline long rss_kb()
{
    std::FILE *f = std::fopen("/proc/self/status", "r");
    if (!f)
        return 0;

    char line[256];
    long kb = 0;
    while (std::fgets(line, sizeof(line), f))
    {
        if (std::sscanf(line, "VmRSS: %ld kB", &kb) == 1)
            break;
    }
    std::fclose(f);
    return kb;
}

// ---------------------------------------------------------------------------
// A ghosted scalar block laid out exactly like GrayScott's u/v arrays:
// (nx+2) * (ny+2) * (nz+2) doubles, one ghost layer on every face.
//
// Index arithmetic is done in size_t, not int. The miniapp does it in int
// (gray-scott.h l2i) and silently overflows past ~1290^3 local points.
// ---------------------------------------------------------------------------
struct GhostedBlock
{
    size_t nx = 0, ny = 0, nz = 0;          // interior extent
    size_t ox = 0, oy = 0, oz = 0;          // global offset of the interior
    std::vector<double> u;
    std::vector<double> v;

    GhostedBlock(size_t nx_, size_t ny_, size_t nz_,
                 size_t ox_ = 0, size_t oy_ = 0, size_t oz_ = 0)
        : nx(nx_), ny(ny_), nz(nz_), ox(ox_), oy(oy_), oz(oz_),
          u(padded_size(), 1.0), v(padded_size(), 0.0)
    {
    }

    size_t padded_size() const { return (nx + 2) * (ny + 2) * (nz + 2); }
    size_t interior_size() const { return nx * ny * nz; }

    // Padded (ghosted) linear index.
    size_t idx(size_t x, size_t y, size_t z) const
    {
        return x + y * (nx + 2) + z * (nx + 2) * (ny + 2);
    }

    // Fill the interior with a reproducible, step-dependent pattern so a
    // downstream renderer produces a stable image and a checksum is
    // meaningful.
    void seed(int step)
    {
        for (size_t z = 1; z <= nz; ++z)
            for (size_t y = 1; y <= ny; ++y)
                for (size_t x = 1; x <= nx; ++x)
                {
                    const size_t i = idx(x, y, z);
                    const double gx = static_cast<double>(ox + x - 1);
                    const double gy = static_cast<double>(oy + y - 1);
                    const double gz = static_cast<double>(oz + z - 1);
                    u[i] = 0.5 + 0.5 * ((gx + gy + gz + step) / 64.0);
                    v[i] = 1.0 - u[i];
                }
    }

    double checksum() const
    {
        double s = 0.0;
        for (size_t z = 1; z <= nz; ++z)
            for (size_t y = 1; y <= ny; ++y)
                for (size_t x = 1; x <= nx; ++x)
                    s += u[idx(x, y, z)];
        return s;
    }
};

// ---------------------------------------------------------------------------
// Collective assertion. Every rank must call it with its own local verdict;
// the returned verdict is the AND across the communicator, so all ranks
// agree on whether to continue. Rank 0 prints the one-line result.
// ---------------------------------------------------------------------------
class Checks
{
public:
    Checks(MPI_Comm comm, const std::string &vignette)
        : m_comm(comm), m_vignette(vignette)
    {
        MPI_Comm_rank(m_comm, &m_rank);
        MPI_Comm_size(m_comm, &m_size);
        if (m_rank == 0)
            std::printf("\n=== %s (%d rank%s) ===\n",
                        m_vignette.c_str(), m_size, m_size == 1 ? "" : "s");
    }

    bool check_all(const std::string &name, bool local_ok, const std::string &detail = "")
    {
        int ok = local_ok ? 1 : 0;
        int all_ok = 0;
        MPI_Allreduce(&ok, &all_ok, 1, MPI_INT, MPI_MIN, m_comm);

        // Report the lowest-numbered failing rank so the log names a culprit.
        int culprit = local_ok ? m_size : m_rank;
        int first_bad = m_size;
        MPI_Allreduce(&culprit, &first_bad, 1, MPI_INT, MPI_MIN, m_comm);

        if (m_rank == 0)
        {
            std::printf("  [%s] %-42s", all_ok ? "PASS" : "FAIL", name.c_str());
            if (!all_ok)
                std::printf("  (first failing rank: %d)", first_bad);
            if (!detail.empty())
                std::printf("  %s", detail.c_str());
            std::printf("\n");
            std::fflush(stdout);
        }

        if (!all_ok)
            ++m_failures;
        return all_ok != 0;
    }

    // Returns the process exit code. Identical on every rank by construction.
    int finish() const
    {
        if (m_rank == 0)
        {
            if (m_failures == 0)
                std::printf("=== %s: ALL CHECKS PASSED ===\n\n", m_vignette.c_str());
            else
                std::printf("=== %s: %d CHECK(S) FAILED ===\n\n",
                            m_vignette.c_str(), m_failures);
            std::fflush(stdout);
        }
        return m_failures == 0 ? 0 : 1;
    }

    int rank() const { return m_rank; }
    int size() const { return m_size; }

private:
    MPI_Comm m_comm;
    std::string m_vignette;
    int m_rank = 0;
    int m_size = 1;
    int m_failures = 0;
};

} // namespace insitu

#endif // INSITU_HARNESS_H
