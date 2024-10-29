#ifndef __WRITER_H__
#define __WRITER_H__

#include "gray-scott.h"
#include "settings.h"
#include <mpi.h>
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
    virtual void CreateWriter(const Settings &settings, const GrayScott &sim, int rank) = 0;
    virtual void open(const std::string &fname, bool append, int rank) = 0;
    virtual void write(int step, const GrayScott &sim, int rank, int numRanks) = 0;
    virtual void close(int rank) = 0;
    virtual void printSelf() = 0;


protected:
    Settings settings;
    vtkSmartPointer<vtkXMLPImageDataWriter> writer;
    vtkSmartPointer<vtkMPIController> controller;
};

#endif
