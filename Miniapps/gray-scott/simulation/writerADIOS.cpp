#include "writerADIOS.h"
#include "mesh_blueprint.h"

#include <algorithm>
#include <cctype>
#include <chrono>

WriterADIOS::WriterADIOS() = default;
WriterADIOS::~WriterADIOS() = default;

void WriterADIOS::CreateWriter(const Settings &_settings, const GrayScott &sim, MPI_Comm comm, int rank)
{
    settings = _settings;

    // Span and memory selection are checked with BP5 only. With SST they are
    // untested here and reported not to work (span Put unsupported; FFS
    // marshalling may ignore the memory selection), so SST uses the default
    // mode until the in transit path is tested in phase 5 (#42).
    std::string engine = m_io.EngineType();
    std::transform(engine.begin(), engine.end(), engine.begin(), ::tolower);
    if (engine == "sst" && (settings.adios_span || settings.adios_memory_selection))
    {
        if (rank == 0)
            vtkLog(WARNING, "ADIOS2: adios_span and adios_memory_selection are not supported with SST; "
                            "using the default write mode");
        settings.adios_span = false;
        settings.adios_memory_selection = false;
    }

    // --- DEFINE THE SIMULATION VARIABLES ---
    const adios2::Dims shape = {settings.L, settings.L, settings.L};

    // The starting offset of this rank's block within the global domain
    // NOTE: ADIOS2 expects Z, Y, X order
    const adios2::Dims start = {sim.offset_z, sim.offset_y, sim.offset_x};
    const adios2::Dims count = {sim.size_z, sim.size_y, sim.size_x};

    m_var_u = m_io.DefineVariable<double>("U", shape, start, count, adios2::ConstantDims);
    m_var_v = m_io.DefineVariable<double>("V", shape, start, count, adios2::ConstantDims);
    m_var_step = m_io.DefineVariable<int>("step");

    // --- CONDITIONALLY Configure Memory Selection ---
    // Only set the complex memory layout if the user has requested mem selection
    if (settings.adios_memory_selection)
    {
        vtkLog(INFO, "ADIOS2 writer configured for high-performance memory selection (zero-copy) mode.");
        const adios2::Dims memory_start = {1, 1, 1};
        const adios2::Dims memory_count = {sim.size_z + 2, sim.size_y + 2, sim.size_x + 2};
        const adios2::Box<adios2::Dims> mem_selection(memory_start, memory_count);

        m_var_u.SetMemorySelection(mem_selection);
        m_var_v.SetMemorySelection(mem_selection);
    }
}

void WriterADIOS::SetADIOS(adios2::ADIOS &adios)
{
    // Initialize the IO object using the ADIOS instance from main()
    m_io = adios.DeclareIO("SimulationOutput");
}

void WriterADIOS::open(const std::string &fname, bool append, int rank)
{
    vtkLog(INFO, "Opening ADIOS2 writer for file: " << fname);
    // Removed the engine type setting to allow runtime configuration from XML file
    // m_io.SetEngine("BP5");

    m_fname = fname;

    // --- DEFINE SIMULATION PARAMETERS AS ATTRIBUTES ---
    m_io.DefineAttribute<double>("F", settings.F);
    m_io.DefineAttribute<double>("k", settings.k);
    m_io.DefineAttribute<double>("dt", settings.dt);
    m_io.DefineAttribute<double>("Du", settings.Du);
    m_io.DefineAttribute<double>("Dv", settings.Dv);
    m_io.DefineAttribute<double>("noise", settings.noise);
    m_io.DefineAttribute<std::string>("adios_config", settings.adios_config);
    m_io.DefineAttribute<std::string>(
        "adios_span", settings.adios_span ? "true" : "false");
    m_io.DefineAttribute<std::string>(
        "adios_memory_selection", settings.adios_memory_selection ? "true" : "false");

    // --- DEFINE THE FIDES DATA MODEL METADATA ---
    // Ghost and ownership metadata (#22). U and V are global L^3 arrays of
    // owned points only: every global point is stored exactly once, by the
    // rank that owns it, and no halo is written, so there is nothing for a
    // reader to deduplicate. A reader that builds one mesh per block must
    // read one extra layer itself (wrapping, since the domain is periodic)
    // to close the one-cell gap between blocks, and flag that layer as
    // ghost. The geometry matches the shared mesh description
    // (mesh_blueprint.h): global point i at i * 0.1.
    m_io.DefineAttribute<std::string>("gs_point_ownership", "each global point stored once");
    m_io.DefineAttribute<int>("gs_halo_layers_written", 0);
    const std::vector<int> periodic = {1, 1, 1};
    m_io.DefineAttribute<int>("gs_periodic", periodic.data(), periodic.size());
    m_io.DefineAttribute<std::string>("gs_ghost_policy",
                                      "readers add their own overlap layer and flag it ghost");

    m_io.DefineAttribute<std::string>("Fides_Data_Model", "uniform");

    const std::vector<double> origin = {0.0, 0.0, 0.0};
    const std::vector<double> spacing = {gs_mesh::kSpacing, gs_mesh::kSpacing, gs_mesh::kSpacing};
    m_io.DefineAttribute<double>("Fides_Origin", origin.data(), origin.size());
    m_io.DefineAttribute<double>("Fides_Spacing", spacing.data(), spacing.size());

    // --- ASSOCIATE VARIABLES WITH THE FIDES MODEL ---
    m_io.DefineAttribute<std::string>("Fides_Dimension_Variable", "U");
    const std::vector<std::string> var_list = {"U", "V"};
    m_io.DefineAttribute<std::string>("Fides_Variable_List", var_list.data(), var_list.size());
    const std::vector<std::string> associations = {"points", "points"};
    m_io.DefineAttribute<std::string>("Fides_Variable_Associations", associations.data(), associations.size());

    // --- OPEN THE ADIOS ENGINE ---
    const adios2::Mode mode = append ? adios2::Mode::Append : adios2::Mode::Write;
    m_engine = m_io.Open(fname, mode);
}

void WriterADIOS::write(int step, const GrayScott &sim, int rank, int numRanks)
{
    vtkLog(INFO, "ADIOS2 Writing step: " << step);

    if (!m_engine)
    {
        vtkLog(ERROR, "ADIOS2 engine is not initialized. Cannot write data.");
        return;
    }

    using clock = std::chrono::steady_clock;
    const auto t0 = clock::now();

    // --- OVERWRITE MODE: CLOSE & REOPEN EACH WRITE (counted as io) ---
    if (settings.overwrite_last_step)
    {
        if (m_engine)
        {
            m_engine.Close();
        }
        m_engine = m_io.Open(m_fname, adios2::Mode::Write);
    }
    const auto t_reopen = clock::now();

    // Pointer lifetime (#22). Put() is deferred by default: ADIOS2 may read
    // the memory at Put() or at any point up to EndStep(). Every pointer handed to Put() below
    // must stay valid and unchanged until EndStep() returns:
    //  * memory selection: the solver's own u and v (nothing touches them
    //    during write(); checked after EndStep below)
    //  * default mode: u_data and v_data, locals that live to the end of
    //    their block, which contains EndStep()
    //  * span mode: ADIOS2's own buffer, filled before EndStep()
    //  * step: the by-value parameter, alive for the whole call
    const double *u_before = sim.u_ghost().data();
    const double *v_before = sim.v_ghost().data();
    double wrap_s = 0.0, put_s = 0.0, end_s = 0.0;

    if (settings.adios_memory_selection)
    {
        // Zero-copy: ADIOS2 reads the interior of the ghosted arrays.
        const auto a = clock::now();
        m_engine.BeginStep();
        m_engine.Put(m_var_u, sim.u_ghost().data());
        m_engine.Put(m_var_v, sim.v_ghost().data());
        m_engine.Put(m_var_step, &step);
        const auto b = clock::now();
        m_engine.EndStep();
        const auto c = clock::now();
        put_s = std::chrono::duration<double>(b - a).count();
        end_s = std::chrono::duration<double>(c - b).count();
    }
    else if (settings.adios_span)
    {
        // One copy, straight into ADIOS2's buffer (counted as wrap).
        const auto a = clock::now();
        m_engine.BeginStep();
        m_engine.Put<int>(m_var_step, &step);
        adios2::Variable<double>::Span u_span = m_engine.Put<double>(m_var_u);
        adios2::Variable<double>::Span v_span = m_engine.Put<double>(m_var_v);
        const auto b = clock::now();
        sim.u_noghost(u_span.data());
        sim.v_noghost(v_span.data());
        const auto c = clock::now();
        m_engine.EndStep();
        const auto d = clock::now();
        put_s = std::chrono::duration<double>(b - a).count();
        wrap_s = std::chrono::duration<double>(c - b).count();
        end_s = std::chrono::duration<double>(d - c).count();
    }
    else
    {
        // One copy here, into u_data and v_data; the engine may copy again
        // into its own buffer (engine-dependent).
        const auto a = clock::now();
        const std::vector<double> u_data = sim.u_noghost();
        const std::vector<double> v_data = sim.v_noghost();
        const auto b = clock::now();
        m_engine.BeginStep();
        m_engine.Put(m_var_u, u_data.data());
        m_engine.Put(m_var_v, v_data.data());
        m_engine.Put(m_var_step, &step);
        const auto c = clock::now();
        m_engine.EndStep(); // u_data and v_data are still alive here
        const auto d = clock::now();
        wrap_s = std::chrono::duration<double>(b - a).count();
        put_s = std::chrono::duration<double>(c - b).count();
        end_s = std::chrono::duration<double>(d - c).count();
    }

    if (sim.u_ghost().data() != u_before || sim.v_ghost().data() != v_before)
    {
        vtkLog(ERROR, "ADIOS2 writer: field arrays moved during a step; a deferred Put read freed memory");
        MPI_Abort(MPI_COMM_WORLD, 1);
    }

    phases.wrap_s = wrap_s;
    phases.execute_s = put_s; // Put() calls: registering the data
    phases.io_s = end_s + std::chrono::duration<double>(t_reopen - t0).count(); // EndStep moves the data
    phases.split = true;
}

void WriterADIOS::close(int rank)
{
    vtkLog(INFO, "Closing ADIOS2 writer");

    if (rank == 0)
    {
        std::cout << "--- ADIOS2 Final Configuration ---" << std::endl;
        const adios2::Params parameters = m_io.Parameters();
        if (parameters.empty())
        {
            std::cout << "No parameters found." << std::endl;
        }
        else
        {
            for (const auto &pair : parameters)
            {
                std::cout << pair.first << " = " << pair.second << std::endl;
            }
        }
        std::cout << "------------------------------------" << std::endl;
    }

    // Close the engine, which finalizes the file.
    if (m_engine)
    {
        m_engine.Close();
    }
}

void WriterADIOS::printSelf()
{
    vtkLog(INFO, "This is writer type ADIOS2");
}
