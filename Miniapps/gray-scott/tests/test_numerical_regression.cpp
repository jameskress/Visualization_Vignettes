// Numerical regression test for the Gray-Scott simulation core.
//
// Runs the solver on a fixed problem (64^3, 500 steps, fixed seed, noise on)
// and checks three things:
//
//  1. Budget. Diffusion sums to zero on the periodic domain and the reaction
//     terms u*v^2 cancel between U and V, so each step
//         sum(U+V)_new - sum(U+V)_old = dt * sum[F(1-U) - (F+k)V + noise*r]
//     over the owned points, up to rounding. A halo, stencil or
//     decomposition bug breaks this on the step it happens.
//  2. Norms. Global L2 and L-infinity norms of U and V at the end match the
//     stored golden values within a relative tolerance (default 1e-12; the
//     L2 sums are MPI reductions, so their order depends on the rank count).
//  3. Bitwise equivalence. The final U and V, gathered into global order,
//     are hashed and the hash is written to --hash-out. CTest runs this on
//     1, 2 and 4 ranks and a separate test checks the three hashes are equal.
//
// Usage:
//   test_numerical_regression --golden=<file> [--hash-out=<file>]
//                             [--rtol=1e-12] [--bless]
// --bless rewrites the golden file from this run instead of checking it.

#include <algorithm>
#include <cinttypes>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <limits>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include <mpi.h>

#include "gray-scott.h"
#include "settings.h"

namespace
{

// The fixed problem. Matches configs/miniapp-settings/settings-none.json
// except for the step count.
Settings regression_settings()
{
    Settings s;
    s.L = 64;
    s.steps = 500;
    s.plotgap = 500;
    s.Du = 0.2;
    s.Dv = 0.1;
    s.F = 0.01;
    s.k = 0.05;
    s.dt = 2.0;
    s.noise = 1e-7;
    s.seed = 20261107;
    s.output_type = "none";
    return s;
}

// Neumaier compensated sum, so the budget residual measures the solver's
// rounding and not the error of adding 262144 terms.
struct CompensatedSum
{
    double sum = 0.0, c = 0.0;
    void add(double x)
    {
        const double t = sum + x;
        c += std::fabs(sum) >= std::fabs(x) ? (sum - t) + x : (x - t) + sum;
        sum = t;
    }
    double value() const { return sum + c; }
};

// Exposes the owned-point sums the budget check needs.
class Probe : public GrayScott
{
public:
    using GrayScott::GrayScott;

    struct Sums
    {
        double source = 0.0; // sum[F(1-U) - (F+k)V]
        double noise = 0.0;  // sum r at the current step
        double scale = 0.0;  // sum(|U|+|V|), for the tolerance
    };

    // Record the sources for the step about to run and keep a copy of U, V.
    Sums before_step()
    {
        u_old = u;
        v_old = v;
        CompensatedSum src, nz, sc;
        for (size_t z = 1; z < size_z + 1; z++)
            for (size_t y = 1; y < size_y + 1; y++)
                for (size_t x = 1; x < size_x + 1; x++)
                {
                    const int i = l2i(x, y, z);
                    src.add(settings.F * (1.0 - u[i]) - (settings.F + settings.k) * v[i]);
                    sc.add(std::fabs(u[i]) + std::fabs(v[i]));
                    if (settings.noise != 0.0)
                        nz.add(noise_at(offset_x + x - 1, offset_y + y - 1, offset_z + z - 1));
                }
        return {src.value(), nz.value(), sc.value()};
    }

    // sum[(U+V)_new - (U+V)_old] over the owned points.
    double change() const
    {
        CompensatedSum d;
        for (size_t z = 1; z < size_z + 1; z++)
            for (size_t y = 1; y < size_y + 1; y++)
                for (size_t x = 1; x < size_x + 1; x++)
                {
                    const int i = l2i(x, y, z);
                    d.add((u[i] - u_old[i]) + (v[i] - v_old[i]));
                }
        return d.value();
    }

private:
    std::vector<double> u_old, v_old;
};

struct Norms
{
    double u_l2, u_linf, v_l2, v_linf;
};

Norms global_norms(const GrayScott &sim, MPI_Comm comm)
{
    const std::vector<double> u = sim.u_noghost();
    const std::vector<double> v = sim.v_noghost();
    double local[2] = {0.0, 0.0}, local_max[2] = {0.0, 0.0};
    for (double a : u)
    {
        local[0] += a * a;
        local_max[0] = std::max(local_max[0], std::fabs(a));
    }
    for (double a : v)
    {
        local[1] += a * a;
        local_max[1] = std::max(local_max[1], std::fabs(a));
    }
    double sum[2], mx[2];
    MPI_Allreduce(local, sum, 2, MPI_DOUBLE, MPI_SUM, comm);
    MPI_Allreduce(local_max, mx, 2, MPI_DOUBLE, MPI_MAX, comm);
    return {std::sqrt(sum[0]), mx[0], std::sqrt(sum[1]), mx[1]};
}

// Gather the owned points of one field into global x-fastest order on rank 0.
std::vector<double> gather_global(const GrayScott &sim, const std::vector<double> &local,
                                  size_t L, MPI_Comm comm)
{
    int rank, procs;
    MPI_Comm_rank(comm, &rank);
    MPI_Comm_size(comm, &procs);

    unsigned long long box[6] = {sim.offset_x, sim.offset_y, sim.offset_z,
                                 sim.size_x,   sim.size_y,   sim.size_z};
    std::vector<unsigned long long> boxes(rank == 0 ? 6 * procs : 0);
    MPI_Gather(box, 6, MPI_UNSIGNED_LONG_LONG, boxes.data(), 6, MPI_UNSIGNED_LONG_LONG, 0,
               comm);

    int n = static_cast<int>(local.size());
    std::vector<int> counts(rank == 0 ? procs : 0), displs(rank == 0 ? procs : 0);
    MPI_Gather(&n, 1, MPI_INT, counts.data(), 1, MPI_INT, 0, comm);
    std::vector<double> packed;
    if (rank == 0)
    {
        int total = 0;
        for (int r = 0; r < procs; r++)
        {
            displs[r] = total;
            total += counts[r];
        }
        packed.resize(total);
    }
    MPI_Gatherv(local.data(), n, MPI_DOUBLE, packed.data(), counts.data(), displs.data(),
                MPI_DOUBLE, 0, comm);

    std::vector<double> global;
    if (rank == 0)
    {
        global.assign(L * L * L, std::numeric_limits<double>::quiet_NaN());
        for (int r = 0; r < procs; r++)
        {
            const unsigned long long *b = &boxes[6 * r];
            size_t k = displs[r];
            for (size_t z = 0; z < b[5]; z++)
                for (size_t y = 0; y < b[4]; y++)
                    for (size_t x = 0; x < b[3]; x++)
                        global[(b[0] + x) + (b[1] + y) * L + (b[2] + z) * L * L] = packed[k++];
        }
    }
    return global;
}

// FNV-1a over the raw bytes: equal hashes mean bitwise-equal fields.
std::uint64_t fnv1a64(const std::vector<double> &a, std::uint64_t h = 0xcbf29ce484222325ULL)
{
    const unsigned char *p = reinterpret_cast<const unsigned char *>(a.data());
    for (size_t i = 0; i < a.size() * sizeof(double); i++)
    {
        h ^= p[i];
        h *= 0x100000001b3ULL;
    }
    return h;
}

std::map<std::string, double> read_golden(const std::string &path)
{
    std::map<std::string, double> m;
    std::ifstream in(path);
    std::string line;
    while (std::getline(in, line))
    {
        if (line.empty() || line[0] == '#')
            continue;
        std::istringstream ss(line);
        std::string key;
        double value;
        if (ss >> key >> value)
            m[key] = value;
    }
    return m;
}

bool arg_value(const char *arg, const char *name, std::string &out)
{
    const size_t n = std::strlen(name);
    if (std::strncmp(arg, name, n) == 0)
    {
        out = arg + n;
        return true;
    }
    return false;
}

} // namespace

int main(int argc, char **argv)
{
    MPI_Init(&argc, &argv);
    int rank, procs;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &procs);

    std::string golden, hash_out, rtol_s;
    bool bless = false;
    for (int i = 1; i < argc; i++)
    {
        if (arg_value(argv[i], "--golden=", golden) || arg_value(argv[i], "--hash-out=", hash_out) ||
            arg_value(argv[i], "--rtol=", rtol_s))
            continue;
        if (std::strcmp(argv[i], "--bless") == 0)
        {
            bless = true;
            continue;
        }
        if (rank == 0)
            std::fprintf(stderr, "unknown argument: %s\n", argv[i]);
        MPI_Abort(MPI_COMM_WORLD, 2);
    }
    if (golden.empty())
    {
        if (rank == 0)
            std::fprintf(stderr, "--golden=<file> is required\n");
        MPI_Abort(MPI_COMM_WORLD, 2);
    }
    const double rtol = rtol_s.empty() ? 1e-12 : std::stod(rtol_s);

    const Settings settings = regression_settings();
    int failures = 0;
    double worst_budget = 0.0; // largest |residual| / tolerance over all steps
    {
        Probe sim(settings, MPI_COMM_WORLD);
        sim.init();

        // Budget tolerance per step: 16 ulps of sum(|U|+|V|), about 1e-9 here.
        // The README's Testing section gives the observed margin.
        const double eps = std::numeric_limits<double>::epsilon();

        for (int step = 0; step < settings.steps; step++)
        {
            const Probe::Sums before = sim.before_step();
            sim.iterate();

            double local[4] = {sim.change(), before.source, before.noise, before.scale};
            double g[4];
            MPI_Allreduce(local, g, 4, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);

            const double change = g[0];
            const double expected = settings.dt * (g[1] + settings.noise * g[2]);
            const double residual = std::fabs(change - expected);
            const double tol = 16.0 * eps * g[3];
            worst_budget = std::max(worst_budget, residual / tol);
            if (residual > tol)
            {
                if (rank == 0 && failures < 10)
                    std::printf("FAIL budget step %d: change %.17g expected %.17g "
                                "residual %.3g > tol %.3g\n",
                                step, change, expected, residual, tol);
                failures++;
            }
        }

        const Norms n = global_norms(sim, MPI_COMM_WORLD);
        const std::vector<double> gu = gather_global(sim, sim.u_noghost(), settings.L, MPI_COMM_WORLD);
        const std::vector<double> gv = gather_global(sim, sim.v_noghost(), settings.L, MPI_COMM_WORLD);

        if (rank == 0)
        {
            std::printf("ranks %d (%zu x %zu x %zu), L %zu, steps %d, seed %" PRIu64 "\n", procs,
                        sim.npx, sim.npy, sim.npz, settings.L, settings.steps, settings.seed);
            std::printf("budget: worst residual is %.3g of the tolerance\n", worst_budget);

            const std::uint64_t h = fnv1a64(gv, fnv1a64(gu));
            std::printf("fields_fnv1a64 %016" PRIx64 "\n", h);
            if (!hash_out.empty())
            {
                std::ofstream out(hash_out);
                char buf[32];
                std::snprintf(buf, sizeof buf, "%016" PRIx64, h);
                out << buf << "\n";
                out.close();
                // A missing or stale hash file would let the rank comparison
                // pass on old data, so a failed write fails the test.
                if (!out)
                {
                    std::printf("FAIL could not write %s\n", hash_out.c_str());
                    failures++;
                }
            }

            const std::pair<const char *, double> got[] = {
                {"u_l2", n.u_l2}, {"u_linf", n.u_linf}, {"v_l2", n.v_l2}, {"v_linf", n.v_linf}};

            if (bless)
            {
                std::ofstream out(golden);
                out << "# Golden norms for tests/test_numerical_regression.cpp\n"
                    << "# L 64, 500 steps, Du 0.2, Dv 0.1, F 0.01, k 0.05, dt 2.0,\n"
                    << "# noise 1e-7, seed 20261107. Regenerate with --bless only when\n"
                    << "# a change to the numerics is intended, and say why in the PR.\n";
                char buf[64];
                for (const auto &kv : got)
                {
                    std::snprintf(buf, sizeof buf, "%s %.17g\n", kv.first, kv.second);
                    out << buf;
                }
                out.close();
                if (out)
                {
                    std::printf("wrote %s\n", golden.c_str());
                }
                else
                {
                    std::printf("FAIL could not write %s\n", golden.c_str());
                    failures++;
                }
            }
            else
            {
                const auto ref = read_golden(golden);
                for (const auto &kv : got)
                {
                    auto it = ref.find(kv.first);
                    if (it == ref.end())
                    {
                        std::printf("FAIL %s missing from %s\n", kv.first, golden.c_str());
                        failures++;
                        continue;
                    }
                    const double rel = std::fabs(kv.second - it->second) /
                                       std::max(std::fabs(it->second), 1e-300);
                    const bool ok = rel <= rtol;
                    std::printf("%s %s %.17g golden %.17g rel %.3g\n", ok ? "ok  " : "FAIL",
                                kv.first, kv.second, it->second, rel);
                    if (!ok)
                        failures++;
                }
            }
        }
        sim.free_mpi_resources();
    }

    MPI_Allreduce(MPI_IN_PLACE, &failures, 1, MPI_INT, MPI_SUM, MPI_COMM_WORLD);
    if (rank == 0)
        std::printf("%s\n", failures == 0 ? "PASSED" : "FAILED");
    MPI_Finalize();
    return failures == 0 ? 0 : 1;
}
