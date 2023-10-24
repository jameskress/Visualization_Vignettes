#ifndef __WRITER_H__
#define __WRITER_H__

#include <mpi.h>

#include "../../gray-scott/simulation/gray-scott.h"
#include "../../gray-scott/simulation/settings.h"
#include <vtkVersion.h>
#include <vtkSmartPointer.h>
#include <vtkXMLPImageDataWriter.h>
#include <vtkImageData.h>
#include <vtkPointData.h>
#include <vtkDoubleArray.h>
#include <vtkLogger.h>
#include <vtkMPIController.h>
   
class Writer
{
public:
    Writer(const Settings &settings, const GrayScott &sim, int rank);
    void open(const std::string &fname, bool append, int rank);
    void write(int step, const GrayScott &sim, int rank, int numRanks);
    void close(int rank);

protected:
    Settings settings;
    
    vtkSmartPointer<vtkXMLPImageDataWriter> writer;
    vtkSmartPointer<vtkMPIController> controller;
};

#endif
