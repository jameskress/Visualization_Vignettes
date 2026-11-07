#include "writerKombyne.h"

#include <chrono>
#include <vector>
#include <conduit_relay_io.hpp>

WriterKombyne::WriterKombyne() = default;
WriterKombyne::~WriterKombyne() = default;

void WriterKombyne::CreateWriter(const Settings &_settings, const GrayScott &sim, MPI_Comm comm, int rank)
{
    settings = _settings;
    m_ghosts.build(sim);
    m_x = gs_mesh::axis_points(sim.offset_x, sim.size_x);
    m_y = gs_mesh::axis_points(sim.offset_y, sim.size_y);
    m_z = gs_mesh::axis_points(sim.offset_z, sim.size_z);

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

    // --- DATA PACKAGING (#23) ---
    // Same geometry and ownership as the shared Blueprint description
    // (mesh_blueprint.h), in Kombyne's own objects: a rectilinear grid over
    // the full ghosted array, u and v borrowed (KB_MEM_BORROW, no copy), and
    // the low-halo cells masked as ghosts in Kombyne's convention (0 =
    // ghost). The caller has refreshed the halo. The old adaptor copied u
    // and v without halos and built explicit per-point coordinates, which
    // left a one-cell gap between ranks.
    using clock = std::chrono::steady_clock;
    const auto t0 = clock::now();

    auto pipeline_data = kb_pipeline_data_alloc();
    kb_pipeline_data_set_promises(pipeline_data, KB_PROMISE_STATIC_FIELDS);

    const int px = static_cast<int>(sim.size_x + 2);
    const int py = static_cast<int>(sim.size_y + 2);
    const int pz = static_cast<int>(sim.size_z + 2);
    const int npts = px * py * pz;
    const int ncells = (px - 1) * (py - 1) * (pz - 1);

    auto rgrid = kb_rgrid_alloc();
    const int dims[3] = {px, py, pz};
    kb_rgrid_set_dims(rgrid, dims);

    auto hx = kb_var_alloc();
    auto hy = kb_var_alloc();
    auto hz = kb_var_alloc();
    kb_var_setd(hx, KB_MEM_BORROW, 1, px, m_x.data());
    kb_var_setd(hy, KB_MEM_BORROW, 1, py, m_y.data());
    kb_var_setd(hz, KB_MEM_BORROW, 1, pz, m_z.data());
    kb_rgrid_set_coords(rgrid, hx, hy, hz);

    auto hghost = kb_var_alloc();
    kb_var_setuc(hghost, KB_MEM_BORROW, 1, ncells, m_ghosts.kombyne_cells.data());
    kb_rgrid_set_ghost_cells(rgrid, hghost);

    auto fields = kb_fields_alloc();
    auto var_u = kb_var_alloc();
    auto var_v = kb_var_alloc();
    // Kombyne only reads them; its API takes non-const.
    kb_var_setd(var_u, KB_MEM_BORROW, 1, npts, const_cast<double *>(sim.u_ghost().data()));
    kb_var_setd(var_v, KB_MEM_BORROW, 1, npts, const_cast<double *>(sim.v_ghost().data()));
    kb_fields_add_var(fields, "U", KB_CENTERING_POINTS, var_u);
    kb_fields_add_var(fields, "V", KB_CENTERING_POINTS, var_v);
    kb_rgrid_set_fields(rgrid, fields);

    const double time = static_cast<double>(input_step) * settings.dt;
    kb_pipeline_data_add(pipeline_data, rank, numRanks, output_step, time, (kb_mesh_handle)rgrid);
    const auto t1 = clock::now();

    // Execute (Kombyne's own output happens inside).
    kb_simulation_execute(m_pipeline_collection, pipeline_data, KB_HANDLE_NULL);
    const auto t2 = clock::now();

    kb_pipeline_data_free(pipeline_data);

    phases.wrap_s = std::chrono::duration<double>(t1 - t0).count();
    phases.execute_s = std::chrono::duration<double>(t2 - t1).count();
    phases.io_s = 0.0;
    phases.split = true;
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
