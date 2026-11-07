// The solver is based on Hiroshi Watanabe's 2D Gray-Scott reaction diffusion
// code available at:
// https://github.com/kaityo256/sevendayshpc/tree/master/day5

#include "gray-scott.h"

#include <mpi.h>
#include <stdexcept> // runtime_error
#include <chrono>
#include <initializer_list>
#include <iostream>
#include <vector>

GrayScott::GrayScott(const Settings &settings, MPI_Comm comm)
    : settings(settings), comm(comm)
{
}

GrayScott::~GrayScott()
{
    // Fallback only: main() frees these before MPI_Finalize. After finalize,
    // MPI calls are not allowed, so check first.
    int finalized = 0;
    MPI_Finalized(&finalized);
    if (!finalized)
    {
        free_mpi_resources();
    }
}

void GrayScott::free_mpi_resources()
{
    for (MPI_Datatype *t : {&xy_face_type, &xz_face_type, &yz_face_type})
    {
        if (*t != MPI_DATATYPE_NULL)
        {
            MPI_Type_free(t);
        }
    }
    if (cart_comm != MPI_COMM_NULL)
    {
        MPI_Comm_free(&cart_comm);
    }
}

void GrayScott::init()
{
    init_mpi();
    init_field();
}

void GrayScott::iterate()
{
#ifdef ENABLE_TIMERS
    const auto t0 = std::chrono::steady_clock::now();
#endif
    // Perform halo exchange on the current, valid u and v arrays.
    exchange(u, v);
#ifdef ENABLE_TIMERS
    const auto t1 = std::chrono::steady_clock::now();
#endif
    calc(u, v, u2, v2);

    // Copy the results back to u and v.
    // This is done to avoid issues with 0 values in the ghost cells when restarting the sim
    // u.swap(u2);
    // v.swap(v2);
    for (int z = 1; z < size_z + 1; z++)
    {
        for (int y = 1; y < size_y + 1; y++)
        {
            for (int x = 1; x < size_x + 1; x++)
            {
                const int i = l2i(x, y, z);
                u[i] = u2[i];
                v[i] = v2[i];
            }
        }
    }
#ifdef ENABLE_TIMERS
    const auto t2 = std::chrono::steady_clock::now();
    last_halo_s_ = std::chrono::duration<double>(t1 - t0).count();
    last_stencil_s_ = std::chrono::duration<double>(t2 - t1).count();
#endif
    ++step_;
}

#ifdef USE_ADIOS2
void GrayScott::restart(std::vector<double> &u_in, std::vector<double> &v_in)
{
    auto expected_len = (size_x + 2) * (size_y + 2) * (size_z + 2);
    if (u_in.size() == expected_len && v_in.size() == expected_len)
    {
        u = u_in;
        v = v_in;
    }
    else
    {
        throw std::runtime_error(
            "Restart with incompatible array size, expected " +
            std::to_string(expected_len) + " got " +
            std::to_string(u_in.size()) + " elements");
    }
}
#endif

const std::vector<double> &GrayScott::u_ghost() const { return u; }

const std::vector<double> &GrayScott::v_ghost() const { return v; }

std::vector<double> GrayScott::u_noghost() const { return data_noghost(u); }

std::vector<double> GrayScott::v_noghost() const { return data_noghost(v); }

void GrayScott::u_noghost(double *u_no_ghost) const
{
    data_noghost(u, u_no_ghost);
}

void GrayScott::v_noghost(double *v_no_ghost) const
{
    data_noghost(v, v_no_ghost);
}

std::vector<unsigned char>
GrayScott::ghost_point_mask() const
{
    std::vector<unsigned char> buf((size_x + 2) * (size_y + 2) * (size_z + 2), 1);
    // set non ghosts
    for (int z = 1; z < size_z + 1; z++)
    {
        for (int y = 1; y < size_y + 1; y++)
        {
            for (int x = 1; x < size_x + 1; x++)
            {
                buf[(x) + (y) * (size_x + 2) +
                    (z) * (size_x + 2) * (size_y + 2)] = 0;
            }
        }
    }

    /*       for (int z = 1; z < size_z + 1; z++)
       {
           for (int y = 1; y < size_y + 1; y++)
           {
               for (int x = 1; x < size_x + 1; x++)
               {
                   data_no_ghost[(x - 1) + (y - 1) * size_x +
                                 (z - 1) * size_x * size_y] = data[l2i(x, y, z)];
               }
           }
       }*/

    return buf;
}

std::vector<unsigned char>
GrayScott::ghost_cell_mask() const
{
    std::vector<unsigned char> buf((size_x + 1) * (size_y + 1) * (size_z + 1), 1);
    // set non ghosts
    for (int z = 1; z < size_z; z++)
    {
        for (int y = 1; y < size_y; y++)
        {
            for (int x = 1; x < size_x; x++)
            {
                buf[(x) + (y) * (size_x + 1) +
                    (z) * (size_x + 1) * (size_y + 1)] = 0;
            }
        }
    }

    /*       for (int z = 1; z < size_z + 1; z++)
       {
           for (int y = 1; y < size_y + 1; y++)
           {
               for (int x = 1; x < size_x + 1; x++)
               {
                   data_no_ghost[(x - 1) + (y - 1) * size_x +
                                 (z - 1) * size_x * size_y] = data[l2i(x, y, z)];
               }
           }
       }*/

    return buf;
}

std::vector<double>
GrayScott::data_noghost(const std::vector<double> &data) const
{
    std::vector<double> buf(size_x * size_y * size_z);
    data_no_ghost_common(data, buf.data());
    return buf;
}

void GrayScott::data_noghost(const std::vector<double> &data,
                             double *data_no_ghost) const
{
    data_no_ghost_common(data, data_no_ghost);
}

void GrayScott::init_field()
{
    const int V = (size_x + 2) * (size_y + 2) * (size_z + 2);
    u.resize(V, 1.0);
    v.resize(V, 0.0);
    u2.resize(V, 0.0);
    v2.resize(V, 0.0);

    const int d = 6;
    for (int z = settings.L / 2 - d; z < settings.L / 2 + d; z++)
    {
        for (int y = settings.L / 2 - d; y < settings.L / 2 + d; y++)
        {
            for (int x = settings.L / 2 - d; x < settings.L / 2 + d; x++)
            {
                if (!is_inside(x, y, z))
                    continue;
                int i = g2i(x, y, z);
                u[i] = 0.25;
                v[i] = 0.33;
            }
        }
    }
}

double GrayScott::calcU(double tu, double tv) const
{
    return -tu * tv * tv + settings.F * (1.0 - tu);
}

double GrayScott::calcV(double tu, double tv) const
{
    return tu * tv * tv - (settings.F + settings.k) * tv;
}

namespace
{
// SplitMix64 (Steele, Lea and Flood 2014): a fast, well-mixed 64-bit hash.
inline std::uint64_t splitmix64(std::uint64_t x)
{
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}
} // namespace

double GrayScott::noise_at(std::uint64_t gx, std::uint64_t gy, std::uint64_t gz) const
{
    // Counter-based: the value depends only on the seed, the step and the global
    // index, never on the rank or on how many values were drawn before it.
    const std::uint64_t L = settings.L;
    const std::uint64_t index = (gz * L + gy) * L + gx;
    std::uint64_t h = splitmix64(settings.seed ^ splitmix64(step_));
    h = splitmix64(h ^ index);
    // 53 random bits to a double in [0, 1), then to [-1, 1).
    return static_cast<double>(h >> 11) * (1.0 / 9007199254740992.0) * 2.0 - 1.0;
}

double GrayScott::laplacian(int x, int y, int z,
                            const std::vector<double> &s) const
{
    double ts = 0.0;
    ts += s[l2i(x - 1, y, z)];
    ts += s[l2i(x + 1, y, z)];
    ts += s[l2i(x, y - 1, z)];
    ts += s[l2i(x, y + 1, z)];
    ts += s[l2i(x, y, z - 1)];
    ts += s[l2i(x, y, z + 1)];
    ts += -6.0 * s[l2i(x, y, z)];

    return ts / 6.0;
}

void GrayScott::calc(const std::vector<double> &u, const std::vector<double> &v,
                     std::vector<double> &u2, std::vector<double> &v2)
{
    for (int z = 1; z < size_z + 1; z++)
    {
        for (int y = 1; y < size_y + 1; y++)
        {
            for (int x = 1; x < size_x + 1; x++)
            {
                const int i = l2i(x, y, z);
                double du = 0.0;
                double dv = 0.0;
                du = settings.Du * laplacian(x, y, z, u);
                dv = settings.Dv * laplacian(x, y, z, v);
                du += calcU(u[i], v[i]);
                dv += calcV(u[i], v[i]);
                if (settings.noise != 0.0)
                {
                    du += settings.noise * noise_at(offset_x + x - 1, offset_y + y - 1,
                                                    offset_z + z - 1);
                }
                u2[i] = u[i] + du * settings.dt;
                v2[i] = v[i] + dv * settings.dt;
            }
        }
    }
}

void GrayScott::init_mpi()
{
    int dims[3] = {};
    const int periods[3] = {1, 1, 1};
    int coords[3] = {};

    MPI_Comm_rank(comm, &rank);
    MPI_Comm_size(comm, &procs);

    MPI_Dims_create(procs, 3, dims);
    npx = dims[0];
    npy = dims[1];
    npz = dims[2];

    MPI_Cart_create(comm, 3, dims, periods, 0, &cart_comm);
    MPI_Cart_coords(cart_comm, rank, 3, coords);
    px = coords[0];
    py = coords[1];
    pz = coords[2];

    // Every rank must own at least one point per axis: with L smaller than the
    // number of ranks along an axis, some blocks would be empty and the halo
    // exchange would send halo values instead of interior ones.
    if (settings.L < npx || settings.L < npy || settings.L < npz)
    {
        if (rank == 0)
        {
            std::cerr << "Error: L = " << settings.L << " is smaller than the rank grid "
                      << npx << " x " << npy << " x " << npz
                      << "; every rank needs at least one point per axis." << std::endl;
        }
        MPI_Abort(comm, 1);
    }

    size_x = settings.L / npx;
    size_y = settings.L / npy;
    size_z = settings.L / npz;

    if (px < settings.L % npx)
    {
        size_x++;
    }
    if (py < settings.L % npy)
    {
        size_y++;
    }
    if (pz < settings.L % npz)
    {
        size_z++;
    }

    offset_x = (settings.L / npx * px) + std::min(settings.L % npx, px);
    offset_y = (settings.L / npy * py) + std::min(settings.L % npy, py);
    offset_z = (settings.L / npz * pz) + std::min(settings.L % npz, pz);

    MPI_Cart_shift(cart_comm, 0, 1, &west, &east);
    MPI_Cart_shift(cart_comm, 1, 1, &down, &up);
    MPI_Cart_shift(cart_comm, 2, 1, &south, &north);

    // XY faces: size_x * (size_y + 2)
    MPI_Type_vector(size_y + 2, size_x, size_x + 2, MPI_DOUBLE, &xy_face_type);
    MPI_Type_commit(&xy_face_type);

    // XZ faces: size_x * size_z
    MPI_Type_vector(size_z, size_x, (size_x + 2) * (size_y + 2), MPI_DOUBLE,
                    &xz_face_type);
    MPI_Type_commit(&xz_face_type);

    // YZ faces: (size_y + 2) * (size_z + 2)
    MPI_Type_vector((size_y + 2) * (size_z + 2), 1, size_x + 2, MPI_DOUBLE,
                    &yz_face_type);
    MPI_Type_commit(&yz_face_type);

    // Each exchange sends every face type in both directions, for u and v.
    int xy = 0, xz = 0, yz = 0;
    MPI_Type_size(xy_face_type, &xy);
    MPI_Type_size(xz_face_type, &xz);
    MPI_Type_size(yz_face_type, &yz);
    halo_bytes_ = 2ull * 2ull * (static_cast<std::uint64_t>(xy) + xz + yz);
}

void GrayScott::exchange_xy(std::vector<double> &local_data) const
{
    MPI_Status st;

    // Send XY face z=size_z to north and receive z=0 from south
    MPI_Sendrecv(&local_data[l2i(1, 0, size_z)], 1, xy_face_type, north, 1,
                 &local_data[l2i(1, 0, 0)], 1, xy_face_type, south, 1,
                 cart_comm, &st);
    // Send XY face z=1 to south and receive z=size_z+1 from north
    MPI_Sendrecv(&local_data[l2i(1, 0, 1)], 1, xy_face_type, south, 1,
                 &local_data[l2i(1, 0, size_z + 1)], 1, xy_face_type, north, 1,
                 cart_comm, &st);
}

void GrayScott::exchange_xz(std::vector<double> &local_data) const
{
    MPI_Status st;

    // Send XZ face y=size_y to up and receive y=0 from down
    MPI_Sendrecv(&local_data[l2i(1, size_y, 1)], 1, xz_face_type, up, 2,
                 &local_data[l2i(1, 0, 1)], 1, xz_face_type, down, 2, cart_comm,
                 &st);
    // Send XZ face y=1 to down and receive y=size_y+1 from up
    MPI_Sendrecv(&local_data[l2i(1, 1, 1)], 1, xz_face_type, down, 2,
                 &local_data[l2i(1, size_y + 1, 1)], 1, xz_face_type, up, 2,
                 cart_comm, &st);
}

void GrayScott::exchange_yz(std::vector<double> &local_data) const
{
    MPI_Status st;

    // Send YZ face x=size_x to east and receive x=0 from west
    MPI_Sendrecv(&local_data[l2i(size_x, 0, 0)], 1, yz_face_type, east, 3,
                 &local_data[l2i(0, 0, 0)], 1, yz_face_type, west, 3, cart_comm,
                 &st);
    // Send YZ face x=1 to west and receive x=size_x+1 from east
    MPI_Sendrecv(&local_data[l2i(1, 0, 0)], 1, yz_face_type, west, 3,
                 &local_data[l2i(size_x + 1, 0, 0)], 1, yz_face_type, east, 3,
                 cart_comm, &st);
}

void GrayScott::exchange(std::vector<double> &u, std::vector<double> &v) const
{
    // Order matters for the edges and corners of the halo. xz faces carry no
    // halo rows; xy faces carry the y halo rows that xz just filled; yz faces
    // carry the whole padded plane, so after all three the edges and corners
    // hold this step's values. The 7-point stencil never reads them, but any
    // wider stencil or a writer that outputs the halo would (#12).
    exchange_xz(u);
    exchange_xy(u);
    exchange_yz(u);

    exchange_xz(v);
    exchange_xy(v);
    exchange_yz(v);
}

void GrayScott::data_no_ghost_common(const std::vector<double> &data,
                                     double *data_no_ghost) const
{
    for (int z = 1; z < size_z + 1; z++)
    {
        for (int y = 1; y < size_y + 1; y++)
        {
            for (int x = 1; x < size_x + 1; x++)
            {
                data_no_ghost[(x - 1) + (y - 1) * size_x +
                              (z - 1) * size_x * size_y] = data[l2i(x, y, z)];
            }
        }
    }
}
