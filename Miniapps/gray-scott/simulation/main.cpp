#include <fstream>
#include <iostream>
#include <sstream>
#include <vector>
#include <string>
#include <mpi.h>

#include "../../gray-scott/common/timer.hpp"
#include "gray-scott.h"
#include "writer.h"
#include "writerType.h"

#ifdef USE_ADIOS2
#include "restart.h"
#include "writerADIOS.h"
#endif

// #include <vtkDebugLeaks.h>

using namespace std;

#include "stdlib.h"
#include "stdio.h"
#include "string.h"

/*
int parseLine(char* line){
    // This assumes that a digit will be found and the line ends in " Kb".
    int i = strlen(line);
    const char* p = line;
    while (*p <'0' || *p > '9') p++;
    line[i-3] = '\0';
    i = atoi(p);
    return i;
}

int getValue(){ //Note: this value is in KB!
    FILE* file = fopen("/proc/self/status", "r");
    int result = -1;
    char line[128];

    while (fgets(line, 128, file) != NULL){
        if (strncmp(line, "VmRSS:", 6) == 0){
            result = parseLine(line);
            break;
        }
    }
    fclose(file);
    return result;
}
*/

int unknownArg = 0;
string fileName = "";
string loggingLevel = "INFO";
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
            "\t\t\t--help || --h || -h\n"
            "\n\n",
            argv[0]);
    printf("\n\t--Ran with :: Number of tasks=%d--\n\n", numTasks);
  }
  MPI_Abort(MPI_COMM_WORLD, -1);
} // END printUsage

// method to check user input args and set up the program
void checkArgs(int argc, char **argv, int rank, int numTasks)
{
  char repeatargs[2048];
  sprintf(repeatargs, "\n\tRunning %s with:\n", argv[0]);

  char unrecognizedArgs[2048];
  sprintf(unrecognizedArgs, "\n\t!!WARNING!! Passed unrecognized argument:\n");

  for (int i = 1; i < argc; i++)
  {
    string longvarNm(argv[i]);
    string optionName = longvarNm.substr(0, longvarNm.find("=", 1, 1) + 1);
    string optionValue =
        longvarNm.substr(longvarNm.find("=", 1, 1) + 1, longvarNm.length());

    if (optionName == "")
    {
      optionName = longvarNm;
    }

    if (optionName == "--help" || optionName == "-h" || optionName == "--h")
    {
      printUsage(argc, argv, rank, numTasks);
    }
    else if (optionName == "--settings-file=")
    {
      fileName = optionValue;
      // set args to repeat to user
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
    ;
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
} // END checkAndSetProgramArgs

void print_settings(const Settings &s, int restart_step)
{
  std::cout << "grid:                 " << s.L << "x" << s.L << "x" << s.L
            << std::endl;
  if (restart_step > 0)
  {
    std::cout << "restart:          from step " << restart_step  << std::endl;
  }
  else
  {
    std::cout << "restart:              no" << std::endl;
  }
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
  std::cout << "catalyst_script_path: " << s.catalyst_script_path << std::endl;
  std::cout << "catalyst_lib_path:    " << s.catalyst_lib_path << std::endl;
#ifdef USE_ADIOS2
  std::cout << "adios_config:         " << s.adios_config << std::endl;
#endif
}

void print_simulator_settings(const GrayScott &s)
{
  std::cout << "process layout:       " << s.npx << "x" << s.npy << "x" << s.npz
            << std::endl;
  std::cout << "local grid size:      " << s.size_x << "x" << s.size_y << "x"
            << s.size_z << std::endl;
}

int main(int argc, char **argv)
{
  MPI_Comm comm = MPI_COMM_WORLD;
  MPI_Init(&argc, &argv);
  int rank, procs, len;
  char my_hostname[MPI_MAX_PROCESSOR_NAME];
  MPI_Comm_rank(comm, &rank);
  MPI_Comm_size(comm, &procs);
  MPI_Get_processor_name(my_hostname, &len);

  //----Test and then set args
  checkArgs(argc, argv, rank, procs);
  //--

  // vtk logger
  vtkLogger::Init(argc, argv);
  // Only show what we asked for on stderr:
  vtkLogger::SetStderrVerbosity(vtkLogger::ConvertToVerbosity(loggingLevel.c_str()));
  vtkLogger::SetThreadName("Rank_" + to_string(rank));

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

  GrayScott sim(settings, comm);
  sim.init();

  int restart_step = 0;
#ifdef USE_ADIOS2
  vtkLog(TRACE, "Setting up ADIOS2 for checkpointing");
  adios2::ADIOS adios(settings.adios_config, comm);
  adios2::IO io_ckpt = adios.DeclareIO("SimulationCheckpoint");

  if (settings.restart)
  {
      restart_step = ReadRestart(comm, settings, sim, io_ckpt);
      vtkLog(INFO, "Restarting simulation from step " << restart_step);
      //io_main.SetParameter("AppendAfterSteps",
      //                      std::to_string(restart_step / settings.plotgap));
  }
#endif

  std::shared_ptr<Writer> writer_main;
  // Create the writer based on the settings
  if (settings.output_type.empty())
  {
      std::cerr << "Error: output_type is not set!" << std::endl;
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
      std::cerr << "Error: Invalid output_type value: " << settings.output_type << std::endl;
      exit(1);
  }

#ifdef USE_ADIOS2
  // --- Special handling for the ADIOS writer ---
  // Check if the writer we created is, in fact, an ADIOS writer.
  if (settings.output_type == "adios")
  {
      // Safely cast the generic Writer pointer to a specific WriterADIOS pointer.
      auto adios_writer = std::dynamic_pointer_cast<WriterADIOS>(writer_main);
      if (adios_writer)
      {
          // If the cast was successful, call our new method to pass the adios object.
          adios_writer->SetADIOS(adios);
      }
  }
#endif

  writer_main->CreateWriter(settings, sim, rank);
  writer_main->open(settings.output_file_name, (restart_step > 0), rank);
  writer_main->printSelf();

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

      // vtkLog(INFO, "Pre-write mem usage: " << float(getValue())/1000000.0);
      writer_main->write(it, sim, rank, procs);
      // vtkLog(INFO, "Post-write mem usage: " << float(getValue())/1000000.0);
    }

#ifdef USE_ADIOS2
    // Write checkpoint if enabled
    if (settings.checkpoint && (it % settings.checkpoint_freq) == 0)
    {
        vtkLog(INFO, "Writing checkpoint at step " << it);
        // Write checkpoint data
        WriteCkpt(comm, it, settings, sim, io_ckpt);
    }
#endif

#ifdef ENABLE_TIMERS
    double time_write = timer_write.stop();
    double time_step = timer_total.stop();
    MPI_Barrier(comm);

    log << it << "\t" << timer_total.elapsed() << "\t"
        << timer_compute.elapsed() << "\t" << timer_write.elapsed()
        << std::endl;
#endif
  }

  writer_main->close(rank);
  // vtkDebugLeaks::PrintCurrentLeaks();

#ifdef ENABLE_TIMERS
  log << "total\t" << timer_total.elapsed() << "\t" << timer_compute.elapsed()
      << "\t" << timer_write.elapsed() << std::endl;

  log.close();
#endif

  MPI_Finalize();
}
