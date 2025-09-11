#include <fstream>
#include <iostream>
#include <sstream>
#include <vector>
#include <string>
#include <memory>
#include <mpi.h>
#include <filesystem>

#include <sys/resource.h>

#include "../../gray-scott/common/timer.hpp"
#include "gray-scott.h"
#include "writer.h"
#include "writerType.h"

#ifdef USE_ADIOS2
#include "restart.h"
#endif

#include "../../gray-scott/common/perf_logger.hpp"

int unknownArg = 0;
std::string fileName = "";
std::string loggingLevel = "INFO";

// print program usage message to user
void printUsage(int argc, char **argv, int rank, int numTasks)
{
    if (rank == 0)
    {
        fprintf(stderr,
                "\n\tUSAGE: %s \n"
                "\t\tRequired Arguments:\n"
                "\t\t\t--settings-file=<path+file>\n"
                "\t\tAdditional Arguments:\n"
                "\t\t\t--logging-level=<string> (default INFO [OFF, ERROR, WARNING, INFO, TRACE, INVALID])\n"
                "\t\t\t--help || --h || -h\n\n",
                argv[0]);
        printf("\n\t--Ran with :: Number of tasks=%d--\n\n", numTasks);
    }
    MPI_Abort(MPI_COMM_WORLD, -1);
}

// method to check user input args and set up the program
void checkArgs(int argc, char **argv, int rank, int numTasks)
{
    char repeatargs[2048];
    sprintf(repeatargs, "\n\tRunning %s with:\n", argv[0]);

    char unrecognizedArgs[2048];
    sprintf(unrecognizedArgs, "\n\t!!WARNING!! Passed unrecognized argument:\n");

    for (int i = 1; i < argc; i++)
    {
        std::string longvarNm(argv[i]);
        std::string optionName = longvarNm.substr(0, longvarNm.find("=", 1, 1) + 1);
        std::string optionValue = longvarNm.substr(longvarNm.find("=", 1, 1) + 1, longvarNm.length());
        if (optionName == "")
            optionName = longvarNm;

        if (optionName == "--help" || optionName == "-h" || optionName == "--h")
        {
            printUsage(argc, argv, rank, numTasks);
        }
        else if (optionName == "--settings-file=")
        {
            fileName = optionValue;
            char str[1024];
            sprintf(str, "\t\t--settings-file=%s\n", optionValue.c_str());
            strcat(repeatargs, str);
        }
        else if (optionName == "--logging-level=")
        {
            loggingLevel = optionValue;
            char str[1024];
            sprintf(str, "\t\t--logging-level=%s\n", optionValue.c_str());
            strcat(repeatargs, str);
        }
        else
        {
            unknownArg = 1;
            char str[1024];
            sprintf(str, "\t\t%s\n", longvarNm.c_str());
            strcat(unrecognizedArgs, str);
        }
    }

    // test for required args
    if (fileName == "")
    {
        if (rank == 0)
        {
            if (unknownArg == 1)
                printf("%s\n", unrecognizedArgs);
            printf("\n\n\t-*-*-ERROR-*-*- \t%s\n", repeatargs);
            printUsage(argc, argv, rank, numTasks);
        }
        MPI_Abort(MPI_COMM_WORLD, -1);
    }
    else
    {
        if (rank == 0)
        {
            if (unknownArg == 1)
                printf("%s\n", unrecognizedArgs);
            printf("%s\n", repeatargs);
        }
    }
}

void print_settings(const Settings &s, int restart_step)
{
    std::cout << "grid:                 " << s.L << "x" << s.L << "x" << s.L << std::endl;
    if (restart_step > 0)
        std::cout << "restart:          from step " << restart_step << std::endl;
    else
        std::cout << "restart:              no" << std::endl;
    std::cout << "checkpoint:           " << (s.checkpoint ? "yes" : "no") << std::endl;
    if (s.checkpoint)
    {
        std::cout << "checkpoint_freq:      " << s.checkpoint_freq << std::endl;
        std::cout << "checkpoint_output:    " << s.checkpoint_output << std::endl;
    }
    std::cout << "steps:                " << s.steps << std::endl;
    std::cout << "plotgap:              " << s.plotgap << std::endl;
    std::cout << "F:                    " << s.F << std::endl;
    std::cout << "k:                    " << s.k << std::endl;
    std::cout << "dt:                   " << s.dt << std::endl;
    std::cout << "Du:                   " << s.Du << std::endl;
    std::cout << "Dv:                   " << s.Dv << std::endl;
    std::cout << "noise:                " << s.noise << std::endl;
    std::cout << "output_file_name:     " << s.output_file_name << std::endl;
    std::cout << "output_type:          " << s.output_type << std::endl;
#ifdef USE_CATALYST
    std::cout << "catalyst_script_path: " << s.catalyst_script_path << std::endl;
    std::cout << "catalyst_lib_path:    " << s.catalyst_lib_path << std::endl;
#endif
#ifdef USE_ADIOS2
    std::cout << "adios_config:         " << s.adios_config << std::endl;
    std::cout << "adios_span:           " << (s.adios_span ? "yes" : "no") << std::endl;
    std::cout << "adios_memory_selection: " << (s.adios_memory_selection ? "yes" : "no") << std::endl;
#endif
#ifdef USE_KOMBYNE
    std::cout << "kombynelite_script_path: " << s.kombynelite_script_path << std::endl;
#endif
}

void print_simulator_settings(const GrayScott &s)
{
    std::cout << "process layout:       " << s.npx << "x" << s.npy << "x" << s.npz << std::endl;
    std::cout << "local grid size:      " << s.size_x << "x" << s.size_y << "x" << s.size_z << std::endl;
}

int main(int argc, char **argv)
{
    int provided; // This will store the level of thread support MPI actually gave us
    MPI_Init_thread(&argc, &argv, MPI_THREAD_MULTIPLE, &provided);

    // Logic to get the application's color for splitting
    int mpi_split_color = 13; // Default to 13 for writer
    for (int i = 1; i < argc; ++i)
    {
        if (std::string(argv[i]) == "--mpi-split-color" && i + 1 < argc)
        {
            mpi_split_color = std::stoi(argv[i + 1]);
        }
    }

    MPI_Comm app_comm;
    MPI_Comm_split(MPI_COMM_WORLD, mpi_split_color, 0, &app_comm);

    int rank, procs, len;
    char my_hostname[MPI_MAX_PROCESSOR_NAME];
    MPI_Comm_rank(app_comm, &rank);
    MPI_Comm_size(app_comm, &procs);
    MPI_Get_processor_name(my_hostname, &len);

#ifdef USE_ADIOS2
    if (provided < MPI_THREAD_MULTIPLE)
    {
        if (rank == 0)
        {
            std::cerr << "Warning: MPI thread support level is insufficient for SST's MPI DataPlane." << std::endl;
        }
    }
#endif

    //----Test and then set args
    checkArgs(argc, argv, rank, procs);
    //--

    // vtk logger
    vtkLogger::Init(argc, argv);
    // Only show what we asked for on stderr:
    vtkLogger::SetStderrVerbosity(vtkLogger::ConvertToVerbosity(loggingLevel.c_str()));
    vtkLogger::SetThreadName("Rank_" + std::to_string(rank));

    // Put every log message in "everything.log":
    vtkLogger::LogToFile("everything.log", vtkLogger::APPEND, vtkLogger::VERBOSITY_MAX);
    // Only log INFO, WARNING, ERROR to "latest_readable.log":
    vtkLogger::LogToFile("latest_readable.log", vtkLogger::TRUNCATE, vtkLogger::VERBOSITY_INFO);

    //----Print run setup info
    if (rank == 0)
    {
        printf("\t - Number of tasks=%d My rank=%d Running on %s\n", procs, rank, my_hostname);
    }
    //--

    Settings settings = Settings::from_json(fileName);
    GrayScott sim(settings, app_comm);
    sim.init();

    int restart_step = 0;
#ifdef USE_ADIOS2
    vtkLog(TRACE, "Setting up ADIOS2 for checkpointing");
    adios2::ADIOS adios(settings.adios_config, app_comm);
    adios2::IO io_ckpt = adios.DeclareIO("SimulationCheckpoint");

    if (settings.restart)
    {
        restart_step = ReadRestart(app_comm, settings, sim, io_ckpt);
        vtkLog(INFO, "Restarting simulation from step " << restart_step);
    }
#endif

    // ------------------- PerfLogger -------------------
    std::string timer_dir = "writer_timers";
    std::filesystem::create_directories(timer_dir);

    // Initialize PerfLogger with output directory and timers
    PerfLogger perf(timer_dir, rank, my_hostname,
                    {"init_writer", "writer_open", "printSelf", "compute_step", "write_step", "create_checkpoint", "total_step"});

    // ------------------- Writer creation -------------------
    perf.start("create_writer");
    std::shared_ptr<Writer> writer_main;
    if (settings.output_type.empty())
    {
        std::cerr << "Error: output_type not set!" << std::endl;
        exit(1);
    }
    else if (settings.output_type == "pvti")
    {
        writer_main = WriterType::Create(WriterType::WRITER_TYPE_PVTI);
    }
#ifdef USE_ASCENT
    else if (settings.output_type == "ascent")
    {
        writer_main = WriterType::Create(WriterType::WRITER_TYPE_ASCENT);
    }
#endif
#ifdef USE_CATALYST
    else if (settings.output_type == "catalyst_io" || settings.output_type == "catalyst_insitu")
    {
        writer_main = WriterType::Create(WriterType::WRITER_TYPE_CATALYST);
    }
#endif
#ifdef USE_ADIOS2
    else if (settings.output_type == "adios")
    {
        writer_main = WriterType::Create(WriterType::WRITER_TYPE_ADIOS);
        auto adios_writer = std::dynamic_pointer_cast<WriterADIOS>(writer_main);
        if (adios_writer)
            adios_writer->SetADIOS(adios);
    }
#endif
#ifdef USE_KOMBYNE
    else if (settings.output_type == "kombyne")
    {
        writer_main = WriterType::Create(WriterType::WRITER_TYPE_KOMBYNE);
    }
#endif
    else
    {
        std::cerr << "Invalid output_type: " << settings.output_type << std::endl;
        exit(1);
    }

    writer_main->CreateWriter(settings, sim, app_comm, rank);
    perf.stop("create_writer");

    perf.start("writer_open");
    writer_main->open(settings.output_file_name, (restart_step > 0), rank);
    perf.stop("writer_open");

    perf.start("printSelf");
    writer_main->printSelf();
    perf.stop("printSelf");

    if (rank == 0)
    {
        std::cout << "========================================" << std::endl;
        print_settings(settings, restart_step);
        print_simulator_settings(sim);
        std::cout << "========================================" << std::endl;
    }

    // ------------------- Main simulation loop -------------------
    for (int it = restart_step; it < settings.steps; it++)
    {
        MPI_Barrier(app_comm);
        perf.start("total_step");

        perf.start("compute_step");
        sim.iterate();
        perf.stop("compute_step");

        MPI_Barrier(app_comm);

        if (it % settings.plotgap == 0)
        {
            if (rank == 0)
                vtkLog(INFO, "Simulation at step " << it << " writing output step " << it / settings.plotgap);

            perf.start("write_step");
            writer_main->write(it, sim, rank, procs);
            perf.stop("write_step");
        }

#ifdef USE_ADIOS2
        if (settings.checkpoint && (it % settings.checkpoint_freq) == 0)
        {
            perf.start("create_checkpoint");
            vtkLog(INFO, "Writing checkpoint at step " << it);
            WriteCkpt(app_comm, it, settings, sim, io_ckpt);
            perf.stop("create_checkpoint");
        }
#endif

        perf.stop("total_step");

        // For consistent CSV length:
        // init_writer is only meaningful once, zero afterwards
        if (it > restart_step)
        {
            perf.resetTimer("init_writer");
        }

        perf.logStep(it);
    }

    writer_main->close(rank);
    perf.finalize();

    MPI_Finalize();
}