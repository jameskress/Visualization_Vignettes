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
ADIOS has issues with RDMA on shaheen, perfroamnce and hangs are inconsistent, when usingadios v2.11. I also tried wan, mpi, ucx, everything ends up crashing on the slingshot.

I upgraded to v2.12.0 and it seems to work consistenatly using mpi data transport on the slingshot. 


# Paraview
cmake -DCMAKE_BUILD_TYPE=RelWithDebInfo -DUSE_SYSTEM_mpi=ON -DUSE_SYSTEM_python3=OFF -DENABLE_catalyst=ON -DENABLE_mpi=ON -DENABLE_netcdf=ON -DENABLE_hdf5=ON -DENABLE_python3=ON -DENABLE_openmp=ON -DENABLE_ospray=ON ../paraview-superbuild


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



### Running generator
python3 ../sites/shaheen/2026-WOIV-scripts/generate_experiments.py --repo-path /scratch/kressjm/Visualization_Vignettes/ --bin-path /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/install/ --results-dir /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/runs/

### Running orchestrator
**warning!!!** Do not run these from the python virtual environment we created to run the analysis scripts, it breaks catalyst.
python3 ../sites/shaheen/2026-WOIV-scripts/orchestrate.py  --results-dir /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/runs/ --paper paper2  --submit --nodes 8
python3 ../sites/shaheen/2026-WOIV-scripts/orchestrate.py  --results-dir /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/runs/ --paper paper2  --submit --nodes 64
python3 ../sites/shaheen/2026-WOIV-scripts/orchestrate.py  --results-dir /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/runs/ --paper paper2  --submit --nodes 256
python3 ../sites/shaheen/2026-WOIV-scripts/orchestrate.py  --results-dir /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/runs/ --paper paper2  --submit --nodes 512
python3 ../sites/shaheen/2026-WOIV-scripts/orchestrate.py  --results-dir /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/runs/ --paper paper2  --submit --nodes 1024

I added the ability to select runs based on grid size as I wanted to put the restart files in fast storage, and it was limited tso could not place all data there at once
python3 ../sites/shaheen/2026-WOIV-scripts/orchestrate.py --results-dir /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/runs/ --paper paper2 --grid 1024 --dry-run





# Shaheen III Exascale Staging & ADIOS2 Survival Guide

### 1. Network & Transport (Slingshot 11 / OFI)
* **The MPI Socket Explosion:** At massive scales (e.g., 32,768 tasks), using `DataTransport="MPI"` for the SST engine will overwhelm the network control plane with connection requests. **Always use `DataTransport="RDMA"`** for large in-transit transfers.
* **The RDMA Fan-In Bomb (Segfaults in `CP_sendToPeer`):** Slingshot 11 OFI queue pairs have hardware limits. If you have 32k simulation tasks sending data to only 256 staging tasks, the staging tasks are hit with a 128:1 fan-in ratio and the network card drops the connections, causing a segfault. **Keep the fan-in ratio to 16:1 or 32:1** (e.g., use 1024 or 2048 staging tasks).
* **The Teardown Hang:** When the simulation finishes and sends the "Disconnect/FIN" packet, staging nodes might miss it if their CPUs are locked up doing heavy Lustre I/O. The simulation and reader will wait for each other infinitely. **Fix:** Add `<parameter key="ControlTimeoutSecs" value="120.0"/>` to `SimulationOutput` so SST gracefully gives up and exits after 2 minutes.

### 2. Lustre & POSIX I/O Limits
* **The 2 GiB POSIX Wall:** The Linux kernel (`MAX_RW_COUNT`) forbids writing a single memory block larger than 2 GiB. If an ADIOS2 aggregator's payload exceeds this (e.g., 17 GB per aggregator), it will deadlock or crash mid-write. **Fix:** Ensure the payload-per-aggregator stays under 2 GB, or rely on 1 aggregator per node to correctly stitch small chunks.
* **The Lustre MDS Storm:** If thousands of independent tasks try to create files simultaneously (e.g., using `EveryoneWrites`), the Lustre Metadata Server locks up and times out. **Fix:** Add `<parameter key="MaxOpenFilesAtOnce" value="64"/>` to throttle file creation.
* **Lustre Striping:** When writing hundreds or thousands of files in a staging pool, keep the stripe count low to avoid locking up Object Storage Targets (OSTs). **Use `lfs setstripe -c 1`**.

### 3. ADIOS2 BP5 Aggregation & Memory
* **The Shared Memory OOM Crash:** BP5 coordinates writers using `/dev/shm` (shared memory). If you force multiple aggregators onto a single compute node (e.g., 32 aggregators on 1 node), they will all request the default 4 GB (or more) memory buffer. This will exhaust the node's physical RAM, and Linux will silently assassinate the tasks mid-write (resulting in truncated 3.0 MB files).
* **The "Gold Standard" Configuration:**
    * **Rule:** Exactly **1 Aggregator per Node** (`NumAggregators` = Number of staging nodes).
    * **Rule:** Override the default memory buffer to safely hold the node's entire payload. Use `<parameter key="MaxShmSize" value="42949672960"/>` (40 GB).

### 4. Slurm MPMD Lifecycle
* **The `--wait=0` Assassin:** In an MPMD job (`srun sim : reader`), the `--wait=0` flag tells Slurm to kill the entire job the absolute millisecond the *first* application exits. If the simulation finishes while the readers are still writing to disk, Slurm will violently kill the readers, truncating your files and destroying the metadata. **Fix: Completely remove `--wait=0`** and `--kill-on-bad-exit=1` so Slurm patiently waits for the reader nodes to finish their I/O.

### 5. ParaView Catalyst Headless Rendering
* **OSMesa Segfaults:** When rendering on compute nodes without displays (`unset DISPLAY`), you must use software rendering (`vtkOSOpenGLRenderWindow`). If Catalyst cannot find `libOSMesa.so`, it falls back to hardware X11, returns a `NULL` pointer, and crashes all 512 tasks instantly. **Fix:** Ensure the ParaView `install/lib` directory is appended to `LD_LIBRARY_PATH` in the `.sbat` script.

***

### The Golden ADIOS2 In-Transit Staging Block
*Paste this into `adios2.xml` when using the staging backend to avoid POSIX crashes, OOM errors, and MDS storms.*

```xml
    <io name="AnalysisOutput">
        <engine type="BP5">
            <parameter key="verbose" value="0"/>
            
            <parameter key="NumAggregators" value="{stage_aggregators}"/>
            
            <parameter key="MaxShmSize" value="42949672960"/>
            
            <parameter key="AsyncWrite" value="false"/>
        </engine>
    </io>
"""
