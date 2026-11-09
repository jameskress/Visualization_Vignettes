#ifndef __WRITER_H__
#define __WRITER_H__

#include "gray-scott.h"
#include "settings.h"
#include <mpi.h>
#include <string>
#include <vtkVersion.h>
#include <vtkSmartPointer.h>
#include <vtkXMLPImageDataWriter.h>
#include <vtkImageData.h>
#include <vtkPointData.h>
#include <vtkDoubleArray.h>
#include <vtkFloatArray.h>
#include <vtkLogger.h>
#include <vtkMPIController.h>

class Writer
{
public:
    virtual void CreateWriter(const Settings &settings, const GrayScott &sim, MPI_Comm comm, int rank) = 0;
    virtual void open(const std::string &fname, bool append, int rank) = 0;
    virtual void write(int step, const GrayScott &sim, int rank, int numRanks) = 0;
    virtual void close(int rank) = 0;
    virtual void printSelf() = 0;

    // Performance log support (#26) ------------------------------------
    // Where a backend can separate its work, write() fills these for the
    // step it just ran (seconds). split == false means the backend reports
    // no split yet and the whole write counts as "execute".
    struct Phases
    {
        double wrap_s = 0.0;    // building the backend's data description
        double execute_s = 0.0; // the backend's pipeline, actions or engine
        double io_s = 0.0;      // writing files or moving data out
        bool split = false;
    };
    const Phases &lastPhases() const { return phases; }
    // Backend library and version for the run metadata.
    virtual std::string backendVersion() const { return "unknown"; }
    // Script or configuration file that drives the backend, if any.
    virtual std::string backendScript() const { return ""; }


protected:
    Phases phases;
    Settings settings;
    vtkSmartPointer<vtkXMLPImageDataWriter> writer;
    vtkSmartPointer<vtkMPIController> controller;
};

#endif
