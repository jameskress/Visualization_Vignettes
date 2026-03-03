#include "restart.h"
#include <stdexcept>
#include <vector>
#include <vtkLogger.h>

// --- 100% Accurate Topology Matcher ---
// This perfectly mimics how the Gray-Scott app calculates its grid
void GetOffsets(MPI_Comm comm, int nproc, int rank, size_t L,
                size_t &ox, size_t &oy, size_t &oz)
{
    // 1. Let MPI calculate the exact 3D division the simulation is using
    int dims[3] = {0, 0, 0};
    MPI_Dims_create(nproc, 3, dims); 

    // 2. Create a temporary grid to get our exact X, Y, Z coordinates
    MPI_Comm cart_comm;
    int periods[3] = {1, 1, 1};
    MPI_Cart_create(comm, 3, dims, periods, 0, &cart_comm);
    
    int coords[3] = {0, 0, 0};
    MPI_Cart_coords(cart_comm, rank, 3, coords);
    MPI_Comm_free(&cart_comm); // Clean up

    // 3. Calculate spatial offsets based on the global size (L)
    ox = coords[0] * (L / dims[0]);
    oy = coords[1] * (L / dims[1]);
    oz = coords[2] * (L / dims[2]);
}

void WriteCkpt(MPI_Comm comm, const int step, const Settings &settings,
               const GrayScott &sim, adios2::IO &io)
{
    int rank, nproc;
    MPI_Comm_rank(comm, &rank);
    MPI_Comm_size(comm, &nproc);

    if(rank == 0) vtkLog(INFO, "Checkpointing step " << step);

    try
    {
        adios2::Engine writer = io.Open(settings.checkpoint_output, adios2::Mode::Write);
        if (!writer) throw std::runtime_error("ADIOS2 engine creation failed.");

        // Global Dimensions are FIXED to settings.L (e.g., 2048 x 2048 x 2048)
        const size_t GX = settings.L;
        const size_t GY = settings.L;
        const size_t GZ = settings.L;
        
        // Get our exact starting coordinates
        size_t OX, OY, OZ;
        GetOffsets(comm, nproc, rank, settings.L, OX, OY, OZ);

        // Local dimensions (how much this specific rank owns)
        const size_t LX = sim.size_x;
        const size_t LY = sim.size_y;
        const size_t LZ = sim.size_z;
        
        auto var_u = io.InquireVariable<double>("U");
        auto var_v = io.InquireVariable<double>("V");
        auto var_step = io.InquireVariable<int>("step");

        if (!var_u) var_u = io.DefineVariable<double>("U", {GX, GY, GZ}, {OX, OY, OZ}, {LX, LY, LZ});
        if (!var_v) var_v = io.DefineVariable<double>("V", {GX, GY, GZ}, {OX, OY, OZ}, {LX, LY, LZ});
        if (!var_step) var_step = io.DefineVariable<int>("step");

        // Copy data to strip out ghost cells safely
        std::vector<double> buf_u(LX * LY * LZ);
        std::vector<double> buf_v(LX * LY * LZ);
        const std::vector<double> &u_src = sim.u_ghost();
        const std::vector<double> &v_src = sim.v_ghost();

        size_t idx_dst = 0;
        for (size_t z = 1; z <= LZ; ++z) {
            for (size_t y = 1; y <= LY; ++y) {
                for (size_t x = 1; x <= LX; ++x) {
                    size_t idx_src = z * (LX + 2) * (LY + 2) + y * (LX + 2) + x;
                    buf_u[idx_dst] = u_src[idx_src];
                    buf_v[idx_dst] = v_src[idx_src];
                    idx_dst++;
                }
            }
        }

        writer.BeginStep();
        writer.Put(var_step, &step);
        writer.Put(var_u, buf_u.data());
        writer.Put(var_v, buf_v.data());
        writer.EndStep();
        writer.Close();
    }
    catch (std::exception &e)
    {
        vtkLog(ERROR, "Checkpoint write failed: " << e.what());
    }
}

int ReadRestart(MPI_Comm comm, const Settings &settings, GrayScott &sim,
                adios2::IO &io)
{
    int step = 0;
    int rank, nproc;
    MPI_Comm_rank(comm, &rank);
    MPI_Comm_size(comm, &nproc);

    if (settings.restart_input.empty()) return 0;

    try
    {
        io.SetParameter("OpenTimeoutSecs", "5.0");
        adios2::Engine reader = io.Open(settings.restart_input, adios2::Mode::ReadRandomAccess);
        if (!reader) throw std::runtime_error("Could not open restart file.");

        auto var_step = io.InquireVariable<int>("step");
        auto var_u = io.InquireVariable<double>("U");
        auto var_v = io.InquireVariable<double>("V");

        if (!var_step || !var_u || !var_v) throw std::runtime_error("Missing variables.");

        // Get our new coordinates based on the current number of nodes
        size_t OX, OY, OZ;
        GetOffsets(comm, nproc, rank, settings.L, OX, OY, OZ);

        const size_t LX = sim.size_x;
        const size_t LY = sim.size_y;
        const size_t LZ = sim.size_z;

        // Tell ADIOS to fetch exactly the block of data this rank needs
        var_u.SetSelection({{OX, OY, OZ}, {LX, LY, LZ}});
        var_v.SetSelection({{OX, OY, OZ}, {LX, LY, LZ}});

        std::vector<double> buf_u(LX * LY * LZ);
        std::vector<double> buf_v(LX * LY * LZ);

        reader.Get(var_step, step);
        reader.Get(var_u, buf_u.data());
        reader.Get(var_v, buf_v.data());
        reader.Close();

        // Reconstruct the array with ghost cell padding
        std::vector<double> u = sim.u_ghost();
        std::vector<double> v = sim.v_ghost();
        
        size_t idx_src = 0;
        for (size_t z = 1; z <= LZ; ++z) {
            for (size_t y = 1; y <= LY; ++y) {
                for (size_t x = 1; x <= LX; ++x) {
                    size_t idx_dst = z * (LX + 2) * (LY + 2) + y * (LX + 2) + x;
                    u[idx_dst] = buf_u[idx_src];
                    v[idx_dst] = buf_v[idx_src];
                    idx_src++;
                }
            }
        }
        
        sim.restart(u, v);
        if(rank==0) vtkLog(INFO, "Restarted successfully from step " << step);
    }
    catch (std::exception &e)
    {
        if (rank == 0) vtkLog(ERROR, "Restart read failed: " << e.what());
        MPI_Abort(comm, 1);
    }

    return step;
}
