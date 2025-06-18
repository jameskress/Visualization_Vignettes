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

    // The base class interface remains unchanged.
    void CreateWriter(const Settings &settings, const GrayScott &sim, int rank) override;
    
    // Add a new public method specific to this class
    void SetADIOS(adios2::ADIOS &adios);

    void open(const std::string &fname, bool append, int rank) override;
    void write(int step, const GrayScott &sim, int rank, int numRanks) override;
    void close(int rank) override;
    void printSelf() override;

private:
    // This class no longer creates or owns the ADIOS object.
    adios2::IO m_io;
    adios2::Engine m_engine;

    // ... other members are the same
    adios2::Variable<double> m_var_u;
    adios2::Variable<double> m_var_v;
    adios2::Variable<int> m_var_step;
    bool m_is_first_step = true;
};

#endif // __WRITERADIOS_H__