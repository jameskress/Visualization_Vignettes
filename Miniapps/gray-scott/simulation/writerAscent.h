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

private:
    ascent::Ascent ascent;
};

#endif