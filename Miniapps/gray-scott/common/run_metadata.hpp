#pragma once
//
// Run metadata that does not depend on the simulation: build (git state,
// compiler, flags), host (CPU and GPU model, hostnames) and MPI library.
// main.cpp adds the problem, decomposition and backend. See README.md,
// Performance, for the full metadata.json layout.

#include <mpi.h>

#include "simulation/json.hpp"

// Collective over comm (gathers hostnames). The result is complete on rank 0.
nlohmann::json collect_run_metadata(MPI_Comm comm);
