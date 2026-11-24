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

// The protocol Ascent 0.9.6 reads a settings file with: yaml when the name
// ends in .yaml, json otherwise.
inline std::string SettingsFileProtocol(const std::string &file)
{
    const std::string ext = ".yaml";
    return file.size() >= ext.size() && file.compare(file.size() - ext.size(), ext.size(), ext) == 0 ? "yaml"
                                                                                                        : "json";
}

// True when node or any node below it has a child named "include": Ascent
// expands those from other files, which this split does not read.
inline bool HasInclude(const conduit::Node &node)
{
    if (!node.dtype().is_object() && !node.dtype().is_list())
        return false;
    conduit::NodeConstIterator itr = node.children();
    while (itr.has_next())
    {
        const conduit::Node &child = itr.next();
        if ((node.dtype().is_object() && itr.name() == "include") || HasInclude(child))
            return true;
    }
    return false;
}

// Loads the actions file Ascent 0.9.6 would load, by its rules: the options
// file is ascent_options.json, or ascent_options.yaml when there is no JSON
// one, and names the actions file (actions_file); without one, Ascent takes
// ascent_actions.json, or ascent_actions.yaml. A missing options file is
// normal; problems reading either file are returned in error (empty when
// none), and leave loaded empty.
inline conduit::Node LoadActionsFile(std::string &error)
{
    conduit::Node loaded;
    std::string options_file = "ascent_options.json";
    if (!std::ifstream(options_file).good())
        options_file = "ascent_options.yaml";
    std::string actions_file;
    bool named = false; // the options name an actions file, possibly ""
    if (std::ifstream(options_file).good())
    {
        try
        {
            conduit::Node options;
            conduit::relay::io::load(options_file, SettingsFileProtocol(options_file), options);
            // Ascent expands includes in the options file; one could name
            // another actions file than the one read here.
            if (HasInclude(options))
                error = options_file + " uses include, which is not read here";
            if (options.has_path("actions_file"))
            {
                actions_file = options["actions_file"].as_string();
                named = true;
            }
        }
        catch (const conduit::Error &e)
        {
            error = "cannot read " + options_file + ": " + e.message();
        }
    }
    // An empty actions_file turns Ascent's file-based actions off.
    if (named && actions_file.empty())
        return loaded;
    if (actions_file.empty())
        actions_file = std::ifstream("ascent_actions.json").good() ? "ascent_actions.json" : "ascent_actions.yaml";
    try
    {
        conduit::relay::io::load(actions_file, SettingsFileProtocol(actions_file), loaded);
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
// left with no extract is dropped. Relay parameters the cycle-0 save does not
// honour (anything but path and protocol, e.g. fields), and include nodes,
// are listed in unsupported.
inline void SplitRelayExtracts(const conduit::Node &loaded, bool overwrite, conduit::Node &actions,
                               std::vector<RelayExtract> &relay, std::vector<std::string> &unsupported)
{
    // An included file could define a relay extract the split cannot see.
    if (overwrite && HasInclude(loaded))
        unsupported.push_back("include (actions from another file)");
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
                    // Only path and protocol are honoured by the save that
                    // replaces the extract (SaveMeshAsCycleZero).
                    if (extract.has_path("params"))
                    {
                        conduit::NodeConstIterator p_itr = extract["params"].children();
                        while (p_itr.has_next())
                        {
                            p_itr.next();
                            const std::string param = p_itr.name();
                            if (param != "path" && param != "protocol")
                                unsupported.push_back(name + "/params/" + param);
                        }
                    }
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

// Saves mesh (one domain, or a list of domains) under base_path as cycle 0,
// so every save writes the same files, in the relay extract's protocol
// (blueprint/mesh/hdf5, the default, or hdf5, yaml, json, with or without
// the blueprint/mesh/ prefix; bare blueprint is HDF5). The mesh's state/cycle is restored afterwards
// (each domain's, for a list). Returns an error message, empty on success.
inline std::string SaveMeshAsCycleZero(conduit::Node &mesh, const std::string &base_path, const std::string &protocol,
                                       MPI_Comm comm)
{
    std::string file_protocol = protocol;
    const std::string prefix = "blueprint/mesh/";
    if (file_protocol.compare(0, prefix.size(), prefix) == 0)
        file_protocol = file_protocol.substr(prefix.size());
    // An empty protocol and bare "blueprint" are HDF5, as before.
    if (file_protocol.empty() || file_protocol == "blueprint")
        file_protocol = "hdf5";
    if (file_protocol != "hdf5" && file_protocol != "yaml" && file_protocol != "json")
        return "unsupported relay protocol '" + protocol + "'";

    std::string file_root = base_path;
    // Only a terminal .hdf5, never one inside a directory name.
    const std::string ext = ".hdf5";
    if (file_root.size() >= ext.size() && file_root.compare(file_root.size() - ext.size(), ext.size(), ext) == 0)
        file_root.resize(file_root.size() - ext.size());

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
        conduit::relay::mpi::io::blueprint::save_mesh(mesh, file_root, file_protocol, comm);
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
