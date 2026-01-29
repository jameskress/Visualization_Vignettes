#ifndef __WRITERNONE_H__
#define __WRITERNONE_H__

#include "writer.h"
#include <iostream>

class WriterNone : public Writer
{
public:
    // Empty implementations for all pure virtual functions
    void CreateWriter(const Settings &settings, const GrayScott &sim, MPI_Comm comm, int rank) override {}
    
    void open(const std::string &fname, bool append, int rank) override {}
    
    void write(int step, const GrayScott &sim, int rank, int numRanks) override {}
    
    void close(int rank) override {}
    
    void printSelf() override 
    {
        std::cout << "Writer: None (No output will be generated)" << std::endl;
    }
};

#endif