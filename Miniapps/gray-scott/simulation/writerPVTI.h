#ifndef __WRITERPVTI_H__
#define __WRITERPVTI_H__

#include "writer.h"
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
   
class WriterPVTI : public Writer
{
    void CreateWriter(const Settings &settings, const GrayScott &sim, int rank) override;
    void open(const std::string &fname, bool append, int rank) override;
    void write(int step, const GrayScott &sim, int rank, int numRanks) override;
    void close(int rank) override;
    void printSelf() override;
};

#endif
