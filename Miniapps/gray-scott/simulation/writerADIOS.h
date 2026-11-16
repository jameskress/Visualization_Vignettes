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
    std::string backendVersion() const override { return std::string("ADIOS2 ") + ADIOS2_VERSION_STR; }
    std::string backendScript() const override { return settings.adios_config; }
    bool overwritesLastStep(const Settings &) const override { return settings.overwrite_last_step; }

private:
    adios2::IO m_io;
    adios2::Engine m_engine;
    std::string m_fname;
    adios2::Variable<double> m_var_u;
    adios2::Variable<double> m_var_v;
    adios2::Variable<int> m_var_step;
    // Rank 0's wall-clock time (seconds since the epoch) as it enters
    // EndStep(), so a reader can time the step's delivery (Step_Latency).
    adios2::Variable<double> m_var_endstep_wall;
    double m_endstep_wall = 0.0;
    MPI_Comm m_comm = MPI_COMM_NULL;
    // Barrier (with adios_endstep_barrier), the wall-clock stamp and
    // EndStep(); returns the seconds spent in the barrier.
    double EndStepTimed(int rank);
    bool m_is_first_step = true;
};

#endif // __WRITERADIOS_H__
