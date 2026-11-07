#include "writerCatalyst.h"
#include <vtkImageAlgorithm.h>
#include <vtkInformation.h>
#include <vtkInformationVector.h>
#include <vtkStreamingDemandDrivenPipeline.h>
#include <iostream>
#include <exception>
#include <chrono>
#include <cstdio>
#include <filesystem>

#include <catalyst_conduit_blueprint.hpp>

namespace fs = std::filesystem;

//--------------------------------------------------------------
//  WriterCatalyst
//--------------------------------------------------------------
void WriterCatalyst::CreateWriter(const Settings &_settings, const GrayScott &sim, MPI_Comm comm, int rank)
{
    settings = _settings;
    ghosts.build(sim);
    vtkLog(TRACE, "");
    conduit_cpp::Node node;

    node["mpi_comm"] = MPI_Comm_c2f(comm);

    if (settings.output_type == "catalyst_io")
    {
        vtkLogStartScope(TRACE, "before script");
        node["catalyst/pipelines/0/type"].set("io");
        node["catalyst/pipelines/0/filename"].set(settings.output_file_name);
        node["catalyst/pipelines/0/channel"].set("grid");
        if (settings.overwrite_last_step)
        {
            node["catalyst/pipelines/0/mode"].set("update");
        }
        vtkLogStartScope(TRACE, "after script");
    }
    else if (settings.output_type == "catalyst_insitu")
    {
        const auto path = std::string(settings.catalyst_script_path);
        const auto script_name = path.substr(path.find_last_of("/\\") + 1);

        // Verify the script file exists
        if (!fs::exists(path))
        {
            vtkLog(ERROR, "Catalyst script not found at path: " << path);
            throw std::runtime_error("Missing Catalyst script file: " + path);
        }

        vtkLog(INFO, "Using Catalyst script: " << script_name);

        // Build conduit node for script with arguments
        const auto name = "catalyst/scripts/script" + script_name;
        node[name + "/filename"].set_string(path);
        node[name + "/args"].append().set_string("--channel-name=grid");
    }
    else
    {
        vtkLog(ERROR, "Unknown output type: " << settings.output_type);
        throw std::runtime_error("Invalid output type in settings.");
    }

    // indicate that we want to load ParaView-Catalyst
    node["catalyst_load/implementation"].set_string("paraview");
    node["catalyst_load/search_paths/paraview"].set_string(std::string(settings.catalyst_lib_path));

    catalyst_status err = catalyst_initialize(conduit_cpp::c_node(&node));
    if (err != catalyst_status_ok)
    {
        vtkLog(ERROR, "Failed to initialize Catalyst: " << err);
        
        if (err == catalyst_status_error_not_found)
        {
            std::cerr << "=============================================================" << std::endl;
            std::cerr << "CRITICAL ERROR: Catalyst returned status 3 (Not Found)." << std::endl;
            std::cerr << "The simulation could not locate the Catalyst implementation library." << std::endl;
            std::cerr << "Possible fixes:" << std::endl;
            std::cerr << "  1. Ensure 'catalyst_lib_path' in the json points to your catalyst dir" << std::endl;
            std::cerr << "  2. Or export CATALYST_IMPLEMENTATION_PATHS=/path/to/paraview/catalyst/" << std::endl;
            std::cerr << "=============================================================" << std::endl;
        }
        
        vtkLog(ERROR, "...checkout error code to find out why... ");
        throw std::exception();
    }
}

void WriterCatalyst::open(const std::string &fname, bool append, int rank)
{
    vtkLog(TRACE, "Finished opening Catalyst writer");
}

void WriterCatalyst::write(int step, const GrayScott &sim, int rank, int numRanks)
{
    vtkLogStartScope(TRACE, "Writing: Catalyst");
    if (!sim.size_x || !sim.size_y || !sim.size_z)
    {
        return;
    }
    using clock = std::chrono::steady_clock;
    const auto t0 = clock::now();

    conduit_cpp::Node exec_params;
    auto state = exec_params["catalyst/state"];
    // With overwrite_last_step in catalyst_io mode the step is forced to 0 so
    // each extract replaces the last; the real step goes in a parameter.
    // catalyst_insitu scripts always get the real step.
    if (settings.overwrite_last_step && settings.output_type == "catalyst_io")
    {
        state["timestep"].set(0);
        state["time"].set(0.0);
        state["parameters"].append().set_string("real_step=" + std::to_string(step));
    }
    else
    {
        state["timestep"].set(step);
        state["time"].set(static_cast<double>(step));
    }
    state["parameters"].append().set_string("timeParam=" + std::to_string(step));

    // One channel, "grid", described by the shared Blueprint builder (#21):
    // every rank's block at its true global position over the full ghosted
    // array, u and v attached without a copy, and the halo cells flagged
    // DUPLICATECELL in vtkGhostType so ParaView treats them as ghosts. This
    // replaces the old adaptor, which copied u and v without halos and
    // shifted each block's origin until the pieces touched.
    auto channel = exec_params["catalyst/channels/grid"];
    channel["type"].set("mesh");
    auto mesh = channel["data"];
    gs_mesh::GhostFields which;
    which.vtk_cells = true;
    gs_mesh::describe(mesh, sim, ghosts, which, step, step * settings.dt, rank);

    // The tree's shape never changes, so verify once (not timed).
    const auto t1 = clock::now();
    if (!verified)
    {
        conduit_cpp::Node info;
        if (!conduit_cpp::BlueprintMesh::verify(mesh, info))
        {
            std::cerr << "Blueprint verify failed on rank " << rank << std::endl;
            info.print();
            MPI_Abort(MPI_COMM_WORLD, 1);
        }
        verified = true;
        // The address lets a script confirm ParaView reads this very array.
        char where[32];
        std::snprintf(where, sizeof where, "%p", static_cast<const void *>(sim.u_ghost().data()));
        vtkLog(INFO, "Blueprint mesh verified on rank " << rank << "; u at " << where);
    }

    // Execute: ParaView converts the tree (zero-copy for the arrays) and
    // runs the pipeline or script, including any file output it does.
    const auto t2 = clock::now();
    catalyst_status err = catalyst_execute(conduit_cpp::c_node(&exec_params));
    if (err != catalyst_status_ok)
    {
        vtkLog(ERROR, "Failed to execute Catalyst: " << err);
    }
    const auto t3 = clock::now();

    phases.wrap_s = std::chrono::duration<double>(t1 - t0).count();
    phases.execute_s = std::chrono::duration<double>(t3 - t2).count();
    phases.io_s = 0.0; // file output happens inside ParaView's pipeline
    phases.split = true;
    vtkLogEndScope("Writing: Catalyst");
}

void WriterCatalyst::close(int rank)
{
    vtkLog(TRACE, "");
    conduit_cpp::Node node;
    catalyst_status err = catalyst_finalize(conduit_cpp::c_node(&node));
    if (err != catalyst_status_ok)
    {
        vtkLog(ERROR, "ERROR: Failed to finalize Catalyst: " << err);
    }
}

void WriterCatalyst::printSelf()
{
    vtkLog(TRACE, "This is writer type Catalyst ");
}

