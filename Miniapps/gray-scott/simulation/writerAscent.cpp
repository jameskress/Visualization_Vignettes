#include "writerAscent.h"
#include <vtkLogger.h>
#include <iostream>
#include <exception>

void WriterAscent::CreateWriter(const Settings &_settings, const GrayScott &sim, int rank)
{
    settings = _settings;
    vtkLogStartScope(TRACE, "Create Ascent Writer");

    conduit::Node ascent_opts;
    ascent_opts["runtime/type"] = "ascent";
    ascent_opts["mpi_comm"] = MPI_Comm_c2f(MPI_COMM_WORLD);

    ascent.open(ascent_opts);

    vtkLogEndScope("Create Ascent Writer");
}

void WriterAscent::open(const std::string &fname, bool append, int rank)
{
    vtkLog(TRACE, "Open Ascent Writer");
}

void WriterAscent::write(int step, const GrayScott &sim, int rank, int numRanks)
{
    vtkLogStartScope(TRACE, "Writing: Ascent");

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

    // move the final mesh fragments so that each domain is flush against all other domains.
    // this is necessary as we could not get ghost cells to work correctly, so with all
    // domains touching the visulaization is able to create its own
    mesh["coordsets/coords/origin/x"] = (dx * spacing[0] - (dx / nx) * spacing[0]); // dx * spacing[0];
    mesh["coordsets/coords/origin/y"] = (dy * spacing[1] - (dy / ny) * spacing[1]); // dy * spacing[1];
    mesh["coordsets/coords/origin/z"] = (dz * spacing[2] - (dz / nz) * spacing[2]); // dz * spacing[2];

    mesh["topologies/mesh/type"] = "uniform";
    mesh["topologies/mesh/coordset"] = "coords";

    mesh["fields/u/association"] = "vertex";
    mesh["fields/u/topology"] = "mesh";
    mesh["fields/u/values"].set(sim.u_noghost().data(), sim.u_noghost().size());

    mesh["fields/v/association"] = "vertex";
    mesh["fields/v/topology"] = "mesh";
    mesh["fields/v/values"].set(sim.v_noghost().data(), sim.v_noghost().size());

    conduit::Node verify_info;
    if (!conduit::blueprint::mesh::verify(mesh, verify_info))
    {
        std::cerr << "Mesh verification failed!" << std::endl;
        verify_info.print();
        return;
    }

    conduit::Node data;
    data["mesh"] = mesh;

    conduit::Node actions;

    conduit::Node &add_action = actions.append();
    add_action["action"] = "add_scenes";
    conduit::Node &scenes = add_action["scenes"];
    scenes["default_scene/plots/p1/type"] = "pseudocolor";
    scenes["default_scene/plots/p1/field"] = "u";
    scenes["default_scene/image_prefix"] = "writerAscent_builtin_scene_ts-";

    // Publish the data and execute
    ascent.publish(data);
    ascent.execute(actions);

    // print the conduit structure
    // data.print();

    // used for debugging what ascent sees internally
    // conduit::Node info;
    // ascent.info(info);
    // info.print();

    vtkLogEndScope("Writing: Ascent");
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