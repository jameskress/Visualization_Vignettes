#include "writerAscent.h"

#include <fstream>
#include <vtkLogger.h>
#include <iostream>
#include <chrono>
#include <exception>
#include <conduit_relay_io.hpp>
#include <conduit_relay_mpi_io_blueprint.hpp>
#include "../common/ascent_overwrite.hpp"

void WriterAscent::CreateWriter(const Settings &_settings, const GrayScott &sim, MPI_Comm comm, int rank)
{
    settings = _settings;
    vtkLogStartScope(TRACE, "Create Ascent Writer");

    conduit::Node ascent_opts;
    ascent_opts["runtime/type"] = "ascent";
    ascent_opts["mpi_comm"] = MPI_Comm_c2f(comm);
    this->comm = comm;

    // This opens Ascent and automatically loads 'ascent_options.yaml'
    ascent.open(ascent_opts);

    ghosts.build(sim);
    load_actions();

    vtkLogEndScope("Create Ascent Writer");
}

// Read the actions once (they used to be re-read from disk every step). With
// overwrite_last_step, relay extracts are taken out and done by
// ManualOverwrite so each save replaces the last one.
void WriterAscent::load_actions()
{
    int rank = 0;
    MPI_Comm_rank(comm, &rank);
    std::string error;
    const conduit::Node loaded = gs_ascent::LoadActionsFile(error);
    // A missing options file is normal (Ascent's defaults apply); one that
    // exists but does not parse is an error worth reporting.
    if (!error.empty() && rank == 0)
        vtkLog(ERROR, "Ascent: " << error);
    std::vector<std::string> unsupported;
    gs_ascent::SplitRelayExtracts(loaded, settings.overwrite_last_step, actions, relay_extracts, unsupported);
    if (rank == 0)
        for (const auto &param : unsupported)
            vtkLog(ERROR, "Ascent: overwrite_last_step does not support " << param);
}

void WriterAscent::open(const std::string &fname, bool append, int rank)
{
    vtkLog(TRACE, "Open Ascent Writer");
}

void WriterAscent::close(int rank)
{
    vtkLog(TRACE, "Closing Ascent");
    ascent.close();
}

void WriterAscent::printSelf()
{
    vtkLog(TRACE, "This is writer type Ascent");
}

void WriterAscent::write(int step, const GrayScott &sim, int rank, int numRanks)
{
    vtkLogStartScope(TRACE, "Writing: Ascent");
    using clock = std::chrono::steady_clock;

    // Wrap: the shared Blueprint description, zero-copy (#20). The caller
    // has refreshed the halo.
    const auto t0 = clock::now();
    const AllocSnapshot wrap_alloc;
    gs_mesh::GhostFields which;
    which.ascent = true;
    gs_mesh::describe(data["mesh"], sim, ghosts, which, step, step * settings.dt, rank);
    const auto t1 = clock::now();
    phases.wrap_allocs = wrap_alloc.delta_calls();
    phases.wrap_alloc_bytes = wrap_alloc.delta_bytes();
    check_zero_copy(data["mesh/fields/u/values"].data_ptr(), sim.u_ghost().data(), "Ascent u");

    // The tree's shape never changes, so verify once (not timed).
    if (!verified)
    {
        conduit::Node info;
        if (!conduit::blueprint::mesh::verify(data["mesh"], info))
        {
            std::cerr << "Blueprint verify failed on rank " << rank << std::endl;
            info.print();
            MPI_Abort(comm, 1);
        }
        verified = true;
        vtkLog(INFO, "Blueprint mesh verified on rank " << rank);
    }

    // Execute: publish (Ascent keeps a reference, no copy) and run actions.
    // An empty list would make Ascent reload its default actions file.
    const auto t2 = clock::now();
    ascent.publish(data);
    if (actions.number_of_children() > 0)
        ascent.execute(actions);
    const auto t3 = clock::now();

    // I/O: the manual relay save used with overwrite_last_step.
    for (const auto &rx : relay_extracts)
        ManualOverwrite(data["mesh"], rx.first, rx.second, this->comm);
    const auto t4 = clock::now();

    phases.wrap_s = std::chrono::duration<double>(t1 - t0).count();
    phases.execute_s = std::chrono::duration<double>(t3 - t2).count();
    phases.io_s = std::chrono::duration<double>(t4 - t3).count();
    phases.split = true;

    vtkLogEndScope("Writing: Ascent");
}

void WriterAscent::ManualOverwrite(conduit::Node &mesh,
                                   const std::string &base_path,
                                   const std::string &protocol,
                                   MPI_Comm comm)
{
    // Every save is written as cycle 0, so it replaces the last one
    // (common/ascent_overwrite.hpp).
    const std::string error = gs_ascent::SaveMeshAsCycleZero(mesh, base_path, protocol, comm);
    if (!error.empty())
        std::cerr << "[WriterAscent] Error executing manual overwrite: " << error << std::endl;
}
