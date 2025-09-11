#include "writerADIOS.h"

WriterADIOS::WriterADIOS() = default;
WriterADIOS::~WriterADIOS() = default;

void WriterADIOS::CreateWriter(const Settings &_settings, const GrayScott &sim, MPI_Comm comm, int rank)
{
    settings = _settings;

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
    //Removed the engine type setting to allow runtime configuration from XML file
    //m_io.SetEngine("BP5");

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
    m_io.DefineAttribute<std::string>("Fides_Data_Model", "uniform");

    const std::vector<double> origin = {0.0, 0.0, 0.0};
    const std::vector<double> spacing = {0.1, 0.1, 0.1};
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

    // Use a zero-copy approach taking data directly from the simulation's ghosted arrays.
    if (settings.adios_memory_selection)
    {
        m_engine.BeginStep();

        // We pass the pointer to the ghosted array. ADIOS2 uses the memory selection to write only the core data.
        m_engine.Put(m_var_u, sim.u_ghost().data());
        m_engine.Put(m_var_v, sim.v_ghost().data());
        m_engine.Put(m_var_step, &step);
        
        m_engine.EndStep();
    }
    // Use a span to provide memory directly from the ADIOS buffer.
    else if (settings.adios_span)
    {
        m_engine.BeginStep();

        m_engine.Put<int>(m_var_step, &step);

        // provide memory directly from adios buffer
        adios2::Variable<double>::Span u_span = m_engine.Put<double>(m_var_u);
        adios2::Variable<double>::Span v_span = m_engine.Put<double>(m_var_v);

        // populate spans
        sim.u_noghost(u_span.data());
        sim.v_noghost(v_span.data());

        m_engine.EndStep();
    }
    // Use a local copy of the data to write to ADIOS2.
    else
    {
        const std::vector<double> u_data = sim.u_noghost();
        const std::vector<double> v_data = sim.v_noghost();
        
        m_engine.BeginStep();
        
        // Pass the pointers from our new, long-lived local variables.
        m_engine.Put(m_var_u, u_data.data());
        m_engine.Put(m_var_v, v_data.data());
        
        m_engine.EndStep();
    }
}

void WriterADIOS::close(int rank)
{
    vtkLog(INFO, "Closing ADIOS2 writer");

    if(rank == 0)
    {
        std::cout << "--- ADIOS2 Final Configuration ---" << std::endl;
        const adios2::Params parameters = m_io.Parameters();
        if(parameters.empty())
        {
            std::cout << "No parameters found." << std::endl;
        }
        else
        {
            for (const auto& pair : parameters)
            {
                std::cout << pair.first << " = " << pair.second << std::endl;
            }
        }
        std::cout << "------------------------------------" << std::endl;
    }

    // Close the engine, which finalizes the file.
    if(m_engine)
    {
        m_engine.Close();
    }
}

void WriterADIOS::printSelf()
{
    vtkLog(INFO, "This is writer type ADIOS2");
}