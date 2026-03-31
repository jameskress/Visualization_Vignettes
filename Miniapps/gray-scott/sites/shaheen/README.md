# Building Ascent
Ascent was not properly passing the `cc` and `CC` compiler wrappers to all of its sub builds. Below is what worked on the last build. 

***!! NOTE !!*** Compiler paths will have to be updated as the cray environment changes.

```bash
git clone --recursive https://github.com/alpine-dav/ascent.git
cd ascent

cat > shaheen-host-config.cmake << EOL
# shaheen-host-config.cmake

# Forcefully add the C++17 standard flag to the compiler flags.
# This is more direct than CMAKE_CXX_STANDARD and harder for Umpire to ignore.
set(CMAKE_CXX_FLAGS "\${CMAKE_CXX_FLAGS} -std=c++17" CACHE STRING "C++ Compiler Flags" FORCE)

# Also add the filesystem library to the linker flags for good measure.
set(CMAKE_EXE_LINKER_FLAGS "\${CMAKE_EXE_LINKER_FLAGS} -lstdc++fs" CACHE STRING "Linker Flags" FORCE)
EOL

export CC=/opt/cray/pe/craype/2.7.32/bin/cc
export CXX=/opt/cray/pe/craype/2.7.32/bin/CC

env prefix=build enable_mpi=ON enable_openmp=ON \
    ./scripts/build_ascent/build_ascent.sh -H shaheen-host-config.cmake
```

# ADIOS2
ADIOS worked following the README instructions.



# Performance scripts

## Creating python environment
cd /scratch/kressjm
module load python
python3 -m venv perf_env
source perf_env/bin/activate
pip install --upgrade pip
pip install pandas numpy matplotlib

## Generate the stats
python3 reduce_timers.py paper1_func_N0064_baseline/writer_timers summary_baseline.csv
python3 reduce_timers.py paper1_func_N0064_inline_adios_data/writer_timers summary_adios_data.csv
python3 reduce_timers.py paper1_func_N0064_inline_ascent_data/writer_timers summary_ascent_data.csv
python3 reduce_timers.py paper1_func_N0064_inline_ascent_render/writer_timers summary_ascent_render.csv
python3 reduce_timers.py paper1_func_N0064_inline_catalyst_data/writer_timers summary_catalyst_data.csv
python3 reduce_timers.py paper1_func_N0064_inline_catalyst_render/writer_timers summary_catalyst_render.csv
python3 reduce_timers.py paper1_func_N0064_transit_catalyst_render/writer_timers summary_catalyst_intransit_render.csv
python3 reduce_timers.py paper1_func_N0064_transit_ascent_render/writer_timers summary_ascent_intransit_render.csv
python3 reduce_timers.py paper1_func_N0064_inline_kombyne_data/writer_timers summary_kombyne_data.csv
python3 reduce_timers.py paper1_func_N0064_inline_kombyne_render/writer_timers summary_kombyne_render.csv
python3 plot_performance.py


## large scale performance runs
Run the reduce script to compile all of the run stats from each directory
bash reduce.sh 



1. Interesting Findings for the Paper (Architectural Insights)
The MPMD / SLURM Overlap Trap
When launching a heterogeneous Multiple Program, Multiple Data (MPMD) job (e.g., srun sim : reader), SLURM’s default behavior is to pack tasks as densely as possible. Without explicit instructions, SLURM will overlap the visualization ranks onto the exact same physical nodes as the simulation ranks.

The Insight: In-transit visualization is meant to decouple memory footprints, but if the job scheduler silently overlaps them, the combined RAM of the simulation plus the VTK-m rendering pipeline will instantly cause an Out-of-Memory (OOM) hardware crash. You must enforce physical separation.

The 32-bit vs. 64-bit Visualization Boundary
When trying to save RAM by running only 1 reader rank per node, the local grid partition grew to 4.36 Billion vertices per rank.

The Insight: High-performance rendering backends (like VTK-m inside Ascent) default to 32-bit signed integers for indexing to maximize GPU throughput and save memory. However, 32-bit integers overflow at 2.14 Billion. Attempting to process more than 2.14B points per rank causes a silent integer overflow, resulting in a fatal SIGSEGV during contouring. You must carefully balance the number of MPI ranks to keep the points-per-rank under 2.14B, without spawning so many ranks that the VTK-m context overheads exhaust the node's physical RAM.

Network Connection Density & The "SYN Storm"
At 512 simulation nodes and 32+ staging nodes, the ADIOS2 SST engine attempts to build a peer-to-peer communication mesh across ~33,000 MPI ranks.

The Insight: The Cray Slingshot 11 (CXI) network card is highly optimized, but its hardware queues (Portal Table Entries - PTEs) and Memory Registration (MR) caches can be instantly exhausted by millions of simultaneous connection requests. Pinning application memory (Zero-Copy) exacerbates this. If the network hardware is overloaded, or if the OS kills a rank due to OOM during the handshake, it results in cascading network failures like PERM_VIOLATION or PTLTE_NOT_FOUND.

2. What to Watch For (Practical "Gotchas")
SLURM Command Flags are Mandatory
For an srun : command, you cannot just specify total nodes and total tasks. You must use --exclusive on both sides of the colon to prevent node sharing. You must also explicitly define --ntasks-per-node and --cpus-per-task for each executable so SLURM properly spreads the ranks across the dedicated hardware rather than packing them all onto the first few nodes.

The SST 60-Second Timeout Trap
The ADIOS2 SST reader has a hardcoded default timeout of 60 seconds (OpenTimeoutSecs). At massive scales, a simulation might take 65+ seconds just to read a 4-Terabyte checkpoint file from the Lustre file system before it even starts the ADIOS writer.

The Gotcha: The readers will time out and crash before the simulation even finishes booting. Always override OpenTimeoutSecs in your reader code to something large (e.g., 600 seconds) for at-scale runs.

Transport and Engine Incompatibilities

WAN + epoll: If you try to use the WAN (TCP) transport in ADIOS2, you must change the ControlModule to select. Using WAN with epoll will cause an immediate MPI_Abort.

SSC + Sub-Communicators: The ADIOS2 SSC engine uses native MPI one-sided communication instead of network sockets. It is incredibly fast, but if you initialize the core ADIOS2 object with a split sub-communicator (app_comm) instead of MPI_COMM_WORLD, the writers and readers will be globally invisible to each other, and the job will hang indefinitely.

Masking Exceptions in C++
If a visualization reader rank crashes but your C++ catch block restricts error printing to Rank == 0, the crashing rank will silently call MPI_Abort and take down the entire 33,000-rank job without leaving a single log trace. Always ensure fatal exceptions are printed by the rank that throws them!
