#pragma once

// Ascent's overwrite_last_step, shared by the simulation's Ascent writer and
// the analysis reader's Ascent backend: both run the same actions file, and
// with overwrite_last_step both save the mesh in place of Ascent's relay
// extracts, as cycle 0, so each save replaces the last one.

#include <mpi.h>

#include <conduit.hpp>
#include <conduit_relay_io.hpp>
#include <conduit_relay_mpi_io_blueprint.hpp>

#include <fstream>
#include <string>
#include <utility>
#include <vector>

namespace gs_ascent
{

// A relay extract taken out of the actions: its params/path and
// params/protocol.
using RelayExtract = std::pair<std::string, std::string>;

// Loads the actions file Ascent would load: the one ascent_options.yaml in
// the working directory names (actions_file), or ascent_actions.yaml. A
// missing options file is normal; problems reading either file are
// returned in error (empty when none), and leave loaded empty.
inline conduit::Node LoadActionsFile(std::string &error)
{
    conduit::Node loaded;
    std::string actions_file = "ascent_actions.yaml"; // Ascent's default
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
            error = "cannot read ascent_options.yaml: " + e.message();
        }
    }
    try
    {
        conduit::relay::io::load(actions_file, "yaml", loaded);
    }
    catch (const conduit::Error &e)
    {
        error += (error.empty() ? "" : "; ") + std::string("cannot read actions file '") + actions_file + "': " +
                 e.message() + "; no Ascent actions will run";
    }
    return loaded;
}

// Copies the actions in loaded to actions (a list). With overwrite, relay
// extracts are left out and listed in relay, and an add_extracts action
// left with no extract is dropped.
inline void SplitRelayExtracts(const conduit::Node &loaded, bool overwrite, conduit::Node &actions,
                               std::vector<RelayExtract> &relay)
{
    actions.set(conduit::DataType::list());
    conduit::NodeConstIterator itr = loaded.children();
    while (itr.has_next())
    {
        const conduit::Node &action = itr.next();
        if (!action.has_path("action"))
            continue;
        const std::string action_type = action["action"].as_string();
        if (action_type == "add_extracts" && overwrite)
        {
            conduit::Node kept;
            conduit::NodeConstIterator ext_itr = action["extracts"].children();
            while (ext_itr.has_next())
            {
                const conduit::Node &extract = ext_itr.next();
                const std::string name = ext_itr.name();
                const std::string type = extract.has_path("type") ? extract["type"].as_string() : "";
                if (type == "relay")
                {
                    relay.emplace_back(
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

// Saves mesh (one domain, or a list of domains) as Blueprint HDF5 under
// base_path as cycle 0, so every save writes the same files. The mesh's
// state/cycle is restored afterwards (each domain's, for a list). Returns an
// error message, empty on success.
inline std::string SaveMeshAsCycleZero(conduit::Node &mesh, const std::string &base_path, MPI_Comm comm)
{
    std::string file_root = base_path;
    const size_t ext_pos = file_root.find(".hdf5");
    if (ext_pos != std::string::npos)
        file_root = file_root.substr(0, ext_pos);

    // The domains whose cycle is forced: the mesh itself, or each domain.
    std::vector<conduit::Node *> domains;
    if (mesh.dtype().is_list())
    {
        for (conduit::index_t i = 0; i < mesh.number_of_children(); ++i)
            domains.push_back(&mesh.child(i));
    }
    else
        domains.push_back(&mesh);

    std::vector<conduit::Node> held(domains.size());
    for (size_t i = 0; i < domains.size(); ++i)
    {
        if (domains[i]->has_path("state/cycle"))
            held[i] = (*domains[i])["state/cycle"];
        (*domains[i])["state/cycle"] = 0;
    }

    std::string error;
    try
    {
        conduit::relay::mpi::io::blueprint::save_mesh(mesh, file_root, "hdf5", comm);
    }
    catch (const conduit::Error &e)
    {
        error = e.message();
    }

    for (size_t i = 0; i < domains.size(); ++i)
    {
        if (!held[i].dtype().is_empty())
            (*domains[i])["state/cycle"] = held[i];
        else
            domains[i]->remove("state/cycle");
    }
    return error;
}

} // namespace gs_ascent
