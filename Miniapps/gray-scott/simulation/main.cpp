#include <fstream>
#include <iostream>
#include <sstream>
#include <vector>
#include <string>
#include <mpi.h>

#include "../../gray-scott/common/timer.hpp"
#include "../../gray-scott/simulation/gray-scott.h"
#include "../../gray-scott/simulation/writer.h"

using namespace std;

int unknownArg = 0;
string fileName = "";
string loggingLevel = "MAX";
// print program usage message to user
void printUsage(int argc, char **argv, int rank, int numTasks) {
  if (rank == 0) {
    fprintf(stderr,
            "\n\tUSAGE: %s \n"
            "\t\tRequired Arguments:\n"
            "\t\t\t--settings-file=<path+file>\n"
            "\t\tAdditional Arguments:\n"
            "\t\t\t--logging-level=<string> (default INFO [OFF, ERROR, WARNING, INFO, TRACE, MAX, INVALID])\n"
            "\t\t\t--help || --h || -h\n"
            "\n\n",
            argv[0]);
    printf("\n\t--Ran with :: Number of tasks=%d--\n\n", numTasks);
  }
  MPI_Abort(MPI_COMM_WORLD, -1);
} // END printUsage

// method to check user input args and set up the program
void checkArgs(int argc, char **argv, int rank, int numTasks) {
  char repeatargs[2048];
  sprintf(repeatargs, "\n\tRunning %s with:\n", argv[0]);

  char unrecognizedArgs[2048];
  sprintf(unrecognizedArgs, "\n\t!!WARNING!! Passed unrecognized argument:\n");

  for (int i = 1; i < argc; i++) {
    string longvarNm(argv[i]);
    string optionName = longvarNm.substr(0, longvarNm.find("=", 1, 1) + 1);
    string optionValue =
        longvarNm.substr(longvarNm.find("=", 1, 1) + 1, longvarNm.length());

    if (optionName == "") {
      optionName = longvarNm;
    }

    if (optionName == "--help" || optionName == "-h" || optionName == "--h") {
      printUsage(argc, argv, rank, numTasks);
    } else if (optionName == "--settings-file=") {
      fileName = optionValue;
      // set args to repeat to user
      char str[1024];
      sprintf(str, "\t\t--settings-file=%s\n", optionValue.c_str());
      strcat(repeatargs, str);
    } else if (optionName == "--logging-level=") {
      loggingLevel = optionValue;
      char str[1024];
      sprintf(str, "\t\t--logging-level=%s\n", optionValue.c_str());
      strcat(repeatargs, str); 
    } else {
      unknownArg = 1;
      char str[1024];
      sprintf(str, "\t\t%s\n", longvarNm.c_str());
      strcat(unrecognizedArgs, str);
    }
  }

  // test for required args
  if (fileName == "") {
    if (rank == 0) {
      if (unknownArg == 1)
        printf("%s\n", unrecognizedArgs);
      printf("\n\n\t-*-*-ERROR-*-*- \t%s\n", repeatargs);
      printUsage(argc, argv, rank, numTasks);
    }
    MPI_Abort(MPI_COMM_WORLD, -1);;
  } else {
    if (rank == 0) {
      if (unknownArg == 1)
        printf("%s\n", unrecognizedArgs);
      printf("%s\n", repeatargs);
    }
  }
} // END checkAndSetProgramArgs

void print_settings(const Settings &s, int restart_step)
{
    std::cout << "grid:             " << s.L << "x" << s.L << "x" << s.L
              << std::endl;
    if (restart_step > 0)
    {
        std::cout << "restart:          from step " << restart_step
                  << std::endl;
    }
    else
    {
        std::cout << "restart:          no" << std::endl;
    }
    std::cout << "steps:            " << s.steps << std::endl;
    std::cout << "plotgap:          " << s.plotgap << std::endl;
    std::cout << "F:                " << s.F << std::endl;
    std::cout << "k:                " << s.k << std::endl;
    std::cout << "dt:               " << s.dt << std::endl;
    std::cout << "Du:               " << s.Du << std::endl;
    std::cout << "Dv:               " << s.Dv << std::endl;
    std::cout << "noise:            " << s.noise << std::endl;
    std::cout << "output:           " << s.output << std::endl;
    //std::cout << "adios_config:     " << s.adios_config << std::endl;
}

void print_simulator_settings(const GrayScott &s)
{
    std::cout << "process layout:   " << s.npx << "x" << s.npy << "x" << s.npz
              << std::endl;
    std::cout << "local grid size:  " << s.size_x << "x" << s.size_y << "x"
              << s.size_z << std::endl;
}

int main(int argc, char **argv)
{
    int provided;
    MPI_Init_thread(&argc, &argv, MPI_THREAD_MULTIPLE, &provided);
    int rank, procs, wrank, len;
    char my_hostname[MPI_MAX_PROCESSOR_NAME];

    MPI_Comm_rank(MPI_COMM_WORLD, &wrank);

    const unsigned int color = 1;
    MPI_Comm comm;
    MPI_Comm_split(MPI_COMM_WORLD, color, wrank, &comm);

    MPI_Comm_rank(comm, &rank);
    MPI_Comm_size(comm, &procs);
    MPI_Get_processor_name(my_hostname, &len);
    
    //----Test and then set args
    checkArgs(argc, argv, rank, procs);
    //--
    
    // vtk logger
    vtkLogger::Init(argc, argv);
    vtkLogger::SetStderrVerbosity(vtkLogger::ConvertToVerbosity(loggingLevel.c_str()));
    vtkLogger::SetThreadName("Rank_" + to_string(rank));

    //----Print run setup info
    if (rank == 0) 
    {
        printf("\t - Number of tasks=%d My rank=%d Running on %s\n", procs, rank, my_hostname);
    }
    //--

    Settings settings = Settings::from_json(fileName);

    GrayScott sim(settings, comm);
    sim.init();

    int restart_step = 0;
    Writer writer_main(settings, sim, rank);
    writer_main.open(settings.output, (restart_step > 0), rank);
    if (rank == 0)
    {
        std::cout << "========================================" << std::endl;
        print_settings(settings, restart_step);
        print_simulator_settings(sim);
        std::cout << "========================================" << std::endl;
    }

#ifdef ENABLE_TIMERS
    Timer timer_total;
    Timer timer_compute;
    Timer timer_write;

    std::ostringstream log_fname;
    log_fname << "gray_scott_pe_" << rank << ".log";

    std::ofstream log(log_fname.str());
    log << "step\ttotal_gs\tcompute_gs\twrite_gs" << std::endl;
#endif

    for (int it = restart_step; it < settings.steps;)
    {
#ifdef ENABLE_TIMERS
        MPI_Barrier(comm);
        timer_total.start();
        timer_compute.start();
#endif

        sim.iterate();
        it++;

#ifdef ENABLE_TIMERS
        timer_compute.stop();
        MPI_Barrier(comm);
        timer_write.start();
#endif

        if (it % settings.plotgap == 0)
        {
            if (rank == 0)
            {
                vtkLog(INFO, "Simulation at step " << it
                          << " writing output step     "
                          << it / settings.plotgap);
            }

            writer_main.write(it, sim, rank, procs);
        }

#ifdef ENABLE_TIMERS
        double time_write = timer_write.stop();
        double time_step = timer_total.stop();
        MPI_Barrier(comm);

        log << it << "\t" << timer_total.elapsed() << "\t"
            << timer_compute.elapsed() << "\t" << timer_write.elapsed()
            << std::endl;
#endif
    }

    writer_main.close(rank);

#ifdef ENABLE_TIMERS
    log << "total\t" << timer_total.elapsed() << "\t" << timer_compute.elapsed()
        << "\t" << timer_write.elapsed() << std::endl;

    log.close();
#endif

    MPI_Finalize();
}
