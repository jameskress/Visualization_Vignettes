#ifndef __WRITERASCENT_H__
#define __WRITERASCENT_H__

#include "writer.h"
#include "gray-scott.h"
#include "settings.h"
#include <ascent.hpp>
#include <conduit.hpp>
#include <conduit_blueprint.hpp>

#include "mesh_blueprint.h"

#include <string>
#include <utility>
#include <vector>

class WriterAscent : public Writer
{
public:
    void CreateWriter(const Settings &settings, const GrayScott &sim, MPI_Comm comm, int rank) override;
    void open(const std::string &fname, bool append, int rank) override;
    void write(int step, const GrayScott &sim, int rank, int numRanks) override;
    void close(int rank) override;
    void printSelf() override;
    std::string backendVersion() const override
    {
        conduit::Node about;
        ascent::about(about);
        return "Ascent " + (about.has_child("version") ? about["version"].as_string() : std::string("unknown"));
    }
    // Ascent reads ascent_options.yaml, which names the actions file.
    std::string backendScript() const override { return "ascent_options.yaml"; }

private:
    ascent::Ascent ascent;
    Settings settings;
    MPI_Comm comm;

    // Published tree; its fields point at the solver's arrays (#20).
    conduit::Node data;
    gs_mesh::Ghosts ghosts;
    bool verified = false;
    // Actions, loaded and filtered once in CreateWriter. With
    // overwrite_last_step, relay extracts are replaced by a manual save.
    conduit::Node actions;
    // Each relay extract's (path, protocol), saved one by one.
    std::vector<std::pair<std::string, std::string>> relay_extracts;
    void load_actions();

    void ManualOverwrite(conduit::Node &mesh, const std::string &base_path, const std::string &protocol, MPI_Comm comm);
};

#endif