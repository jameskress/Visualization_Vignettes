#include "writerKombyne.h"
#include <vector>

WriterKombyne::WriterKombyne() = default;
WriterKombyne::~WriterKombyne() = default;

void WriterKombyne::CreateWriter(const Settings &_settings, const GrayScott &sim, int rank)
{
    settings = _settings;
    // The main initialization happens in open(), where the MPI communicator is available.
}

void WriterKombyne::open(const std::string &fname, bool append, int rank)
{
    vtkLog(INFO, "Initializing Kombyne Lite Session");

    // Initialize the Kombyne Lite C API.
    MPI_Comm split_comm;
    kb_role role;
    kb_initialize(MPI_COMM_WORLD, "producer", "Gray-Scott Kombyne Producer",
                  KB_ROLE_SIMULATION_AND_ANALYSIS, 0, 0, "session.txt", &split_comm, &role);

    // Create and initialize a pipeline collection. This reads a configuration
    // file that tells Kombyne what in situ operations to perform.
    m_pipeline_collection = kb_pipeline_collection_alloc();
    
    // Use a setting consistent with other writers (e.g., catalyst_script_path)
    if (settings.kombynelite_script_path.empty())
    {
        vtkLog(WARNING, "Kombyne script path not specified in settings. In situ analysis may not occur.");
        return;
    }

    kb_pipeline_collection_set_filename(m_pipeline_collection, settings.kombynelite_script_path.c_str());
    if (kb_pipeline_collection_initialize(m_pipeline_collection) != KB_RETURN_OKAY)
    {
        vtkLog(ERROR, "Kombyne: Could not initialize pipeline using " << settings.kombynelite_script_path);
        kb_pipeline_collection_free(m_pipeline_collection);
        m_pipeline_collection = KB_HANDLE_NULL;
    }
}

void WriterKombyne::write(int step, const GrayScott &sim, int rank, int numRanks)
{
    if (m_pipeline_collection == KB_HANDLE_NULL)
    {
        return; // Kombyne failed to initialize, so we do nothing.
    }

    vtkLog(INFO, "Kombyne: Co-processing data for step " << step);

    // 1. Create a handle for this step's data payload.
    auto pipeline_data = kb_pipeline_data_alloc();
    kb_pipeline_data_set_promises(pipeline_data, KB_PROMISE_STATIC_FIELDS);

    // 2. Describe the grid as a structured grid.
    auto sgrid = kb_sgrid_alloc();
    // Explicitly cast from size_t to int to avoid narrowing warnings
    int nx = sim.size_x + 2, ny = sim.size_y + 2, nz = sim.size_z + 2;
    int dims[3] = {static_cast<int>(nx), 
                   static_cast<int>(ny), 
                   static_cast<int>(nz)};
    kb_sgrid_set_dims(sgrid, dims);

    // 3. Generate and attach the coordinates for the grid points.
    // Kombyne expects a flat array of {x1,y1,z1, x2,y2,z2, ...}.
    std::vector<float> coords;
    coords.reserve(nx * ny * nz * 3);
    for (int k = 0; k < nz; ++k) {
        for (int j = 0; j < ny; ++j) {
            for (int i = 0; i < nx; ++i) {
                coords.push_back(static_cast<float>(sim.offset_x + i));
                coords.push_back(static_cast<float>(sim.offset_y + j));
                coords.push_back(static_cast<float>(sim.offset_z + k));
            }
        }
    }
    auto hcoords = kb_var_alloc();
    // We use KB_MEM_COPY since the `coords` vector will be destroyed at the end of this function.
    kb_var_setf(hcoords, KB_MEM_COPY, 3, coords.size() / 3, coords.data());
    kb_sgrid_set_coords(sgrid, hcoords);

    // 4. Package the field data (U and V variables).
    auto fields = kb_fields_alloc();
    auto var_u = kb_var_alloc();
    auto var_v = kb_var_alloc();

    // Get the core data. The vectors must be non-const to get a non-const pointer.
    std::vector<double> u_data = sim.u_ghost();
    std::vector<double> v_data = sim.v_ghost();

    // The kb_var_setd function expects a non-const double*
    kb_var_setd(var_u, KB_MEM_BORROW, 1, u_data.size(), u_data.data());
    kb_var_setd(var_v, KB_MEM_BORROW, 1, v_data.size(), v_data.data());

    kb_fields_add_var(fields, "U", KB_CENTERING_POINTS, var_u);
    kb_fields_add_var(fields, "V", KB_CENTERING_POINTS, var_v);
    
    kb_sgrid_set_fields(sgrid, fields);

    // 5. Add the fully described mesh to the pipeline data for this step.
    double time = static_cast<double>(step) * settings.dt;
    kb_pipeline_data_add(pipeline_data, rank, numRanks, step, time, (kb_mesh_handle)sgrid);

    // 6. Execute the in situ step. This sends the data to the Kombyne endpoint.
    // We pass KB_HANDLE_NULL for the controls since we are not doing steering.
    kb_simulation_execute(m_pipeline_collection, pipeline_data, KB_HANDLE_NULL);

    // 7. Clean up the per-step data allocations.
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
