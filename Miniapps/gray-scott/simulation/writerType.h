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

// Always include VTK writer
#include "../../gray-scott/simulation/writerPVTI.h"

#ifdef USE_CATALYST
#include "../../gray-scott/simulation/writerCatalyst.h"
#endif

#ifdef USE_ASCENT
#include "../../gray-scott/simulation/writerAscent.h"
#endif

#ifdef USE_ADIOS2
#include "../../gray-scott/simulation/writerADIOS.h"
#endif

class WriterType
{
public:
    enum EWriterType
    {
        WRITER_TYPE_PVTI = 0,
    #ifdef USE_CATALYST
        WRITER_TYPE_CATALYST = 1,
    #endif
    #ifdef USE_ASCENT
        WRITER_TYPE_ASCENT = 2,
    #endif
    #ifdef USE_ADIOS2
        WRITER_TYPE_ADIOS = 3 
    #endif
    };

    static std::shared_ptr<Writer> Create(EWriterType type)
    {
        switch (type)
        {
        case WRITER_TYPE_PVTI:
            return std::make_shared<WriterPVTI>();

        #ifdef USE_CATALYST
        case WRITER_TYPE_CATALYST:
            return std::make_shared<WriterCatalyst>();
        #endif

        #ifdef USE_ASCENT
        case WRITER_TYPE_ASCENT:
            return std::make_shared<WriterAscent>();
        #endif

        #ifdef USE_ADIOS2
        case WRITER_TYPE_ADIOS:
            return std::make_shared<WriterADIOS>();
        #endif

        default:
            return nullptr;
        }
    }
};

#endif
