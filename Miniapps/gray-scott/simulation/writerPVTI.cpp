#include "writerPVTI.h"
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
    ImageSource(int L, const GrayScott &sim, int rank);

private:
    double origin_[3], spacing_[3];
    int wholeExtent_[6], localExtent_[6];
    int L_;
    int rank_;
    const GrayScott &sim_;

    vtkSmartPointer<vtkFloatArray> var_u;
    vtkSmartPointer<vtkFloatArray> var_v;

    void setWholeExtent(int x1, int x2, int y1, int y2, int z1, int z2);
    void setLocalExtent(int x1, int x2, int y1, int y2, int z1, int z2);
    void setOrigin(double ox, double oy, double oz);
    void setSpacing(double sx, double sy, double sz);

    int RequestInformation(vtkInformation *, vtkInformationVector **, vtkInformationVector *outputVector);

    void ExecuteDataWithInformation(vtkDataObject *, vtkInformation *outInfo);

    int FillOutputPortInformation(int port, vtkInformation *info);
};

ImageSource::ImageSource(int L, const GrayScott &sim, int rank) : L_(L), sim_(sim), rank_(rank)
{
    this->setOrigin(0.0, 0.0, 0.0);
    this->setSpacing(0.1, 0.1, 0.1);

    int nx = sim_.size_x + 2, ny = sim_.size_y + 2, nz = sim_.size_z + 2;
    int dx = sim_.offset_x, dy = sim_.offset_y, dz = sim_.offset_z;
    this->setLocalExtent(0 + dx, nx - 1 + dx, 0 + dy, ny - 1 + dy, 0 + dz, nz - 1 + dz);
    this->setWholeExtent(0, this->L_, 0, this->L_, 0, this->L_);

    vtkLog(TRACE, "rank_" << this->rank_ << " :: offsets " << sim_.offset_x << " " << sim_.offset_y << " " << sim_.offset_z);
    vtkLog(TRACE, "rank_" << this->rank_ << " :: local dims " << localExtent_[0] << " "
                          << localExtent_[1] << " "
                          << localExtent_[2] << " "
                          << localExtent_[3] << " "
                          << localExtent_[4] << " "
                          << localExtent_[5]);
    vtkLog(TRACE, "rank_" << this->rank_ << " :: global dims " << wholeExtent_[0] << " "
                          << wholeExtent_[1] << " "
                          << wholeExtent_[2] << " "
                          << wholeExtent_[3] << " "
                          << wholeExtent_[4] << " "
                          << wholeExtent_[5]);

    vtkLog(TRACE, "");

    var_u = vtkSmartPointer<vtkFloatArray>::New();
    var_v = vtkSmartPointer<vtkFloatArray>::New();

    vtkLog(TRACE, "");

    this->var_u->SetNumberOfComponents(1);
    this->var_u->SetNumberOfTuples(nx * ny * nz);

    vtkLog(TRACE, "");

    this->var_v->SetNumberOfComponents(1);
    this->var_v->SetNumberOfTuples(nx * ny * nz);

    vtkLog(TRACE, "");

    this->SetNumberOfInputPorts(0);
}

void ImageSource::setOrigin(double ox, double oy, double oz)
{
    this->origin_[0] = ox;
    this->origin_[1] = oy;
    this->origin_[2] = oz;
}

void ImageSource::setSpacing(double sx, double sy, double sz)
{
    this->spacing_[0] = sx;
    this->spacing_[1] = sy;
    this->spacing_[2] = sz;
}

void ImageSource::setLocalExtent(int x1, int x2, int y1, int y2, int z1, int z2)
{
    this->localExtent_[0] = x1;
    this->localExtent_[1] = x2;
    this->localExtent_[2] = y1;
    this->localExtent_[3] = y2;
    this->localExtent_[4] = z1;
    this->localExtent_[5] = z2;
}

void ImageSource::setWholeExtent(int x1, int x2, int y1, int y2, int z1, int z2)
{
    this->wholeExtent_[0] = x1;
    this->wholeExtent_[1] = x2;
    this->wholeExtent_[2] = y1;
    this->wholeExtent_[3] = y2;
    this->wholeExtent_[4] = z1;
    this->wholeExtent_[5] = z2;
}
int ImageSource::RequestInformation(vtkInformation *, vtkInformationVector **, vtkInformationVector *outputVector)
{
    vtkInformation *outInfo = outputVector->GetInformationObject(0);

    outInfo->Set(vtkStreamingDemandDrivenPipeline::WHOLE_EXTENT(), wholeExtent_, 6);
    outInfo->Set(vtkDataObject::ORIGIN(), origin_, 3);
    outInfo->Set(vtkDataObject::SPACING(), spacing_, 3);
    outInfo->Set(vtkStreamingDemandDrivenPipeline::UPDATE_EXTENT(), localExtent_, 6);

    // log object info
    std::stringstream streamOut;
    outInfo->Print(streamOut);
    vtkLog(MAX, "" << streamOut.str());

    vtkDataObject::SetPointDataActiveScalarInfo(outInfo, VTK_FLOAT, 1);

    outInfo->Set(CAN_PRODUCE_SUB_EXTENT(), 1);

    return 1;
}

/**
 * Converting double result to float to save space
*/
void ImageSource::ExecuteDataWithInformation(vtkDataObject *, vtkInformation *outInfo)
{
    vtkImageData *imageData = vtkImageData::GetData(outInfo);
    imageData->SetExtent(localExtent_);
    imageData->SetSpacing(spacing_);
    imageData->SetOrigin(origin_);

    std::vector<double> u = sim_.u_ghost();
    std::vector<double> v = sim_.v_ghost();
    // std::vector<double> u = sim.u_noghost();
    // std::vector<double> v = sim.v_noghost();

    for (int i = 0; i < u.size(); i++)
    {
        this->var_v->SetValue(i, (float)v[i]);
        this->var_u->SetValue(i, (float)u[i]);
    }

    this->var_v->SetName("v");
    this->var_u->SetName("u");

    // log object info
    std::stringstream streamOut;
    imageData->Print(streamOut);
    vtkLog(MAX, "" << streamOut.str());

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
void WriterPVTI::CreateWriter(const Settings &_settings, const GrayScott &sim, MPI_Comm comm, int rank)
{
    settings = _settings;
    vtkLog(TRACE, "");
    controller = static_cast<vtkMPIController *>(vtkMultiProcessController::GetGlobalController());
    if (!controller)
    {
        vtkLog(TRACE, "");
        controller = vtkSmartPointer<vtkMPIController>::New();
        controller->Initialize();
        vtkMultiProcessController::SetGlobalController(controller);
        vtkLog(TRACE, "Finished creating vtkMPIController");
    }
}

void WriterPVTI::open(const std::string &fname, bool append, int rank)
{
    writer = vtkSmartPointer<vtkXMLPImageDataWriter>::New();
    writer->SetController(controller);
    vtkLog(TRACE, "Finished opening vtkXMLPImageDataWriter");
}

void WriterPVTI::write(int step, const GrayScott &sim, int rank, int numRanks)
{
    vtkLogStartScope(TRACE, "Writing: VTK");
    if (!sim.size_x || !sim.size_y || !sim.size_z)
    {
        return;
    }

    vtkLogStartScope(TRACE, "Creating custom ImageSource object");
    ImageSource *source = new ImageSource(int(settings.L), sim, rank);
    vtkLogEndScope("Creating custom ImageSource object");

    char str[1024];
    sprintf(str, "grayScott_step-%06d.pvti", step);

    writer->SetFileName(str);
    writer->SetInputConnection(source->GetOutputPort());
    writer->SetNumberOfPieces(numRanks);
    writer->SetStartPiece(rank);
    writer->SetEndPiece(rank);
    writer->SetGhostLevel(0);
    writer->SetUseSubdirectory(true);
    writer->SetCompressorTypeToNone();
    writer->Write();
    vtkLogEndScope("Writing: VTK");

    source->Delete();
}

void WriterPVTI::close(int rank)
{
    vtkLog(TRACE, "");
}

void WriterPVTI::printSelf()
{
    vtkLog(TRACE, "This is writer type PVTI ");
}
