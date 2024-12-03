#ifndef __WRITERTYPE_H__
#define __WRITERTYPE_H__

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

/* TODO later*/
// #ifdef USE_CATALYST
#include "../../gray-scott/simulation/writerCatalyst.h"
// #endif

/* TODO later*/
// #ifdef USE_VTK
#include "../../gray-scott/simulation/writerPVTI.h"
// #endif

class WriterType
{
public:
    enum EWriterType
    {
        WRITER_TYPE_PVTI = 0,
        WRITER_TYPE_CATALYST = 1
    };

    static std::shared_ptr<Writer> Create(EWriterType type)
    {
        switch (type)
        {
        case WRITER_TYPE_PVTI:
            return std::shared_ptr<Writer>(new WriterPVTI());
            break;
        case WRITER_TYPE_CATALYST:
            return std::shared_ptr<Writer>(new WriterCatalyst());
            break;
        default:
            return nullptr;
        }
    }
};

#endif
