#include "restart.h"
#include <stdexcept>
#include <vector>
#include <cmath>
#include <algorithm> // For std::swap if needed
#include <vtkLogger.h>

// --- Helper: Crash-Proof Topology Calculation ---
void GetDecomposition(MPI_Comm comm, int nproc, int rank, 
                      int &px, int &py, int &pz, 
                      int &rx, int &ry, int &rz)
{
    int status;
    // 1. Check if the communicator even HAS a topology
    MPI_Topo_test(comm, &status);

    if (status == MPI_CART)
    {
        // Safe to call MPI_Cart_get
        int dims[3] = {0, 0, 0};
        int periods[3] = {0, 0, 0};
        int coords[3] = {0, 0, 0};
        MPI_Cart_get(comm, 3, dims, periods, coords);
        
        px = dims[0]; py = dims[1]; pz = dims[2];
        rx = coords[0]; ry = coords[1]; rz = coords[2];
    }
    else
    {
        // FALLBACK: Manual Calculation (The "Chicken and Egg" Fix)
        // We assume a standard block decomposition.
        
        // A. Factorize NPROC into px * py * pz (Targeting a cube)
        px = 1; py = 1; pz = 1;
        int temp = nproc;
        
        // Simple logic: maintain cubic aspect ratio
        while(temp > 1) {
            if (px <= py && px <= pz) { px *= 2; }
            else if (py <= px && py <= pz) { py *= 2; }
            else { pz *= 2; }
            temp /= 2;
        }

        // B. Calculate Rank Coordinates (Standard Row-Major mapping)
        // This assumes the simulation fills X first, then Y, then Z.
        // If your sim fills Z first, swap these! 
        // Standard for most Gray-Scott miniapps:
        // Rank = rx + ry*px + rz*px*py
        
        rx = rank % px;
        ry = (rank / px) % py;
        rz = rank / (px * py);
        
        // Sanity Check
        if (px * py * pz != nproc) {
            // If nproc isn't a power of 2, this simple loop fails. 
            // Fallback to 1D strip if complex math fails.
            px = nproc; py = 1; pz = 1;
            rx = rank; ry = 0; rz = 0;
        }
    }
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

        int px, py, pz, rx, ry, rz;
        GetDecomposition(comm, nproc, rank, px, py, pz, rx, ry, rz);

        const size_t LX = sim.size_x;
        const size_t LY = sim.size_y;
        const size_t LZ = sim.size_z;
        
        const size_t GX = LX * px;
        const size_t GY = LY * py;
        const size_t GZ = LZ * pz;
        const size_t OX = rx * LX;
        const size_t OY = ry * LY;
        const size_t OZ = rz * LZ;

        auto var_u = io.InquireVariable<double>("U");
        auto var_v = io.InquireVariable<double>("V");
        auto var_step = io.InquireVariable<int>("step");

        if (!var_u) var_u = io.DefineVariable<double>("U", {GX, GY, GZ}, {OX, OY, OZ}, {LX, LY, LZ});
        if (!var_v) var_v = io.DefineVariable<double>("V", {GX, GY, GZ}, {OX, OY, OZ}, {LX, LY, LZ});
        if (!var_step) var_step = io.DefineVariable<int>("step");

        // Copy to contiguous buffer (Strip Ghosts)
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

        // --- SAFE DECOMPOSITION ---
        int px, py, pz, rx, ry, rz;
        GetDecomposition(comm, nproc, rank, px, py, pz, rx, ry, rz);

        const size_t LX = sim.size_x;
        const size_t LY = sim.size_y;
        const size_t LZ = sim.size_z;
        const size_t OX = rx * LX;
        const size_t OY = ry * LY;
        const size_t OZ = rz * LZ;

        var_u.SetSelection({{OX, OY, OZ}, {LX, LY, LZ}});
        var_v.SetSelection({{OX, OY, OZ}, {LX, LY, LZ}});

        std::vector<double> buf_u(LX * LY * LZ);
        std::vector<double> buf_v(LX * LY * LZ);

        reader.Get(var_step, step);
        reader.Get(var_u, buf_u.data());
        reader.Get(var_v, buf_v.data());
        reader.Close();

        // Reconstruct Ghosts
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
        if(rank==0) vtkLog(INFO, "Restarted from step " << step);
    }
    catch (std::exception &e)
    {
        if (rank == 0) vtkLog(ERROR, "Restart read failed: " << e.what());
        MPI_Abort(comm, 1);
    }

    return step;
}
