#include "restart.h"

#include <stdexcept> 
#include <vtkLogger.h> 

/**
 * @brief Writes a checkpoint file using ADIOS2.
 */
void WriteCkpt(MPI_Comm comm, const int step, const Settings &settings,
               const GrayScott &sim, adios2::IO io)
{
    int rank, nproc;
    MPI_Comm_rank(comm, &rank);
    MPI_Comm_size(comm, &nproc);

    vtkLog(INFO, "Checkpointing at step " << step << " to file "
                << settings.checkpoint_output);

    try
    {
        adios2::Engine writer =
            io.Open(settings.checkpoint_output, adios2::Mode::Write);

        if (!writer)
        {
            throw std::runtime_error("ADIOS2 engine could not be created.");
        }

        // Define variables for checkpointing. This can be done on every call;
        // ADIOS2 is smart enough to only write the metadata once.
        const size_t X = sim.size_x + 2;
        const size_t Y = sim.size_y + 2;
        const size_t Z = sim.size_z + 2;
        const size_t R = static_cast<size_t>(rank);
        const size_t N = static_cast<size_t>(nproc);

        auto var_u = io.DefineVariable<double>("U", {N, X, Y, Z}, {R, 0, 0, 0},
                                            {1, X, Y, Z});
        auto var_v = io.DefineVariable<double>("V", {N, X, Y, Z}, {R, 0, 0, 0},
                                            {1, X, Y, Z});
        auto var_step = io.DefineVariable<int>("step");

        writer.BeginStep();
        writer.Put(var_step, &step);
        writer.Put(var_u, sim.u_ghost().data());
        writer.Put(var_v, sim.v_ghost().data());
        writer.EndStep();

        writer.Close();
    }
    catch (std::exception &e)
    {
        // For a write failure, we log an error but do not abort the simulation,
        // as the simulation can often continue without a successful checkpoint.
        vtkLog(ERROR, "Could not write checkpoint file '"
                    << settings.checkpoint_output << "'. Reason: " << e.what());
    }
}

/**
 * @brief Reads a restart file using ADIOS2.
 *
 * This function handles errors gracefully. If the restart file does not exist
 * or is invalid, it logs a ERROR error via vtkLog and aborts the MPI job.
 */
int ReadRestart(MPI_Comm comm, const Settings &settings, GrayScott &sim,
                adios2::IO io)
{
    int step = 0;
    int rank;
    MPI_Comm_rank(comm, &rank);

    if (settings.restart_input.empty())
    {
        vtkLogF(ERROR,
                "Restart is enabled, but no 'restart_input' file was "
                "specified in the settings.");
        MPI_Abort(comm, 1);
    }

    vtkLog(INFO, "Attempting to restart from file: " << settings.restart_input);

    try
    {
        io.SetParameter("OpenTimeoutSecs", "5.0");
        adios2::Engine reader =
            io.Open(settings.restart_input, adios2::Mode::ReadRandomAccess);

        if (!reader)
        {
            throw std::runtime_error("ADIOS2 engine could not be opened. "
                                     "File may not exist or is inaccessible.");
        }

        adios2::Variable<int> var_step = io.InquireVariable<int>("step");
        adios2::Variable<double> var_u = io.InquireVariable<double>("U");
        adios2::Variable<double> var_v = io.InquireVariable<double>("V");

        if (!var_step || !var_u || !var_v)
        {
            throw std::runtime_error(
                "One or more required variables (step, U, V) not found in "
                "the checkpoint file.");
        }

        const size_t X = sim.size_x + 2;
        const size_t Y = sim.size_y + 2;
        const size_t Z = sim.size_z + 2;
        const size_t R = static_cast<size_t>(rank);
        
        std::vector<double> u, v;
        u.reserve(X * Y * Z);
        v.reserve(X * Y * Z);

        var_u.SetSelection({{R, 0, 0, 0}, {1, X, Y, Z}});
        var_v.SetSelection({{R, 0, 0, 0}, {1, X, Y, Z}});

        reader.Get(var_step, step);
        reader.Get(var_u, u);
        reader.Get(var_v, v);
        
        reader.Close();

        vtkLog(INFO, "Successfully read checkpoint. Restarting from step " << step);
        sim.restart(u, v);
    }
    catch (std::exception &e)
    {
        // On failure, log a single ERROR message from rank 0 and abort all processes.
        if (rank == 0)
        {
            vtkLog(ERROR, "Failed to read restart file '"
                        << settings.restart_input << "'. Reason: " << e.what()
                        << ". Please check that the file exists and is valid.");
        }
        MPI_Abort(comm, 1);
    }
    
    return step;
}