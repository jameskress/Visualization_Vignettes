#include "writerKombyne.h"
#include <vector>
#include <conduit_relay_io.hpp>

WriterKombyne::WriterKombyne() = default;
WriterKombyne::~WriterKombyne() = default;

void WriterKombyne::CreateWriter(const Settings &_settings, const GrayScott &sim, MPI_Comm comm, int rank)
{
    settings = _settings;

    // Initialize the Kombyne Lite C API
    MPI_Comm split_comm;
    kb_role role;
    kb_initialize(comm, "producer", "Gray-Scott Kombyne Producer",
                  KB_ROLE_SIMULATION_AND_ANALYSIS, 0, 0, "session.txt", &split_comm, &role);
}

void WriterKombyne::open(const std::string &fname, bool append, int rank)
{
    vtkLog(INFO, "Initializing Kombyne Lite Session");

    // Allocate the pipeline collection
    m_pipeline_collection = kb_pipeline_collection_alloc();

    if (settings.kombynelite_script_path.empty())
    {
        vtkLog(WARNING, "Kombyne script path not specified. In situ analysis may not occur.");
        return;
    }

    std::string script_path = settings.kombynelite_script_path;

    kb_pipeline_collection_set_filename(m_pipeline_collection, script_path.c_str());

    if (kb_pipeline_collection_initialize(m_pipeline_collection) != KB_RETURN_OKAY)
    {
        vtkLog(ERROR, "Kombyne: Could not initialize pipeline using " << script_path);
        kb_pipeline_collection_free(m_pipeline_collection);
        m_pipeline_collection = KB_HANDLE_NULL;
    }
}

void WriterKombyne::write(int step, const GrayScott &sim, int rank, int numRanks)
{
    if (m_pipeline_collection == KB_HANDLE_NULL)
        return;

    // 1. I/O Control Variables
    int input_step = step;
    int output_step = input_step;

    if (settings.overwrite_last_step)
    {
        output_step = 0;
        if (rank == 0)
            vtkLog(INFO, "Kombyne: Executing OVERWRITE step " << input_step << " (Output Index: 0)");
    }
    else
    {
        if (rank == 0)
            vtkLog(INFO, "Kombyne: Co-processing data for step " << input_step);
    }

    bool is_plot_step = (step >= settings.burn_in_steps && step % settings.plotgap == 0);
    if (!is_plot_step)
        return;

    // --- DATA PACKAGING ---

    auto pipeline_data = kb_pipeline_data_alloc();
    kb_pipeline_data_set_promises(pipeline_data, KB_PROMISE_STATIC_FIELDS);

    auto sgrid = kb_sgrid_alloc();
    auto hcoords = kb_var_alloc();
    auto fields = kb_fields_alloc();
    auto var_u = kb_var_alloc();
    auto var_v = kb_var_alloc();

    // 2. Describe the structured grid (Use VALID dimensions, excluding ghosts)
    int nx = sim.size_x;
    int ny = sim.size_y;
    int nz = sim.size_z;
    int dims[3] = {nx, ny, nz};
    kb_sgrid_set_dims(sgrid, dims);

    // 3. Generate coordinates for VALID points only
    float spacing = 0.1f;
    std::vector<float> coords;
    coords.reserve(nx * ny * nz * 3);
    for (int k = 0; k < nz; ++k)
        for (int j = 0; j < ny; ++j)
            for (int i = 0; i < nx; ++i)
            {
                coords.push_back(static_cast<float>(sim.offset_x + i) * spacing);
                coords.push_back(static_cast<float>(sim.offset_y + j) * spacing);
                coords.push_back(static_cast<float>(sim.offset_z + k) * spacing);
            }

    kb_var_setf(hcoords, KB_MEM_COPY, 3, coords.size() / 3, coords.data());
    kb_sgrid_set_coords(sgrid, hcoords);

    // 4. Package the field data (Use NOGHOST data)
    // u_noghost() returns a copy of the data without the halo layers.
    std::vector<double> u_data = sim.u_noghost();
    std::vector<double> v_data = sim.v_noghost();

    kb_var_setd(var_u, KB_MEM_COPY, 1, u_data.size(), u_data.data());
    kb_var_setd(var_v, KB_MEM_COPY, 1, v_data.size(), v_data.data());

    kb_fields_add_var(fields, "U", KB_CENTERING_POINTS, var_u);
    kb_fields_add_var(fields, "V", KB_CENTERING_POINTS, var_v);
    kb_sgrid_set_fields(sgrid, fields);

    // 5. Add mesh to pipeline data
    double time = static_cast<double>(input_step) * settings.dt;
    kb_pipeline_data_add(pipeline_data, rank, numRanks, output_step, time, (kb_mesh_handle)sgrid);

    // 6. Execute
    kb_simulation_execute(m_pipeline_collection, pipeline_data, KB_HANDLE_NULL);

    kb_pipeline_data_free(pipeline_data);
}

void WriterKombyne::close(int rank)
{
    vtkLog(INFO, "Finalizing Kombyne Session");
    if (m_pipeline_collection != KB_HANDLE_NULL)
    {
        kb_pipeline_collection_free(m_pipeline_collection);
        m_pipeline_collection = KB_HANDLE_NULL;
    }
    kb_finalize();
}

void WriterKombyne::printSelf()
{
    vtkLog(INFO, "This is writer type Kombyne");
}
