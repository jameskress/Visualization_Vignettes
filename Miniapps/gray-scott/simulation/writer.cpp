#include "../../gray-scott/simulation/writer.h"

#include <vtkImageAlgorithm.h>
#include <vtkInformation.h>
#include <vtkInformationVector.h>
#include <vtkStreamingDemandDrivenPipeline.h>

//--------------------------------------------------------------
//  image source
//--------------------------------------------------------------

class ImageSource : public vtkImageAlgorithm
{
public:
    ImageSource();
    void setWholeExtent(const int *const extent);
    void setLocalExtent(const int *const extent);
    //void setOrigin(const double *const origin);
    //void setSpacing(const double *const spacing);

    vtkSmartPointer<vtkDoubleArray> var_u;
    vtkSmartPointer<vtkDoubleArray> var_v;

private:
    double origin_[3], spacing_[3];
    int wholeExtent_[6], localExtent_[6];

    int RequestInformation(vtkInformation *, vtkInformationVector **, vtkInformationVector *outputVector);

    void ExecuteDataWithInformation(vtkDataObject *, vtkInformation *outInfo);

    int FillOutputPortInformation(int port, vtkInformation *info);
};

ImageSource::ImageSource()
{
    origin_[0] = 0.0;
    origin_[1] = 0.0;
    origin_[2] = 0.0;
    spacing_[0] = 0.1;
    spacing_[1] = 0.1;
    spacing_[2] = 0.1;

    var_u = vtkSmartPointer<vtkDoubleArray>::New();
    var_v = vtkSmartPointer<vtkDoubleArray>::New();

    this->SetNumberOfInputPorts(0);
}

void ImageSource::setLocalExtent(const int *const extent)
{
    for (int i = 0; i < 6; i++)
        localExtent_[i] = extent[i];
}

void ImageSource::setWholeExtent(const int *const extent)
{
    for (int i = 0; i < 6; i++)
        wholeExtent_[i] = extent[i];
}
int ImageSource::RequestInformation(vtkInformation *, vtkInformationVector **, vtkInformationVector *outputVector)
{
    vtkInformation *outInfo = outputVector->GetInformationObject(0);

    outInfo->Set(vtkStreamingDemandDrivenPipeline::WHOLE_EXTENT(), wholeExtent_, 6);
    outInfo->Set(vtkDataObject::ORIGIN(), origin_, 3);
    outInfo->Set(vtkDataObject::SPACING(), spacing_, 3);
    outInfo->Set(vtkStreamingDemandDrivenPipeline::UPDATE_EXTENT(), localExtent_, 6);

    //vtkIndent indent;
    //outInfo->PrintSelf(std::cout, indent.GetNextIndent());

    vtkDataObject::SetPointDataActiveScalarInfo(outInfo, VTK_FLOAT, 1);

    outInfo->Set(CAN_PRODUCE_SUB_EXTENT(), 1);

    return 1;
}

void ImageSource::ExecuteDataWithInformation(vtkDataObject *, vtkInformation *outInfo)
{
    int *execExt = outInfo->Get(vtkStreamingDemandDrivenPipeline::UPDATE_EXTENT());

    vtkImageData *imageData = vtkImageData::GetData(outInfo);
    imageData->SetExtent(localExtent_);
    imageData->SetSpacing(spacing_);
    imageData->SetOrigin(origin_);

    //vtkIndent indent;
    //imageData->PrintSelf(std::cout, indent.GetNextIndent());

    imageData->GetPointData()->AddArray(var_u);
    imageData->GetPointData()->AddArray(var_v);
}

int ImageSource::FillOutputPortInformation(int port, vtkInformation *info)
{
    if (port == 0)
        return vtkImageAlgorithm::FillOutputPortInformation(port, info);

    return 0;
}

//--------------------------------------------------------------
//  Writer
//--------------------------------------------------------------

Writer::Writer(const Settings &settings, const GrayScott &sim, int rank)
    : settings(settings)
{
    vtkLog(TRACE, "");
    controller = static_cast<vtkMPIController*>(vtkMultiProcessController::GetGlobalController());
    if (!controller)
    {
        vtkLog(INFO, "" << rank);
        controller = vtkMPIController::New();
        controller->Initialize();
        vtkMultiProcessController::SetGlobalController(controller);
        vtkLog(TRACE, "Finished creating vtkMPIController");
    }    
}

void Writer::open(const std::string &fname, bool append, int rank)
{
    vtkLog(TRACE, "");
    writer = vtkSmartPointer<vtkXMLPImageDataWriter>::New();   
    writer->SetController(controller); 
}

void Writer::write(int step, const GrayScott &sim, int rank, int numRanks)
{
    vtkLogStartScope(INFO, "Starting Write: VTK");
    if (!sim.size_x || !sim.size_y || !sim.size_z)
    {
        return;
    }

    int nx = sim.size_x + 2, ny = sim.size_y + 2, nz = sim.size_z + 2;
    int dx = sim.offset_x, dy = sim.offset_y, dz = sim.offset_z;
    int localExtent[6] = {0 + dx, nx - 1 + dx, 0 + dy, ny - 1 + dy, 0 + dz, nz - 1 + dz};
    int wholeExtent[6] = {0, settings.L + 1, 0, settings.L + 1, 0, settings.L + 1};

    vtkLog(INFO, "rank_" << rank << " :: offsets " << sim.offset_x << " " << sim.offset_y << " " << sim.offset_z);
    vtkLog(INFO, "rank_" << rank << " :: local dims " << localExtent[0] << " "
                         << localExtent[1] << " "
                         << localExtent[2] << " "
                         << localExtent[3] << " "
                         << localExtent[4] << " "
                         << localExtent[5]);
    vtkLog(INFO, "rank_" << rank << " :: global dims " << wholeExtent[0] << " "
                         << wholeExtent[1] << " "
                         << wholeExtent[2] << " "
                         << wholeExtent[3] << " "
                         << wholeExtent[4] << " "
                         << wholeExtent[5]);

    vtkSmartPointer<ImageSource> source = new ImageSource;
    source->setLocalExtent(localExtent);
    source->setWholeExtent(wholeExtent);

    source->var_u->SetNumberOfComponents(1);
    source->var_u->SetNumberOfTuples(nx * ny * nz);

    source->var_v->SetNumberOfComponents(1);
    source->var_v->SetNumberOfTuples(nx * ny * nz);

    std::vector<double> u = sim.u_ghost();
    std::vector<double> v = sim.v_ghost();
    // std::vector<double> u = sim.u_noghost();
    // std::vector<double> v = sim.v_noghost();

    for (int i = 0; i < source->var_v->GetNumberOfTuples(); ++i)
    {
        source->var_v->SetValue(i, v[i]);
        source->var_u->SetValue(i, u[i]);
        // std::cout << "writing data values " << v[i] << " " << u[i] << std::endl;
    }

    source->var_v->SetName("v");
    source->var_u->SetName("u");

    vtkLog(TRACE, "");
    char str[1024];
    // sprintf(str, "grayScott_ts-%05d_rank-%05d.vti", step, rank);
    sprintf(str, "grayScott_step-%06d.pvti", step);

    writer->SetFileName(str);
    writer->SetInputConnection(source->GetOutputPort());
    writer->SetNumberOfPieces(numRanks);
    writer->SetStartPiece(rank);
    writer->SetEndPiece(rank);
    writer->SetUseSubdirectory(true);
    writer->Write();

    // writer->SetFileName(str);
    // vtkLog(INFO, "" << rank);
    // writer->SetNumberOfPieces(numRanks);
    // writer->SetStartPiece(rank);
    // writer->SetEndPiece(rank);
    // writer->SetGhostLevel(0);
    // writer->SetUseSubdirectory(true);
    // writer->SetInputData(imageData);
    // //writer->WriteSummaryFileOff();
    // writer->Update();
    // writer->UpdateExtent(wholeExtent);
    // //writer->UpdateWholeExtent();
    // //writer->PropagateUpdateExtent();
    // vtkLog(INFO, "" << rank);
    // writer->Update();
    // vtkLog(INFO, "" << rank);
    // writer->Write();
    // vtkLog(INFO, "" << rank);
}

void Writer::close(int rank)
{
    vtkLog(TRACE, "");
}
