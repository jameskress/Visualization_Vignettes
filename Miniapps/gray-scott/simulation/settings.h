#ifndef __SETTINGS_H__
#define __SETTINGS_H__

#include <cstdint>
#include <string>

struct Settings
{
    size_t L;
    int steps;
    int plotgap;
    double F;
    double k;
    double dt;
    double Du;
    double Dv;
    double noise;
    // Seed for the noise term. The noise at each point and step is a pure function of
    // (seed, step, global x, y, z), so any rank layout and any rerun give the same values.
    std::uint64_t seed;
    std::string output_file_name;
    std::string output_type;
    std::string catalyst_script_path;
    std::string catalyst_lib_path;
    bool checkpoint;
    int checkpoint_freq;
    std::string checkpoint_output;
    bool restart;
    std::string restart_input;
    std::string adios_config;
    bool adios_span;
    bool adios_memory_selection;
    std::string mesh_type;
    std::string kombynelite_script_path;
    // Parent directory for each run's performance log directory (#26).
    std::string perf_dir;
    int burn_in_steps;
    // Seconds allowed for closing the output and MPI_Finalize once every
    // output and the performance log are written; then exit 0. 0 disables (#75).
    double teardown_timeout_s;
    bool overwrite_last_step;

    Settings();
    static Settings from_json(const std::string &fname);
};

#endif
