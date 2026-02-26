#include "restart.h"
#include <stdexcept>
#include <vector>
#include <vtkLogger.h>

// Helper to get MPI Cartesian Coordinates
void GetCartInfo(MPI_Comm comm, int &px, int &py, int &pz, int &rx, int &ry, int &rz)
{
    int rank, nproc;
    MPI_Comm_rank(comm, &rank);
    MPI_Comm_size(comm, &nproc);
    
    int dims[3] = {0, 0, 0};
    int periods[3] = {0, 0, 0};
    int coords[3] = {0, 0, 0};
    
    // We assume the comm passed in is a Cartesian Communicator
    MPI_Cart_get(comm, 3, dims, periods, coords);
    
    px = dims[0]; py = dims[1]; pz = dims[2];
    rx = coords[0]; ry = coords[1]; rz = coords[2];
}

void WriteCkpt(MPI_Comm comm, const int step, const Settings &settings,
               const GrayScott &sim, adios2::IO &io)
{
    int rank;
    MPI_Comm_rank(comm, &rank);

    vtkLog(INFO, "Checkpointing at step " << step << " to file " << settings.checkpoint_output);

    try
    {
        adios2::Engine writer = io.Open(settings.checkpoint_output, adios2::Mode::Write);
        if (!writer) throw std::runtime_error("ADIOS2 engine could not be created.");

        // --- 1. Calculate Global Topology ---
        // We need to know WHERE this rank fits in the Global Grid
        int px, py, pz, rx, ry, rz;
        GetCartInfo(comm, px, py, pz, rx, ry, rz);

        // Global Dimensions (The full simulation size, e.g., 2048x2048x2048)
        // Note: Assuming uniform decomposition.
        // If your sim stores global L, use that. Here we derive it.
        const size_t GX = sim.size_x * px;
        const size_t GY = sim.size_y * py;
        const size_t GZ = sim.size_z * pz;

        // Local Dimensions (The interior size of THIS rank, without ghosts)
        const size_t LX = sim.size_x;
        const size_t LY = sim.size_y;
        const size_t LZ = sim.size_z;

        // Global Offsets (Where this rank starts in the global grid)
        const size_t OX = rx * LX;
        const size_t OY = ry * LY;
        const size_t OZ = rz * LZ;

        // --- 2. Define Global Array Variables ---
        // We define a 3D Global Array, NOT a 4D Rank Array
        auto var_u = io.InquireVariable<double>("U");
        auto var_v = io.InquireVariable<double>("V");
        auto var_step = io.InquireVariable<int>("step");

        if (!var_u)
        {
            // Define shape: {Global}, {Start}, {Count}
            var_u = io.DefineVariable<double>("U", {GX, GY, GZ}, {OX, OY, OZ}, {LX, LY, LZ});
        }
        if (!var_v)
        {
            var_v = io.DefineVariable<double>("V", {GX, GY, GZ}, {OX, OY, OZ}, {LX, LY, LZ});
        }
        if (!var_step)
        {
            var_step = io.DefineVariable<int>("step");
        }

        // --- 3. Handle Ghost Cells (Memory Selection) ---
        // The data in memory (sim.u_ghost) HAS ghost cells. The file should NOT.
        // We tell ADIOS: "The memory buffer is larger than what we are writing."
        
        // Memory Dimensions: (LX+2, LY+2, LZ+2)
        // Memory Start: (1, 1, 1) -> Skip the first ghost layer
        // Memory Count: (LX, LY, LZ) -> Write the interior
        var_u.SetMemorySelection({{1, 1, 1}, {LX, LY, LZ}});
        var_v.SetMemorySelection({{1, 1, 1}, {LX, LY, LZ}});
        
        // Note: We need to tell ADIOS the shape of the memory buffer too
        // assuming sim.u_ghost() is a flat vector of size (LX+2)*(LY+2)*(LZ+2)
        // We treat it as a 3D block in memory.
        
        writer.BeginStep();
        writer.Put(var_step, &step);
        
        // Put expects the pointer to the START of the vector, ADIOS handles the stride/skipping
        writer.Put(var_u, sim.u_ghost().data());
        writer.Put(var_v, sim.v_ghost().data());
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
    int rank;
    MPI_Comm_rank(comm, &rank);

    if (settings.restart_input.empty()) {
        MPI_Abort(comm, 1);
        return 0;
    }

    try
    {
        io.SetParameter("OpenTimeoutSecs", "5.0");
        adios2::Engine reader = io.Open(settings.restart_input, adios2::Mode::ReadRandomAccess);

        if (!reader) throw std::runtime_error("Could not open restart file.");

        auto var_step = io.InquireVariable<int>("step");
        auto var_u = io.InquireVariable<double>("U");
        auto var_v = io.InquireVariable<double>("V");

        if (!var_step || !var_u || !var_v) throw std::runtime_error("Missing variables.");

        // --- 1. Calculate New Topology ---
        // We calculate "Where am I NOW?"
        int px, py, pz, rx, ry, rz;
        GetCartInfo(comm, px, py, pz, rx, ry, rz);

        const size_t LX = sim.size_x;
        const size_t LY = sim.size_y;
        const size_t LZ = sim.size_z;

        const size_t OX = rx * LX;
        const size_t OY = ry * LY;
        const size_t OZ = rz * LZ;

        // --- 2. Select the Data Region ---
        // "Give me the data at offset (OX, OY, OZ) of size (LX, LY, LZ)"
        // ADIOS maps this request to the file, regardless of how it was written.
        var_u.SetSelection({{OX, OY, OZ}, {LX, LY, LZ}});
        var_v.SetSelection({{OX, OY, OZ}, {LX, LY, LZ}});

        // --- 3. Read into Ghosted Buffer ---
        // We read the INTERIOR data from file into the INTERIOR of our ghosted vector
        std::vector<double> u = sim.u_ghost(); // Pre-allocate with existing size (incl ghosts)
        std::vector<double> v = sim.v_ghost();

        var_u.SetMemorySelection({{1, 1, 1}, {LX, LY, LZ}});
        var_v.SetMemorySelection({{1, 1, 1}, {LX, LY, LZ}});

        reader.Get(var_step, step);
        reader.Get(var_u, u.data());
        reader.Get(var_v, v.data());
        reader.Close();

        // Update the simulation object
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
