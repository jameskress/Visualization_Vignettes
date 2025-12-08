#ifndef __WRITERADIOS_H__
#define __WRITERADIOS_H__

#include "writer.h"
#include <adios2.h>
#include <vtkLogger.h>

class WriterADIOS : public Writer
{
public:
    WriterADIOS();
    ~WriterADIOS();

    void CreateWriter(const Settings &settings, const GrayScott &sim, MPI_Comm comm, int rank) override;
    void SetADIOS(adios2::ADIOS &adios);
    void open(const std::string &fname, bool append, int rank) override;
    void write(int step, const GrayScott &sim, int rank, int numRanks) override;
    void close(int rank) override;
    void printSelf() override;

private:
    adios2::IO m_io;
    adios2::Engine m_engine;
    std::string m_fname;
    adios2::Variable<double> m_var_u;
    adios2::Variable<double> m_var_v;
    adios2::Variable<int> m_var_step;
    bool m_is_first_step = true;
};

#endif // __WRITERADIOS_H__