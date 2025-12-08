#include "writerAscent.h"
#include <vtkLogger.h>
#include <iostream>
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

    vtkLogEndScope("Create Ascent Writer");
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

    // --- Build Mesh ---
    conduit::Node mesh;
    mesh["coordsets/coords/type"] = "uniform";

    int nx = sim.size_x, ny = sim.size_y, nz = sim.size_z;
    int dx = sim.offset_x, dy = sim.offset_y, dz = sim.offset_z;
    float spacing[3] = {0.1f, 0.1f, 0.1f};

    mesh["coordsets/coords/dims/i"] = nx;
    mesh["coordsets/coords/dims/j"] = ny;
    mesh["coordsets/coords/dims/k"] = nz;
    mesh["coordsets/coords/spacing/dx"] = spacing[0];
    mesh["coordsets/coords/spacing/dy"] = spacing[1];
    mesh["coordsets/coords/spacing/dz"] = spacing[2];
    mesh["coordsets/coords/origin/x"] = (dx * spacing[0] - (dx / nx) * spacing[0]);
    mesh["coordsets/coords/origin/y"] = (dy * spacing[1] - (dy / ny) * spacing[1]);
    mesh["coordsets/coords/origin/z"] = (dz * spacing[2] - (dz / nz) * spacing[2]);

    mesh["topologies/mesh/type"] = "uniform";
    mesh["topologies/mesh/coordset"] = "coords";

    mesh["fields/u/association"] = "vertex";
    mesh["fields/u/topology"] = "mesh";
    mesh["fields/u/values"].set(sim.u_noghost().data(), sim.u_noghost().size());

    mesh["fields/v/association"] = "vertex";
    mesh["fields/v/topology"] = "mesh";
    mesh["fields/v/values"].set(sim.v_noghost().data(), sim.v_noghost().size());

    mesh["state/cycle"] = step;
    mesh["state/time"] = step * settings.dt;

    conduit::Node verify_info;
    if (!conduit::blueprint::mesh::verify(mesh, verify_info))
    {
        std::cerr << "Mesh verification failed!" << std::endl;
        verify_info.print();
        return;
    }

    conduit::Node data;
    data["mesh"] = mesh;

    // --- Publish ---
    ascent.publish(data);

    // --- Hijack Actions Logic ---
    conduit::Node loaded_actions;
    std::string actions_file = "ascent_actions.yaml"; // Default

    // Try to find the real actions file from options
    try
    {
        conduit::Node options;
        conduit::relay::io::load("ascent_options.yaml", "yaml", options);
        if (options.has_path("actions_file"))
        {
            actions_file = options["actions_file"].as_string();
        }
    }
    catch (...)
    {
    }

    // Load the actions
    try
    {
        conduit::relay::io::load(actions_file, "yaml", loaded_actions);
    }
    catch (...)
    {
    }

    // Filter Loop
    conduit::Node actions_to_execute(conduit::DataType::list());
    conduit::NodeIterator itr = loaded_actions.children();

    while (itr.has_next())
    {
        conduit::Node &action = itr.next();
        if (!action.has_path("action"))
            continue;

        std::string action_type = action["action"].as_string();

        if (action_type == "add_extracts" && settings.overwrite_last_step)
        {
            conduit::Node extracts = action["extracts"];
            conduit::Node kept_extracts;
            conduit::NodeIterator ext_itr = extracts.children();

            while (ext_itr.has_next())
            {
                conduit::Node &extract = ext_itr.next();
                std::string extract_name = ext_itr.name();
                std::string type = "";
                if (extract.has_path("type"))
                    type = extract["type"].as_string();

                if (type == "relay")
                {
                    // Found a save action -> Overwrite manually
                    std::string path = "ascent_data";
                    std::string protocol = "blueprint/mesh/hdf5";

                    if (extract.has_path("params/path"))
                        path = extract["params/path"].as_string();
                    if (extract.has_path("params/protocol"))
                        protocol = extract["params/protocol"].as_string();

                    ManualOverwrite(data["mesh"], path, protocol, this->comm);
                }
                else
                {
                    kept_extracts[extract_name].set(extract);
                }
            }

            if (kept_extracts.number_of_children() > 0)
            {
                conduit::Node &new_action = actions_to_execute.append();
                new_action["action"] = "add_extracts";
                new_action["extracts"] = kept_extracts;
            }
        }
        else
        {
            actions_to_execute.append().set(action);
        }
    }

    // If we filtered out the only action (the save), this list is empty.
    // Passing an empty list makes Ascent load the default file again (undoing our work).
    if (actions_to_execute.number_of_children() > 0)
    {
        ascent.execute(actions_to_execute);
    }

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