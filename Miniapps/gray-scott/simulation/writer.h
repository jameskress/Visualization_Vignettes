#ifndef __WRITER_H__
#define __WRITER_H__

#include "gray-scott.h"
#include "settings.h"
#include <mpi.h>
#include <cstdint>
#include <string>

#include "common/alloc_count.hpp"
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
        // Heap allocations made while wrapping (#25); 0 unless the build
        // has GS_COUNT_ALLOCATIONS.
        std::uint64_t wrap_allocs = 0;
        std::uint64_t wrap_alloc_bytes = 0;
    };
    const Phases &lastPhases() const { return phases; }
    // Backend library and version for the run metadata.
    virtual std::string backendVersion() const { return "unknown"; }
    // Script or configuration file that drives the backend, if any.
    virtual std::string backendScript() const { return ""; }


protected:
    // Zero-copy check (#25): the array handed to the backend must be the
    // solver's own. Every write in debug builds, the first write in release.
    void check_zero_copy(const void *handed, const void *own, const char *what)
    {
#ifdef NDEBUG
        if (zero_copy_checked)
            return;
#endif
        zero_copy_checked = true;
        if (handed != own)
        {
            vtkLog(ERROR, "zero-copy check failed: " << what << " handed to the backend is a copy");
            MPI_Abort(MPI_COMM_WORLD, 1);
        }
    }
    bool zero_copy_checked = false;

    Phases phases;
    Settings settings;
    vtkSmartPointer<vtkXMLPImageDataWriter> writer;
    vtkSmartPointer<vtkMPIController> controller;
};

#endif
