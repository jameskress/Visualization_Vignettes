// Exact-value test of AdiosReader::ReadRepartition: every point of every
// reader's buffer, shared planes included, must hold the value the writer
// put there. The first <writers> ranks write a BP5 file in a 3D block
// decomposition (as the simulation splits its domain); after they close it,
// the other ranks read it back with the given decomposition and way of
// getting the shared planes.
//
//   mpiexec -n <writers + readers> test_reader_planes <writers> <slab|brick> <exchange|read> <file>
#include "analysis/adios_reader.h"
#include "analysis/analysis_backend_interface.h"
#include <adios2.h>
#include <mpi.h>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace
{
// An awkward shape: no axis divides evenly by the rank counts used.
constexpr size_t Z = 37, Y = 29, X = 23;
constexpr int kSteps = 2;

double value(size_t z, size_t y, size_t x, int step, int field)
{
    const double g = static_cast<double>((z * Y + y) * X + x) + 1e6 * step;
    return field == 0 ? g : -g;
}

void split(size_t n, int p, int c, size_t &start, size_t &count)
{
    const size_t base = n / p, rem = n % p;
    start = c * base + std::min<size_t>(c, rem);
    count = base + (static_cast<size_t>(c) < rem ? 1 : 0);
}

void write_file(MPI_Comm comm, const std::string &file)
{
    int rank, size;
    MPI_Comm_rank(comm, &rank);
    MPI_Comm_size(comm, &size);
    int dims[3] = {0, 0, 0};
    MPI_Dims_create(size, 3, dims); // dims[0] along x, the fastest axis
    const int cx = rank % dims[0], cy = (rank / dims[0]) % dims[1], cz = rank / (dims[0] * dims[1]);
    size_t sz, kz, sy, ky, sx, kx;
    split(Z, dims[2], cz, sz, kz);
    split(Y, dims[1], cy, sy, ky);
    split(X, dims[0], cx, sx, kx);
    adios2::ADIOS adios(comm);
    adios2::IO io = adios.DeclareIO("TestWriter");
    io.SetEngine("BP5");
    auto u = io.DefineVariable<double>("U", {Z, Y, X}, {sz, sy, sx}, {kz, ky, kx});
    auto v = io.DefineVariable<double>("V", {Z, Y, X}, {sz, sy, sx}, {kz, ky, kx});
    adios2::Engine engine = io.Open(file, adios2::Mode::Write);
    std::vector<double> bu(kz * ky * kx), bv(bu.size());
    for (int s = 0; s < kSteps; ++s)
    {
        for (size_t k = 0; k < kz; ++k)
            for (size_t j = 0; j < ky; ++j)
                for (size_t i = 0; i < kx; ++i)
                {
                    bu[(k * ky + j) * kx + i] = value(sz + k, sy + j, sx + i, s, 0);
                    bv[(k * ky + j) * kx + i] = value(sz + k, sy + j, sx + i, s, 1);
                }
        engine.BeginStep();
        engine.Put(u, bu.data());
        engine.Put(v, bv.data());
        engine.EndStep();
    }
    engine.Close();
}

long read_file(MPI_Comm comm, const std::string &file, const std::string &decomposition, const std::string &planes,
               const std::string &timer_dir, int &steps)
{
    int rank;
    MPI_Comm_rank(comm, &rank);
    BackendOptions opts;
    opts.adios_file = file;
    opts.adios_engine = "BP5";
    opts.read_decomposition = decomposition;
    opts.reader_shared_planes = planes;
    opts.comm = comm;
    PerfLogger logger(timer_dir, rank, "test", {"ADIOS_EndStep", "Halo_Exchange"});
    AdiosReader reader(opts, logger);
    long bad = 0;
    std::vector<double> bu, bv;
    steps = 0;
    while (reader.NextStep())
    {
        RepartitionInfo iu, iv;
        reader.ReadRepartition("U", bu, iu);
        reader.ReadRepartition("V", bv, iv);
        reader.EndStep();
        const int s = static_cast<int>(reader.CurrentStep());
        const auto &st = iu.local_start, &n = iu.local_dims;
        const size_t nz = n.empty() ? 0 : n[0], ny = nz ? n[1] : 0, nx = nz ? n[2] : 0;
        for (size_t k = 0; k < nz; ++k)
            for (size_t j = 0; j < ny; ++j)
                for (size_t i = 0; i < nx; ++i)
                {
                    const size_t at = (k * ny + j) * nx + i;
                    if (bu[at] != value(st[0] + k, st[1] + j, st[2] + i, s, 0) ||
                        bv[at] != value(st[0] + k, st[1] + j, st[2] + i, s, 1))
                    {
                        if (bad < 3)
                            std::fprintf(stderr, "reader %d step %d: wrong value at (%zu, %zu, %zu) of its buffer\n",
                                         rank, s, k, j, i);
                        ++bad;
                    }
                }
        ++steps;
    }
    return bad;
}
} // namespace

int main(int argc, char **argv)
{
    MPI_Init(&argc, &argv);
    if (argc != 5)
    {
        std::fprintf(stderr, "usage: test_reader_planes <writers> <slab|brick> <exchange|read> <file>\n");
        MPI_Abort(MPI_COMM_WORLD, 2);
    }
    const int writers = std::atoi(argv[1]);
    const std::string file = argv[4];
    int world_rank, world_size;
    MPI_Comm_rank(MPI_COMM_WORLD, &world_rank);
    MPI_Comm_size(MPI_COMM_WORLD, &world_size);
    if (writers < 1 || writers >= world_size)
    {
        std::fprintf(stderr, "need at least one writer and one reader rank\n");
        MPI_Abort(MPI_COMM_WORLD, 2);
    }
    const bool is_writer = world_rank < writers;
    MPI_Comm comm;
    MPI_Comm_split(MPI_COMM_WORLD, is_writer ? 0 : 1, world_rank, &comm);
    if (is_writer)
        write_file(comm, file);
    MPI_Barrier(MPI_COMM_WORLD); // the file is complete before anyone reads it
    long bad = 0;
    int steps = kSteps;
    if (!is_writer)
        bad = read_file(comm, file, argv[2], argv[3], file + ".timers", steps);
    long total = 0;
    MPI_Allreduce(&bad, &total, 1, MPI_LONG, MPI_SUM, MPI_COMM_WORLD);
    int min_steps = 0;
    MPI_Allreduce(&steps, &min_steps, 1, MPI_INT, MPI_MIN, MPI_COMM_WORLD);
    if (world_rank == writers)
        std::printf("%s %s, %d readers: %d steps, %ld wrong values\n", argv[2], argv[3], world_size - writers,
                    min_steps, total);
    MPI_Comm_free(&comm);
    MPI_Finalize();
    return (total == 0 && min_steps == kSteps) ? 0 : 1;
}
