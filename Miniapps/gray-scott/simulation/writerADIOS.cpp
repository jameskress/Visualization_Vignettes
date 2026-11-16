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
    m_comm = comm;

    // Span is checked with BP5 only; SST has no span Put(), so it is off for
    // SST. Memory selection works with SST when SST marshals with BP5, its
    // default: an in transit run with memory selection on reads back bitwise
    // identical to a BP5 file written without it, for slab and brick readers
    // (L = 65, 8 writers, 3 to 8 readers). The older FFS marshalling is
    // reported to ignore memory selections and is not tested here, so with
    // MarshalMethod=FFS it stays off, as it does before ADIOS2 2.9.2, whose
    // SST BP5 marshalling also ignored them (2.9.2 added the memory
    // selection path in SstWriter::PutSyncCommon). effis is SST under another name.
    std::string engine = m_io.EngineType();
    std::transform(engine.begin(), engine.end(), engine.begin(), ::tolower);
    if ((engine == "sst" || engine == "effis") && settings.adios_span)
    {
        if (rank == 0)
            vtkLog(WARNING, "ADIOS2: adios_span is not supported with SST; using the default write mode");
        settings.adios_span = false;
    }
    if ((engine == "sst" || engine == "effis") && settings.adios_memory_selection)
    {
        // SST reads only the exact key MarshalMethod (ADIOS2 2.11,
        // SstParamParser.cpp); any other spelling is ignored and SST uses
        // BP5. Read the same key so this check and the engine agree.
        const auto params = m_io.Parameters();
        std::string marshal = "bp5";
        const auto it = params.find("MarshalMethod");
        if (it != params.end())
        {
            marshal = it->second;
            std::transform(marshal.begin(), marshal.end(), marshal.begin(), ::tolower);
        }
        for (const auto &kv : params)
        {
            std::string key = kv.first;
            std::transform(key.begin(), key.end(), key.begin(), ::tolower);
            if (key == "marshalmethod" && kv.first != "MarshalMethod" && rank == 0)
                vtkLog(WARNING, "ADIOS2: SST ignores the parameter '" << kv.first
                                << "'; the name is MarshalMethod");
        }
#if !defined(ADIOS2_VERSION) || ADIOS2_VERSION < 20902
        marshal += " with ADIOS2 before 2.9.2";
#endif
        if (marshal != "bp5")
        {
            if (rank == 0)
                vtkLog(WARNING, "ADIOS2: adios_memory_selection is tested with SST only for MarshalMethod=BP5 "
                                "(this run has " << marshal << "); using the default write mode");
            settings.adios_memory_selection = false;
        }
    }
    // overwrite_last_step closes and reopens the engine at every write. For
    // SST that drops the reader's connection and the reader then waits forever
    // (found in the Paper 2 runs, sites/shaheen/README.md).
    if ((engine == "sst" || engine == "effis") && settings.overwrite_last_step)
    {
        if (rank == 0)
            vtkLog(WARNING, "ADIOS2: overwrite_last_step is not supported with SST (it would drop the "
                            "reader's connection at every step); writing every output step instead");
        settings.overwrite_last_step = false;
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

    // Rank 0's wall-clock time entering EndStep() (a global single value),
    // for the reader's Step_Latency timer (ADIOS2 #5272).
    m_var_endstep_wall = m_io.DefineVariable<double>("gs_endstep_wall");

    // --- OPEN THE ADIOS ENGINE ---
    const adios2::Mode mode = append ? adios2::Mode::Append : adios2::Mode::Write;
    m_engine = m_io.Open(fname, mode);
}

double WriterADIOS::EndStepTimed(int rank)
{
    double barrier_s = 0.0;
    if (settings.adios_endstep_barrier && m_comm != MPI_COMM_NULL)
    {
        const auto a = std::chrono::steady_clock::now();
        MPI_Barrier(m_comm);
        barrier_s = std::chrono::duration<double>(std::chrono::steady_clock::now() - a).count();
    }
    if (rank == 0)
    {
        // Deferred Put: m_endstep_wall is a member, alive past EndStep().
        m_endstep_wall =
            std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
        m_engine.Put(m_var_endstep_wall, &m_endstep_wall);
    }
    m_engine.EndStep();
    return barrier_s;
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
    double wrap_s = 0.0, put_s = 0.0, end_s = 0.0, barrier_s = 0.0;

    if (settings.adios_memory_selection)
    {
        // Zero-copy: ADIOS2 reads the interior of the ghosted arrays. Put()
        // receives the solver's own pointers by construction, so there is no
        // copy to detect here; the check after EndStep() catches a move.
        const auto a = clock::now();
        m_engine.BeginStep();
        m_engine.Put(m_var_u, sim.u_ghost().data());
        m_engine.Put(m_var_v, sim.v_ghost().data());
        m_engine.Put(m_var_step, &step);
        const auto b = clock::now();
        barrier_s = EndStepTimed(rank);
        const auto c = clock::now();
        put_s = std::chrono::duration<double>(b - a).count();
        end_s = std::chrono::duration<double>(c - b).count() - barrier_s;
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
        const AllocSnapshot wrap_alloc;
        sim.u_noghost(u_span.data());
        sim.v_noghost(v_span.data());
        phases.wrap_allocs = wrap_alloc.delta_calls();
        phases.wrap_alloc_bytes = wrap_alloc.delta_bytes();
        const auto c = clock::now();
        barrier_s = EndStepTimed(rank);
        const auto d = clock::now();
        put_s = std::chrono::duration<double>(b - a).count();
        wrap_s = std::chrono::duration<double>(c - b).count();
        end_s = std::chrono::duration<double>(d - c).count() - barrier_s;
    }
    else
    {
        // One copy here, into u_data and v_data; the engine may copy again
        // into its own buffer (engine-dependent).
        const auto a = clock::now();
        const AllocSnapshot wrap_alloc;
        const std::vector<double> u_data = sim.u_noghost();
        const std::vector<double> v_data = sim.v_noghost();
        phases.wrap_allocs = wrap_alloc.delta_calls();
        phases.wrap_alloc_bytes = wrap_alloc.delta_bytes();
        const auto b = clock::now();
        m_engine.BeginStep();
        m_engine.Put(m_var_u, u_data.data());
        m_engine.Put(m_var_v, v_data.data());
        m_engine.Put(m_var_step, &step);
        const auto c = clock::now();
        barrier_s = EndStepTimed(rank); // u_data and v_data are still alive here
        const auto d = clock::now();
        wrap_s = std::chrono::duration<double>(b - a).count();
        put_s = std::chrono::duration<double>(c - b).count();
        end_s = std::chrono::duration<double>(d - c).count() - barrier_s;
    }

    if (sim.u_ghost().data() != u_before || sim.v_ghost().data() != v_before)
    {
        vtkLog(ERROR, "ADIOS2 writer: field arrays moved during a step; a deferred Put read freed memory");
        MPI_Abort(MPI_COMM_WORLD, 1);
    }

    phases.barrier_s = barrier_s;
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
