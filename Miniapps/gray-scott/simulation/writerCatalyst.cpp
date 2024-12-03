#include "writerCatalyst.h"
#include <vtkImageAlgorithm.h>
#include <vtkInformation.h>
#include <vtkInformationVector.h>
#include <vtkStreamingDemandDrivenPipeline.h>
#include <iostream>
#include <exception>


//--------------------------------------------------------------
//  WriterCatalyst
//--------------------------------------------------------------
void WriterCatalyst::CreateWriter(const Settings &_settings, const GrayScott &sim, int rank)

{
    settings = _settings;
    vtkLog(TRACE, "");
    conduit_cpp::Node node;

    if (settings.output_type == "catalyst_io")
    {
      vtkLogStartScope(TRACE, "before script");
      node["catalyst/pipelines/0/type"].set("io");
      node["catalyst/pipelines/0/filename"].set(settings.output_file_name);
      node["catalyst/pipelines/0/channel"].set("grid");
      vtkLogStartScope(TRACE, "after script");
    }
    else
    {
      const auto path = std::string(settings.catalyst_script_path);
      // note: one can simply add the script file as follows:
      //node["catalyst/scripts/script" + settings.catalyst_script].set_string(path);
      const auto script_name =  path.substr(path.find_last_of("/\\") + 1);

      // alternatively, use this form to pass optional parameters to the script.
      const auto name = "catalyst/scripts/script" + script_name;

      node[name + "/filename"].set_string(path);
      node[name + "/args"].append().set_string("--channel-name=grid");
    }

    // indicate that we want to load ParaView-Catalyst
    node["catalyst_load/implementation"].set_string("paraview");
    node["catalyst_load/search_paths/paraview"].set_string(std::string(settings.catalyst_lib_path));

    catalyst_status err = catalyst_initialize(conduit_cpp::c_node(&node));
    if (err != catalyst_status_ok)
    {
        vtkLog(ERROR, "Failed to initialize Catalyst: " << err);
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

    conduit_cpp::Node exec_params;
    // add time/cycle information
    auto state = exec_params["catalyst/state"];
    state["timestep"].set(step);
    state["time"].set(step);

    // add optional exectution parameters passed to catalyst
    state["parameters"].append().set_string("timeParam=" + std::to_string(step));

    // Add channels.
    // We only have 1 channel here. Let's name it 'grid'.
    auto channel = exec_params["catalyst/channels/grid"];

    // Since this example is using Conduit Mesh Blueprint to define the mesh,
    // we set the channel's type to "mesh".
    channel["type"].set("mesh");

    // now create the mesh.
    auto mesh = channel["data"];

    // start with coordsets (of course, the sequence is not important, just make
    // it easier to think in this order).
    mesh["coordsets/coords/type"].set("uniform");

    int origin[3] = {0, 0, 0};
    float spacing[3] = {0.1, 0.1, 0.1};
    //For no_ghost use
    int nx = sim.size_x + 0, ny = sim.size_y + 0, nz = sim.size_z + 0;

    //int nx = sim.size_x + 2, ny = sim.size_y + 2, nz = sim.size_z + 2;
    int dx = sim.offset_x, dy = sim.offset_y, dz = sim.offset_z;
    int wholeExtent[6] = {0, (int)settings.L, 0, (int)settings.L, 0, (int)settings.L};
    vtkLog(TRACE, "" << "size " << nx << " " << ny << " " << nz);
    vtkLog(TRACE, "" << "offsets " << dx << " " << dy << " " << dz);
    vtkLog(TRACE, "" << "local dims "
                          << dx << " "
                          << nx + dx << " "
                          << dy << " "
                          << ny + dy << " "
                          << dz << " "
                          << nz + dz);
    vtkLog(TRACE, "" << "global dims "
                          << 0 << " "
                          << (int)settings.L << " "
                          << 0 << " "
                          << (int)settings.L << " "
                          << 0 << " "
                          << (int)settings.L);


    // move the final mesh fragments so that each domain is flush against all other domains.
    // this is necessary as we could not get ghost cells to work correctly, so with all
    // domains touching the visulaization is able to create its own
    mesh["coordsets/coords/origin/x"].set(dx * spacing[0] - (dx/nx) * spacing[0]);
    mesh["coordsets/coords/origin/y"].set(dy * spacing[1] - (dy/ny) * spacing[1]);
    mesh["coordsets/coords/origin/z"].set(dz * spacing[2] - (dz/nz) * spacing[2]);

    // mesh["coordsets/coords/origin/x"].set(dx * spacing[0]);
    // mesh["coordsets/coords/origin/y"].set(dy * spacing[1]);
    // mesh["coordsets/coords/origin/z"].set(dz * spacing[2]);

    mesh["coordsets/coords/dims/i"].set(nx);
    mesh["coordsets/coords/dims/j"].set(ny);
    mesh["coordsets/coords/dims/k"].set(nz);

    mesh["coordsets/coords/spacing/dx"].set(spacing[0]);
    mesh["coordsets/coords/spacing/dy"].set(spacing[1]);
    mesh["coordsets/coords/spacing/dz"].set(spacing[2]);

    // Next, add topology
    mesh["topologies/mesh/type"].set("uniform");
    mesh["topologies/mesh/coordset"].set("coords");

    // Finally, add fields.
    auto fields = mesh["fields"];
    fields["v/association"].set("vertex");
    fields["v/topology"].set("mesh");
    fields["v/volume_dependent"].set("false");
    //fields["v/values"].set_external(sim.v_ghost().data(), sim.v_ghost().size());
    fields["v/values"].set(sim.v_noghost().data(), sim.v_noghost().size());

    fields["u/association"].set("vertex");
    fields["u/topology"].set("mesh");
    fields["u/volume_dependent"].set("false");
    //fields["u/values"].set_external(sim.u_ghost().data(), sim.u_ghost().size());
    fields["u/values"].set(sim.u_noghost().data(), sim.u_noghost().size());

    // std::cerr << __FILE__ << __LINE__ << std::endl;
    // // special case to handle ghost cells by creating a ghost mask
    // fields["vtkGhostType/association"].set("vertex");
    // fields["vtkGhostType/topology"].set("mesh");
    // fields["vtkGhostType/volume_dependent"].set("false");
    // auto testdata = sim.ghost_point_mask();
    // std::cerr << testdata.size() << std::endl;
    // //sim.ghost_cell_mask().size()
    // fields["vtkGhostType/values"].set(testdata.data(), testdata.size());
    // std::cerr << __FILE__ << __LINE__ << std::endl;

    // special case to handle ghost cells by creating a ghost mask
    // fields["qw/association"].set("element");
    // fields["qw/topology"].set("mesh");
    // fields["qw/volume_dependent"].set("false");
    // auto cellData = sim.ghost_cell_mask();
    // std::cerr << cellData.size() << std::endl;
    // //sim.ghost_cell_mask().size()
    // fields["qw/values"].set(cellData.data(), cellData.size());

    catalyst_status err = catalyst_execute(conduit_cpp::c_node(&exec_params));
    if (err != catalyst_status_ok)
    {
        vtkLog(ERROR, "Failed to execute Catalyst: " << err);
    }
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
