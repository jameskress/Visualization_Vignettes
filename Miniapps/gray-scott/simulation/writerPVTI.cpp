#include "writerPVTI.h"
#include <vtkImageAlgorithm.h>
#include <vtkInformation.h>
#include <vtkInformationVector.h>
#include <vtkStreamingDemandDrivenPipeline.h>
#include <vtkCellData.h>
#include <vtkDataSetAttributes.h>
#include <vtkUnsignedCharArray.h>

#include <chrono>

//--------------------------------------------------------------
//  image source
//--------------------------------------------------------------

class ImageSource : public vtkImageAlgorithm
{
public:
    ImageSource(int L, const GrayScott &sim, const gs_mesh::Ghosts &ghosts, int rank);
    // Time spent building the vtkImageData in the last pipeline update (s).
    double wrap_seconds() const { return wrap_s_; }

private:
    double origin_[3], spacing_[3];
    int wholeExtent_[6], localExtent_[6];
    int L_;
    int rank_;
    const GrayScott &sim_;
    double wrap_s_ = 0.0;

    const gs_mesh::Ghosts &ghosts_;

    void setWholeExtent(int x1, int x2, int y1, int y2, int z1, int z2);
    void setLocalExtent(int x1, int x2, int y1, int y2, int z1, int z2);
    void setOrigin(double ox, double oy, double oz);
    void setSpacing(double sx, double sy, double sz);

    int RequestInformation(vtkInformation *, vtkInformationVector **, vtkInformationVector *outputVector);

    void ExecuteDataWithInformation(vtkDataObject *, vtkInformation *outInfo);

    int FillOutputPortInformation(int port, vtkInformation *info);
};

ImageSource::ImageSource(int L, const GrayScott &sim, const gs_mesh::Ghosts &ghosts, int rank)
    : L_(L), rank_(rank), sim_(sim), ghosts_(ghosts)
{
    // Same geometry as the shared Blueprint description (mesh_blueprint.h,
    // #23): the full ghosted block, local point i at global index
    // offset + i - 1, spacing 0.1. Extents are in global point indices, so
    // the halo layers sit at -1 and L in the whole extent. (The old writer
    // put the block one point too far up and flagged no ghosts.)
    this->setOrigin(0.0, 0.0, 0.0);
    this->setSpacing(gs_mesh::kSpacing, gs_mesh::kSpacing, gs_mesh::kSpacing);
    const int x0 = static_cast<int>(sim_.offset_x) - 1;
    const int y0 = static_cast<int>(sim_.offset_y) - 1;
    const int z0 = static_cast<int>(sim_.offset_z) - 1;
    this->setLocalExtent(x0, x0 + static_cast<int>(sim_.size_x) + 1, y0,
                         y0 + static_cast<int>(sim_.size_y) + 1, z0,
                         z0 + static_cast<int>(sim_.size_z) + 1);
    this->setWholeExtent(-1, this->L_, -1, this->L_, -1, this->L_);
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

    vtkDataObject::SetPointDataActiveScalarInfo(outInfo, VTK_DOUBLE, 1);

    outInfo->Set(CAN_PRODUCE_SUB_EXTENT(), 1);

    return 1;
}

/**
 * Converting double result to float to save space
 */
void ImageSource::ExecuteDataWithInformation(vtkDataObject *, vtkInformation *outInfo)
{
    const auto t0 = std::chrono::steady_clock::now();
    vtkImageData *imageData = vtkImageData::GetData(outInfo);
    imageData->SetExtent(localExtent_);
    imageData->SetSpacing(spacing_);
    imageData->SetOrigin(origin_);

    // u and v are the solver's own arrays (SetArray with save = 1: VTK
    // borrows them and never frees them), written as doubles. The ghost
    // flags are borrowed the same way.
    const vtkIdType npts = static_cast<vtkIdType>(sim_.u_ghost().size());
    auto var_u = vtkSmartPointer<vtkDoubleArray>::New();
    var_u->SetName("u");
    var_u->SetArray(const_cast<double *>(sim_.u_ghost().data()), npts, 1);
    auto var_v = vtkSmartPointer<vtkDoubleArray>::New();
    var_v->SetName("v");
    var_v->SetArray(const_cast<double *>(sim_.v_ghost().data()), npts, 1);
    auto ghost_pts = vtkSmartPointer<vtkUnsignedCharArray>::New();
    ghost_pts->SetName(vtkDataSetAttributes::GhostArrayName());
    ghost_pts->SetArray(const_cast<unsigned char *>(ghosts_.vtk_points.data()), npts, 1);
    auto ghost_cells = vtkSmartPointer<vtkUnsignedCharArray>::New();
    ghost_cells->SetName(vtkDataSetAttributes::GhostArrayName());
    ghost_cells->SetArray(const_cast<unsigned char *>(ghosts_.vtk_cells.data()),
                          static_cast<vtkIdType>(ghosts_.vtk_cells.size()), 1);

    imageData->GetPointData()->AddArray(var_u);
    imageData->GetPointData()->AddArray(var_v);
    imageData->GetPointData()->AddArray(ghost_pts);
    imageData->GetCellData()->AddArray(ghost_cells);
    wrap_s_ = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
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
    ghosts.build(sim);
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
    ImageSource *source = new ImageSource(int(settings.L), sim, ghosts, rank);
    vtkLogEndScope("Creating custom ImageSource object");

    // =================================================================
    // LOGIC: Overwrite Logic (Filename Masking)
    // =================================================================

    // 1. Determine the Step Index
    // If we want to overwrite, we force the index to 0.
    // This ensures the filename string is identical every time (e.g. "output-0000.pvti")
    int file_step_idx = (settings.overwrite_last_step) ? 0 : step;

    // 2. Prepare the Filename Pattern
    std::string fmt = settings.output_file_name;

    // Simple fix: Replace "ts" with "d" if it looks like a format specifier
    size_t pos = fmt.find("ts");
    if (pos != std::string::npos && pos > 0)
    {
        // Replace 'ts' with 'd' (e.g., %04ts -> %04d)
        fmt.replace(pos, 2, "d");
    }

    // Ensure the extension is .pvti for parallel writing
    size_t ext_pos = fmt.rfind(".vti");
    if (ext_pos != std::string::npos)
    {
        fmt.replace(ext_pos, 4, ".pvti");
    }

    // 3. Generate the Filename
    char filename[1024];
    snprintf(filename, sizeof(filename), fmt.c_str(), file_step_idx);

    // =================================================================

    writer->SetFileName(filename);
    writer->SetInputConnection(source->GetOutputPort());
    writer->SetNumberOfPieces(numRanks);
    writer->SetStartPiece(rank);
    writer->SetEndPiece(rank);
    writer->SetGhostLevel(0);

    writer->SetUseSubdirectory(true);

    writer->SetCompressorTypeToNone();
    // Wrap is the image build inside the pipeline update; the rest of
    // Write() is file I/O (and the rank 0 .pvti header).
    const auto t0 = std::chrono::steady_clock::now();
    writer->Write();
    const double total = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    phases.wrap_s = source->wrap_seconds();
    phases.execute_s = 0.0;
    phases.io_s = total - phases.wrap_s;
    phases.split = true;

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
