#include "../../gray-scott/simulation/writer.h"

Writer::Writer(const Settings &settings, const GrayScott &sim, int rank)
: settings(settings)
{
    vtkLog(INFO, "" << rank);
    controller = static_cast<vtkMPIController*>(vtkMultiProcessController::GetGlobalController());
    if (!controller)
    {
        vtkLog(INFO,"" <<  rank);
        controller = vtkMPIController::New();
        controller->Initialize();
        vtkMultiProcessController::SetGlobalController(controller);
        vtkLog(INFO, "Finished creating vtkMPIController");
    }    
}

void Writer::open(const std::string &fname, bool append, int rank)
{
    vtkLog(INFO, "" << rank);
    writer = vtkSmartPointer<vtkXMLPImageDataWriter>::New();   
    writer->SetController(controller); 
}

void Writer::write(int step, const GrayScott &sim, int rank, int numRanks)
{
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

    vtkSmartPointer<vtkImageData> imageData = vtkSmartPointer<vtkImageData>::New();
    imageData->SetExtent(localExtent);
    imageData->SetSpacing(0.1,0.1,0.1);
    imageData->SetOrigin(0.0,0.0,0.0);

    vtkSmartPointer<vtkDoubleArray> var_u = vtkSmartPointer<vtkDoubleArray>::New();
    var_u->SetNumberOfComponents(1);
    var_u->SetNumberOfTuples(nx * ny * nz);

    vtkSmartPointer<vtkDoubleArray> var_v = vtkSmartPointer<vtkDoubleArray>::New();
    var_v->SetNumberOfComponents(1);
    var_v->SetNumberOfTuples(nx * ny * nz);

    std::vector<double> u = sim.u_ghost();
    std::vector<double> v = sim.v_ghost();
    //std::vector<double> u = sim.u_noghost();
    //std::vector<double> v = sim.v_noghost();

    for (int i = 0; i < var_v->GetNumberOfTuples(); ++i) {
        var_v->SetValue(i, v[i]);
        var_u->SetValue(i, u[i]);
        //std::cout << "writing data values " << v[i] << " " << u[i] << std::endl;
    }

    imageData->GetPointData()->AddArray(var_u);
    imageData->GetPointData()->AddArray(var_v);
    var_v->SetName("v");
    var_u->SetName("u");


    vtkLog(INFO, "" << rank);
    char str[1024];
    //sprintf(str, "grayScott_ts-%05d_rank-%05d.vti", step, rank);
    sprintf(str, "grayScott_step-%06d.pvti", step);
    writer->SetFileName(str);
    vtkLog(INFO, "" << rank);
    writer->SetNumberOfPieces(numRanks);
    writer->SetStartPiece(rank);
    writer->SetEndPiece(rank);
    writer->SetGhostLevel(0);
    writer->SetUseSubdirectory(true);
    writer->SetInputData(imageData);
    //writer->WriteSummaryFileOff();
    writer->Update();
    //writer->UpdateExtent(wholeExtent);
    //writer->UpdateWholeExtent();
    //writer->PropagateUpdateExtent();
    vtkLog(INFO, "" << rank);
    writer->Update();
    vtkLog(INFO, "" << rank);
    writer->Write();
    vtkLog(INFO, "" << rank);
}

void Writer::close(int rank) 
{
    vtkLog(INFO, "" << rank);
}
