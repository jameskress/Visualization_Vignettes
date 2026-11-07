#ifndef __WRITERASCENT_H__
#define __WRITERASCENT_H__

#include "writer.h"
#include "gray-scott.h"
#include "settings.h"
#include <ascent.hpp>
#include <conduit.hpp>
#include <conduit_blueprint.hpp>

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

    void ManualOverwrite(conduit::Node &mesh, const std::string &base_path, const std::string &protocol, MPI_Comm comm);
};

#endif