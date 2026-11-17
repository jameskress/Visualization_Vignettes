#pragma once
// collect_run_metadata() as a JSON string, for code that has its own copy of
// nlohmann::json (the analysis reader) and so must not include
// run_metadata.hpp, which brings in the simulation's bundled json.hpp.
// Collective over comm; complete on rank 0 only ("null" on every other rank).

#include <mpi.h>

#include <string>

std::string collect_run_metadata_string(MPI_Comm comm);
