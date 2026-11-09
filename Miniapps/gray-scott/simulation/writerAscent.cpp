#include "writerAscent.h"

#include <fstream>
#include <vtkLogger.h>
#include <iostream>
#include <chrono>
#include <exception>
#include <conduit_relay_io.hpp>
#include <conduit_relay_mpi_io_blueprint.hpp>

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
    conduit::Node loaded;
    std::string actions_file = "ascent_actions.yaml"; // Ascent's default
    // A missing options file is normal (Ascent's defaults apply); one that
    // exists but does not parse is an error worth reporting.
    if (std::ifstream("ascent_options.yaml").good())
    {
        try
        {
            conduit::Node options;
            conduit::relay::io::load("ascent_options.yaml", "yaml", options);
            if (options.has_path("actions_file"))
                actions_file = options["actions_file"].as_string();
        }
        catch (const conduit::Error &e)
        {
            if (rank == 0)
                vtkLog(ERROR, "Ascent: cannot read ascent_options.yaml: " << e.message());
        }
    }
    try
    {
        conduit::relay::io::load(actions_file, "yaml", loaded);
    }
    catch (const conduit::Error &e)
    {
        if (rank == 0)
            vtkLog(ERROR, "Ascent: cannot read actions file '" << actions_file << "': " << e.message()
                          << "; no Ascent actions will run");
    }

    actions.set(conduit::DataType::list());
    conduit::NodeIterator itr = loaded.children();
    while (itr.has_next())
    {
        conduit::Node &action = itr.next();
        if (!action.has_path("action"))
            continue;
        const std::string action_type = action["action"].as_string();
        if (action_type == "add_extracts" && settings.overwrite_last_step)
        {
            conduit::Node kept;
            conduit::NodeIterator ext_itr = action["extracts"].children();
            while (ext_itr.has_next())
            {
                conduit::Node &extract = ext_itr.next();
                const std::string name = ext_itr.name();
                const std::string type = extract.has_path("type") ? extract["type"].as_string() : "";
                if (type == "relay")
                {
                    relay_extracts.emplace_back(
                        extract.has_path("params/path") ? extract["params/path"].as_string() : "ascent_data",
                        extract.has_path("params/protocol") ? extract["params/protocol"].as_string()
                                                            : "blueprint/mesh/hdf5");
                }
                else
                    kept[name].set(extract);
            }
            if (kept.number_of_children() > 0)
            {
                conduit::Node &a = actions.append();
                a["action"] = "add_extracts";
                a["extracts"] = kept;
            }
        }
        else
            actions.append().set(action);
    }
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
    // 1. Prepare Protocol and Path
    std::string file_protocol = "hdf5";
    std::string file_root = base_path;

    // Strip extension if present
    size_t ext_pos = file_root.find(".hdf5");
    if (ext_pos != std::string::npos)
    {
        file_root = file_root.substr(0, ext_pos);
    }

    // 2. Force 'state/cycle' to 0
    conduit::Node hold_cycle;

    // Check if we have a cycle to back up
    if (mesh.has_path("state/cycle"))
    {
        hold_cycle = mesh["state/cycle"]; // Backup the real cycle (e.g., 100)
    }

    // Force the mesh to look like cycle 0
    mesh["state/cycle"] = 0;

    try
    {
        // This will now write to "...cycle_000000..." every time.
        conduit::relay::mpi::io::blueprint::save_mesh(mesh, file_root, file_protocol, comm);
    }
    catch (const conduit::Error &e)
    {
        std::cerr << "[WriterAscent] Error executing manual overwrite: "
                  << e.message() << std::endl;
    }

    // 3. Restore the REAL 'state/cycle'
    if (!hold_cycle.dtype().is_empty())
    {
        mesh["state/cycle"] = hold_cycle;
    }
    else
    {
        // If it didn't exist before, remove our forced 0
        mesh.remove("state/cycle");
    }
}
