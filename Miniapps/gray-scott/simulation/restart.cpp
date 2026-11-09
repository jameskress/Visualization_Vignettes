#include "restart.h"

#include <cstdint>
#include <stdexcept>
#include <vector>
#include <vtkLogger.h>

// --- Accurate Topology Matcher ---
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

        // Global Dimensions are FIXED to settings.L
        const size_t GX = settings.L;
        const size_t GY = settings.L;
        const size_t GZ = settings.L;
        
        // This rank's block starts at the simulation's own offsets, which include
        // the remainder when L does not divide by the rank count (#12).
        const size_t OX = sim.offset_x, OY = sim.offset_y, OZ = sim.offset_z;

        // Local dimensions (how much this specific rank owns)
        const size_t LX = sim.size_x;
        const size_t LY = sim.size_y;
        const size_t LZ = sim.size_z;
        
        auto var_u = io.InquireVariable<double>("U");
        auto var_v = io.InquireVariable<double>("V");
        auto var_step = io.InquireVariable<int>("step");

        // ADIOS2 uses C-order (Row-Major). The slowest moving dimension in our loops is Z.
        if (!var_u) var_u = io.DefineVariable<double>("U", {GZ, GY, GX}, {OZ, OY, OX}, {LZ, LY, LX});
        if (!var_v) var_v = io.DefineVariable<double>("V", {GZ, GY, GX}, {OZ, OY, OX}, {LZ, LY, LX});
        if (!var_step) var_step = io.DefineVariable<int>("step");

        // --- ADD METADATA ATTRIBUTES ---
        if (!io.InquireAttribute<size_t>("L")) {
            io.DefineAttribute<size_t>("L", settings.L);
            io.DefineAttribute<double>("F", settings.F);
            io.DefineAttribute<double>("k", settings.k);
            io.DefineAttribute<double>("dt", settings.dt);
            io.DefineAttribute<double>("Du", settings.Du);
            io.DefineAttribute<double>("Dv", settings.Dv);
            io.DefineAttribute<double>("noise", settings.noise);
            // The noise at each step depends on the seed; a restart with a
            // different seed diverges from the uninterrupted run.
            io.DefineAttribute<std::uint64_t>("seed", settings.seed);
        }

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

        // --- VALIDATE METADATA ---
        auto attr_L = io.InquireAttribute<size_t>("L");
        if (attr_L && attr_L.Data()[0] != settings.L) {
            throw std::runtime_error("FATAL: Grid size mismatch! File L=" + 
                                     std::to_string(attr_L.Data()[0]) + 
                                     ", Settings L=" + std::to_string(settings.L));
        }

        if (rank == 0) {
            auto attr_F = io.InquireAttribute<double>("F");
            auto attr_k = io.InquireAttribute<double>("k");
            auto attr_dt = io.InquireAttribute<double>("dt");
            
            if (attr_F && attr_F.Data()[0] != settings.F) {
                vtkLog(WARNING, "Physics mismatch: File F=" << attr_F.Data()[0] << ", Settings F=" << settings.F);
            }
            if (attr_k && attr_k.Data()[0] != settings.k) {
                vtkLog(WARNING, "Physics mismatch: File k=" << attr_k.Data()[0] << ", Settings k=" << settings.k);
            }
            if (attr_dt && attr_dt.Data()[0] != settings.dt) {
                vtkLog(WARNING, "Physics mismatch: File dt=" << attr_dt.Data()[0] << ", Settings dt=" << settings.dt);
            }
            // Allowed (a deliberate change), but the run will no longer match
            // an uninterrupted one, so say so.
            auto attr_seed = io.InquireAttribute<std::uint64_t>("seed");
            // With noise off the seed is unused, so a different one changes nothing.
            if (settings.noise != 0.0 && attr_seed && attr_seed.Data()[0] != settings.seed) {
                vtkLog(WARNING, "Noise seed mismatch: File seed=" << attr_seed.Data()[0] << ", Settings seed=" << settings.seed
                                << "; the restarted run will not match an uninterrupted one");
            }
            else if (!attr_seed && settings.noise != 0.0) {
                vtkLog(WARNING, "Checkpoint records no noise seed (written before seeds were stored); "
                                "cannot check that seed " << settings.seed << " matches");
            }
        }
        // --- END METADATA VALIDATION ---

        // This rank's block starts at the simulation's own offsets, which include
        // the remainder when L does not divide by the rank count (#12).
        const size_t OX = sim.offset_x, OY = sim.offset_y, OZ = sim.offset_z;

        const size_t LX = sim.size_x;
        const size_t LY = sim.size_y;
        const size_t LZ = sim.size_z;

        // Match the Row-Major {Z, Y, X} order used during write
        var_u.SetSelection({{OZ, OY, OX}, {LZ, LY, LX}});
        var_v.SetSelection({{OZ, OY, OX}, {LZ, LY, LX}});

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
        // Every rank that fails says so: rank 0 may not be one of them (#78).
        vtkLog(ERROR, "Restart read failed on rank " << rank << ": " << e.what());
        MPI_Abort(comm, 1);
    }

    return step;
}
