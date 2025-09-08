// main.cpp
#include "analysis_backends.h"
#include <mpi.h>
#include <getopt.h>
#include <nlohmann/json.hpp>

#include <iostream>
#include <fstream>
#include <string>
#include <sstream>
#include <cstdlib>

static constexpr const char *PROG = "analysis-reader";
static constexpr const char *VERSION = "0.1";

static void usage(std::ostream &os)
{
    os << "Usage: " << PROG << " --file <adios-file-or-stream> --settings <sim-settings.json> [options]\n\n"
       << "Required:\n"
       << "  -f, --file <path>          ADIOS2 file or stream name (BP file or SST stream)\n"
       << "  -s, --settings <path>      Simulation settings JSON file (used to configure geometry/behavior)\n\n"
       << "Optional:\n"
       << "  -c, --mpi-split-color <N>  Color for MPI_Comm_split in MPMD mode\n"
       << "  -e, --engine <engine>      ADIOS2 engine name override (default: BP5)\n"
       << "  -o, --output-type <type>   Processor to use (ascent, vtkm, kombyne...). Default read from settings (output_type)\n"
       << "  -b, --block-mode <mode>    Data handling: preserve | repartition (default: preserve)\n"
       << "  -w, --sst-wait-mode <m>    SST wait mode: block | timeout (default block)\n"
       << "  -t, --sst-timeout <secs>   SST timeout seconds (when --sst-wait-mode=timeout)\n"
       << "  -V, --adios-verbose <lvl>  Set ADIOS2 engine verbose level (0-5)\n"
       << "  -d, --debug-verify         Enable Conduit blueprint verification (debug)\n"
       << "  -v, --version              Print version\n"
       << "  -h, --help                 Print this help message\n";
}

// helper: read settings JSON (returns parsed json; throws on error)
static nlohmann::json read_settings_json(const std::string &path)
{
    std::ifstream ifs(path);
    if (!ifs.is_open())
        throw std::runtime_error("Unable to open settings JSON: " + path);
    nlohmann::json js;
    ifs >> js;
    return js;
}

int main(int argc, char **argv)
{
    int provided;
    MPI_Init_thread(&argc, &argv, MPI_THREAD_MULTIPLE, &provided);

    // Get initial rank from global world for argument parsing
    int global_rank;
    MPI_Comm_rank(MPI_COMM_WORLD, &global_rank);

    // CLI defaults
    std::string file_arg;
    std::string settings_arg;
    int mpi_split_color_arg = -1;
    std::string engine_arg;
    std::string output_type_arg;
    std::string block_mode_arg;
    std::string sst_wait_mode_arg;
    int adios_verbose_arg = 0;
    double sst_timeout_arg = 0.0;
    bool debug_verify_flag = false;

    // getopt_long setup
    const char *short_opts = "f:s:c:e:o:b:w:t:V:dhv";
    const struct option long_opts[] = {
        {"file", required_argument, nullptr, 'f'},
        {"settings", required_argument, nullptr, 's'},
        {"mpi-split-color", required_argument, nullptr, 'c'},
        {"engine", required_argument, nullptr, 'e'},
        {"output-type", required_argument, nullptr, 'o'},
        {"block-mode", required_argument, nullptr, 'b'},
        {"sst-wait-mode", required_argument, nullptr, 'w'},
        {"sst-timeout", required_argument, nullptr, 't'},
        {"adios-verbose", required_argument, nullptr, 'V'},
        {"debug-verify", no_argument, nullptr, 'd'},
        {"help", no_argument, nullptr, 'h'},
        {"version", no_argument, nullptr, 'v'},
        {nullptr, 0, nullptr, 0}};

    int opt;
    int opt_index = 0;
    while ((opt = getopt_long(argc, argv, short_opts, long_opts, &opt_index)) != -1)
    {
        switch (opt)
        {
        case 'f':
            file_arg = optarg;
            break;
        case 's':
            settings_arg = optarg;
            break;
        case 'c':
            mpi_split_color_arg = std::stoi(optarg);
            break;
        case 'e':
            engine_arg = optarg;
            break;
        case 'o':
            output_type_arg = optarg;
            break;
        case 'b':
            block_mode_arg = optarg;
            break;
        case 'w':
            sst_wait_mode_arg = optarg;
            break;
        case 'V':
            adios_verbose_arg = std::stoi(optarg);
            break;
        case 't':
            sst_timeout_arg = std::stod(optarg);
            break;
        case 'd':
            debug_verify_flag = true;
            break;
        case 'h':
            if (global_rank == 0)
                usage(std::cout);
            MPI_Finalize();
            return 0;
        case 'v':
            if (global_rank == 0)
                std::cout << PROG << " version " << VERSION << "\n";
            MPI_Finalize();
            return 0;
        case '?':
        default:
            if (global_rank == 0)
                usage(std::cerr);
            MPI_Finalize();
            return 2;
        }
    }

    // --- COMMUNICATOR SPLIT LOGIC ---
    MPI_Comm app_comm;
    // If a color was not provided, we are in SPMD mode, use MPI_COMM_WORLD.
    // Otherwise, we are in MPMD mode, so split the communicator.
    if (mpi_split_color_arg == -1)
    {
        MPI_Comm_dup(MPI_COMM_WORLD, &app_comm);
    }
    else
    {
        MPI_Comm_split(MPI_COMM_WORLD, mpi_split_color_arg, global_rank, &app_comm);
    }

    // ** RE-QUERY rank and size from the new application-specific communicator **
    int rank, procs;
    MPI_Comm_rank(app_comm, &rank);
    MPI_Comm_size(app_comm, &procs);

    if (provided < MPI_THREAD_MULTIPLE)
    {
        if (rank == 0)
        {
            std::cerr << "Warning: MPI thread support level is insufficient for SST's MPI DataPlane." << std::endl;
        }
    }

    // --- CONTINUE WITH APPLICATION LOGIC USING THE NEW RANK ---

    if (file_arg.empty() || settings_arg.empty())
    {
        if (rank == 0)
        {
            std::cerr << "Error: --file and --settings are required.\n\n";
            usage(std::cerr);
        }
        MPI_Finalize();
        return 2;
    }

    nlohmann::json settings_json;
    try
    {
        settings_json = read_settings_json(settings_arg);
    }
    catch (const std::exception &e)
    {
        if (rank == 0)
            std::cerr << "Error reading settings: " << e.what() << "\n";
        MPI_Finalize();
        return 3;
    }

    BackendOptions opts;
    try
    {
        opts = BackendOptions::FromSettingsFile(settings_arg);
    }
    catch (const std::exception &e)
    {
        if (rank == 0)
            std::cerr << "Error parsing settings file: " << e.what() << "\n";
        MPI_Finalize();
        return 4;
    }

    // Pass the correct communicator to the backend
    opts.comm = app_comm;

    // Apply CLI overrides
    opts.adios_file = file_arg;
    if (!engine_arg.empty())
        opts.adios_engine = engine_arg;
    if (!block_mode_arg.empty())
        opts.block_mode = block_mode_arg;
    if (!sst_wait_mode_arg.empty())
        opts.sst_wait_mode = sst_wait_mode_arg;
    if (sst_timeout_arg > 0.0)
    {
        opts.sst_timeout_seconds = sst_timeout_arg;
        if (sst_wait_mode_arg.empty())
            opts.sst_wait_mode = "timeout";
    }
    if (adios_verbose_arg > 0)
        opts.adios_verbose = adios_verbose_arg;
    if (debug_verify_flag)
        opts.debug_verify_blueprint = true;

    std::string output_type = "ascent";
    if (!output_type_arg.empty())
        output_type = output_type_arg;
    else if (settings_json.contains("output_type") && settings_json["output_type"].is_string())
        output_type = settings_json["output_type"].get<std::string>();

    if (opts.sst_wait_mode != "block" && opts.sst_wait_mode != "timeout")
    {
        if (rank == 0)
            std::cerr << "Error: --sst-wait-mode must be 'block' or 'timeout'\n";
        MPI_Finalize();
        return 5;
    }
    if (opts.sst_wait_mode == "timeout" && opts.sst_timeout_seconds <= 0.0)
    {
        if (rank == 0)
            std::cerr << "Error: --sst-timeout must be > 0 when --sst-wait-mode=timeout\n";
        MPI_Finalize();
        return 6;
    }

    if (rank == 0)
    {
        std::cout << "Configuration:\n"
                  << "  adios file/stream : " << opts.adios_file << "\n"
                  << "  adios engine      : " << opts.adios_engine << "\n"
                  << "  ascent actions    : (from ascent_actions.yaml in run directory)\n"
                  << "  block mode        : " << opts.block_mode << "\n"
                  << "  sst wait mode     : " << opts.sst_wait_mode << "\n"
                  << "  adios verbose     : " << opts.adios_verbose << "\n";
        if (opts.sst_wait_mode == "timeout")
            std::cout << "  sst timeout (s)   : " << opts.sst_timeout_seconds << "\n";
        std::cout << "  debug verify bp   : " << (opts.debug_verify_blueprint ? "true" : "false") << "\n"
                  << "  output type       : " << output_type << "\n";
        if (opts.origin)
            std::cout << "  origin provided in settings/adios attribute\n";
        if (opts.spacing)
            std::cout << "  spacing provided in settings/adios attribute\n";
    }

    try
    {
        if (output_type == "ascent")
        {
            Adios2ConduitBackend<ProcessorAscent> backend;
            backend.Initialize(opts);

            backend.Run([&](const conduit::Node &mesh, size_t step)
                        {
                // Important: 'rank' here is now the rank within the sub-communicator
                if (rank == 0)
                {
                    std::cout << "Processed step " << step << "\n";
                } });

            backend.Finalize();
        }
        else
        {
            if (rank == 0)
                std::cerr << "Unsupported output_type: '" << output_type << "'." << std::endl;
            MPI_Finalize();
            return 7;
        }
    }
    catch (const std::exception &ex)
    {
        if (rank == 0)
            std::cerr << "Fatal error: " << ex.what() << "\n";
        MPI_Abort(MPI_COMM_WORLD, -1);
    }

    MPI_Finalize();
    return 0;
}