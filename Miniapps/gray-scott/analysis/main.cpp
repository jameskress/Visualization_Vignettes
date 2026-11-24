#include "analysis_backend_interface.h"
#include "adios_reader.h"
#include <mpi.h>
#include <getopt.h>
#include <nlohmann/json.hpp>
#include <iostream>
#include <fstream>
#include <string>
#include <memory>
#include <stdexcept>
#include <iomanip>

#include "../common/teardown_guard.hpp"
#include "../common/run_metadata_string.hpp"
#include <filesystem>
#include <sstream>

static constexpr const char *PROG = "analysis-reader";

static void usage(std::ostream &os)
{
    os << "Usage: " << PROG << " --file <adios-file-or-stream> --settings <sim-settings.json> [options]\n\n"
       << "Required:\n"
       << "  -f, --file <path>          ADIOS2 file or stream name (BP file or SST stream)\n"
       << "  -s, --settings <path>      Simulation settings JSON file\n\n"
       << "Optional:\n"
       << "  -c, --mpi-split-color <N>  Color for MPI_Comm_split in MPMD mode\n"
       << "  -e, --engine <engine>      ADIOS2 engine name override\n"
       << "  -o, --output-type <type>   Analysis backend: ascent | catalyst_insitu | catalyst_io | adios_writer\n"
       << "  -b, --block-mode <mode>    Data handling: repartition (the only mode)\n"
       << "  -D, --decomposition <d>    How repartition splits the domain: slab | brick\n"
       << "  -w, --sst-wait-mode <m>    SST wait mode: block | timeout\n"
       << "  -t, --sst-timeout <secs>   SST timeout seconds\n"
       << "  -V, --adios-verbose <lvl>  Set ADIOS2 engine verbose level (0-5)\n"
       << "  -d, --debug                Enable debug prints and verification\n"
       << "  -h, --help                 Print this help message\n";
}

int main(int argc, char **argv)
{
    int provided;
    MPI_Init_thread(&argc, &argv, MPI_THREAD_MULTIPLE, &provided);

    int global_rank;
    std::unique_ptr<TeardownGuard> guard; // armed once the reader has finished (#75)
    MPI_Comm_rank(MPI_COMM_WORLD, &global_rank);

    try
    {
        // CLI defaults
        std::string file_arg;
        std::string settings_arg;
        int mpi_split_color_arg = -1;
        std::string engine_arg;
        std::string output_type_arg;
        std::string block_mode_arg;
        std::string decomposition_arg;
        std::string sst_wait_mode_arg;
        int adios_verbose_arg = 0;
        double sst_timeout_arg = 0.0;
        bool debug_flag = false;

        const char *short_opts = "f:s:c:e:o:b:D:w:t:V:dh";
        const struct option long_opts[] = {
            {"file", required_argument, nullptr, 'f'},
            {"settings", required_argument, nullptr, 's'},
            {"mpi-split-color", required_argument, nullptr, 'c'},
            {"engine", required_argument, nullptr, 'e'},
            {"output-type", required_argument, nullptr, 'o'},
            {"block-mode", required_argument, nullptr, 'b'},
            {"decomposition", required_argument, nullptr, 'D'},
            {"sst-wait-mode", required_argument, nullptr, 'w'},
            {"sst-timeout", required_argument, nullptr, 't'},
            {"adios-verbose", required_argument, nullptr, 'V'},
            {"debug", no_argument, nullptr, 'd'},
            {"help", no_argument, nullptr, 'h'},
            {nullptr, 0, nullptr, 0}};

        int opt;
        while ((opt = getopt_long(argc, argv, short_opts, long_opts, nullptr)) != -1)
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
            case 'D':
                decomposition_arg = optarg;
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
                debug_flag = true;
                break;
            case 'h':
                if (global_rank == 0)
                    usage(std::cout);
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

        MPI_Comm app_comm;
        if (mpi_split_color_arg == -1)
        {
            MPI_Comm_dup(MPI_COMM_WORLD, &app_comm);
        }
        else
        {
            MPI_Comm_split(MPI_COMM_WORLD, mpi_split_color_arg, global_rank, &app_comm);
        }

        int rank, procs;
        MPI_Comm_rank(app_comm, &rank);
        MPI_Comm_size(app_comm, &procs);

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

        BackendOptions opts = BackendOptions::FromSettingsFile(settings_arg);
        opts.comm = app_comm;

        opts.adios_file = file_arg;
        if (!engine_arg.empty())
            opts.adios_engine = engine_arg;
        if (!output_type_arg.empty())
            opts.output_type = output_type_arg;
        if (!block_mode_arg.empty())
            opts.block_mode = block_mode_arg;
        if (opts.block_mode != "repartition")
            throw std::runtime_error("block mode '" + opts.block_mode +
                                     "' is not implemented; every backend uses 'repartition' (#42)");
        if (!decomposition_arg.empty())
            opts.read_decomposition = decomposition_arg;
        if (opts.read_decomposition != "slab" && opts.read_decomposition != "brick")
            throw std::runtime_error("read decomposition '" + opts.read_decomposition +
                                     "' is not one of: slab, brick");
        if (!sst_wait_mode_arg.empty())
            opts.sst_wait_mode = sst_wait_mode_arg;
        if (sst_timeout_arg > 0.0)
            opts.sst_timeout_seconds = sst_timeout_arg;
        if (adios_verbose_arg > 0)
            opts.adios_verbose = adios_verbose_arg;
        if (debug_flag)
        {
            opts.debug = true;
        }

        if (rank == 0)
        {
            std::cout << "\n======================================================\n"
                      << "            Analysis Reader Configuration\n"
                      << "======================================================\n";
            std::cout << std::left << std::setw(22) << "--- MPI Settings" << "---\n"
                      << std::setw(24) << "  Application Ranks" << ": " << procs << "\n";
            std::cout << "\n"
                      << std::setw(22) << "--- Input Data" << "---\n"
                      << std::setw(24) << "  Source" << ": " << opts.adios_file << "\n"
                      << std::setw(24) << "  Engine" << ": " << opts.adios_engine << "\n";
            if (opts.adios_engine == "SST")
            {
                std::cout << std::setw(24) << "  SST Wait Mode" << ": " << opts.sst_wait_mode << "\n";
                if (opts.sst_wait_mode == "timeout")
                {
                    std::cout << std::setw(24) << "  SST Timeout (s)" << ": " << opts.sst_timeout_seconds << "\n";
                }
            }
            std::cout << "\n"
                      << std::setw(22) << "--- Processing" << "---\n"
                      << std::setw(24) << "  Analysis Backend" << ": " << opts.output_type << "\n"
                      << std::setw(24) << "  Block Mode" << ": " << opts.block_mode << "\n"
                      << std::setw(24) << "  Decomposition" << ": " << opts.read_decomposition << "\n"
                      << std::setw(24) << "  ADIOS2 Config" << ": "
                      << (opts.adios_config.empty() ? std::string("(none)") : opts.adios_config) << "\n"
                      << std::setw(24) << "  Overwrite Last Step" << ": "
                      << (OverwritesLastStep(opts) ? "yes" : "no") << "\n";
            if (opts.output_type.find("catalyst") != std::string::npos)
            {
                std::cout << "\n"
                          << std::setw(22) << "--- Catalyst Settings" << "---\n";
                if (opts.output_type == "catalyst_io")
                {
                    std::cout << std::setw(24) << "  Mode" << ": File I/O\n";
                    std::cout << std::setw(24) << "  Output File" << ": " << opts.catalyst_output_file << "\n";
                }
                else
                {
                    std::cout << std::setw(24) << "  Mode" << ": In-Situ Script\n";
                    std::cout << std::setw(24) << "  Script Path" << ": " << opts.catalyst_script_path << "\n";
                }
            }
            if (opts.output_type == "adios_writer")
            {
                std::cout << "\n"
                          << std::setw(22) << "--- ADIOS2 Writer" << "---\n"
                          << std::setw(24) << "  Output File" << ": " << opts.adios_output_file << "\n";
            }
            std::cout << "\n"
                      << std::setw(22) << "--- Debugging" << "---\n"
                      << std::setw(24) << "  ADIOS Verbosity" << ": " << opts.adios_verbose << "\n"
                      << std::setw(24) << "  Debug Mode" << ": " << (opts.debug ? "ON" : "OFF") << "\n";
            std::cout << "======================================================\n\n";
        }

        auto backend = CreateBackend(opts.output_type, opts);
        // The reader's own run record, as the simulation writes one, taken
        // once the backend exists so its libraries (ParaView's Catalyst
        // implementation, Ascent) are in the list. Every rank constructs a
        // backend, so every rank reaches this collective:
        // reader_timers/metadata.json beside its timers (build, git commit,
        // hosts, platform, loaded libraries, settings and options).
        {
            const std::string collected = collect_run_metadata_string(app_comm);
            if (rank == 0)
            {
                nlohmann::json meta = nlohmann::json::parse(collected, nullptr, false);
                if (meta.is_discarded() || !meta.is_object())
                    meta = nlohmann::json::object();
                // Rank 0 only: nothing here may throw, or the other ranks
                // would wait in the backend's first collective.
                std::ifstream sf(settings_arg);
                std::stringstream raw;
                raw << sf.rdbuf();
                nlohmann::json parsed = nlohmann::json::parse(raw.str(), nullptr, false);
                meta["role"] = "analysis-reader";
                meta["settings_file"] = settings_arg;
                if (parsed.is_discarded())
                    meta["settings_text"] = raw.str();
                else
                    meta["settings"] = parsed;
                meta["options"] = {{"output_type", opts.output_type},
                                   {"adios_file", opts.adios_file},
                                   {"adios_engine", opts.adios_engine},
                                   {"adios_config", opts.adios_config},
                                   {"block_mode", opts.block_mode},
                                   {"read_decomposition", opts.read_decomposition},
                                   // what the reader runs, after any fallback
                                   {"reader_shared_planes", AdiosReader::EffectiveSharedPlanes().empty()
                                                                ? opts.reader_shared_planes
                                                                : AdiosReader::EffectiveSharedPlanes()},
                                   {"sst_wait_mode", opts.sst_wait_mode},
                                   // the setting in effect (adios_writer ignores it)
                                   {"overwrite_last_step", OverwritesLastStep(opts)}};
                meta["command_line"] = std::vector<std::string>(argv, argv + argc);
                std::error_code ec;
                std::filesystem::create_directories("reader_timers", ec);
                std::ofstream out("reader_timers/metadata.json");
                out << meta.dump(2, ' ', false, nlohmann::json::error_handler_t::replace) << "\n";
                if (!out)
                    std::cerr << "analysis-reader: could not write reader_timers/metadata.json\n";
            }
        }

        backend->Run();
        // Run() has written every output and the timings. Bound the rest:
        // destroying the backend (SST close, catalyst_finalize) and
        // MPI_Finalize (#75).
        guard = std::make_unique<TeardownGuard>(opts.teardown_timeout_s, global_rank, "analysis-reader");
    }
    catch (const std::exception &e)
    {
        // Print from every rank that throws. In an MPMD job world rank 0 is
        // a simulation rank, so a rank-0-only message hid every reader error (#78).
        std::cerr << "[analysis-reader rank " << global_rank << "] Fatal error: " << e.what() << std::endl;
        MPI_Abort(MPI_COMM_WORLD, -1);
    }
    MPI_Finalize();
    if (guard)
        guard->disarm();
    return 0;
}
