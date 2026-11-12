# Running with Catalyst on a workq node: set the OSMesa window first

The Catalyst implementation in `software/paraview-build` is an EGL build. On a
`workq` node, which has no GPU, its EGL window creation falls into the system
Mesa (`libEGL_mesa` / `libgallium`) and segfaults in `_glapi_add_dispatch` at
the first render, on a handful of ranks, before any image is written (21 Oct
2026, core backtrace). The superbuild also carries OSMesa, so tell VTK to use
its own offscreen window and EGL is never touched:

```bash
export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow
# OSPRay (used by the Paper 2 Catalyst scripts) loads its modules from here:
export LD_LIBRARY_PATH=/scratch/kressjm/Visualization_Vignettes/software/paraview-build/install/lib:$LD_LIBRARY_PATH
srun ... ./gray-scott --settings-file=settings.json
```

The simulation alone (`output_type: none`) is unaffected; only the Catalyst
render path needs it. A 256^3 run on one node (64 ranks x 3 threads) with a
JPG every 10 steps is the HPC Saudi 2026 live demo.

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
ADIOS2 builds following the README instructions. Use 2.12 or newer for in
transit runs. With 2.11, SST over RDMA on Shaheen III hung or performed
inconsistently, and the WAN, MPI and UCX data planes crashed on Slingshot.
With 2.12.0, SST over the MPI data plane ran consistently in the Paper 2
tests. SST over RDMA with 2.12.0 completed a 1,024 + 32 node Catalyst run
(#79), with the shutdown bounded by #75. #72 compares the two at scale.

# ParaView
The superbuild configuration used on Shaheen III:

```bash
cmake -DCMAKE_BUILD_TYPE=RelWithDebInfo -DUSE_SYSTEM_mpi=ON -DUSE_SYSTEM_python3=OFF \
    -DENABLE_catalyst=ON -DENABLE_mpi=ON -DENABLE_netcdf=ON -DENABLE_hdf5=ON \
    -DENABLE_python3=ON -DENABLE_openmp=ON -DENABLE_ospray=ON ../paraview-superbuild
```



# Performance scripts

## Creating python environment
```bash
cd /scratch/kressjm
module load python
python3 -m venv perf_env
source perf_env/bin/activate
pip install --upgrade pip
pip install pandas numpy matplotlib
```

## Generate the stats
```bash
# reduce_timers.py reads either format: the per-rank writer_timers/*.csv files
# of runs made before #26 (the 2026 WOIV runs), or a newer run's perf/<run>
# directory (steps/rank_*.jsonl). The summary CSV is the same, so
# plot_performance.py works on both. scripts/perf_report.py (README.md,
# Performance) also reads new runs.
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
# A run from a current build: pass its perf/<run> directory instead
# (replace <run> with the run directory name, e.g. 20261109-105657_none_np2).
python3 reduce_timers.py paper1_func_N0064_baseline/perf/<run> summary_baseline.csv
```

# Paper 2: runs at scale

## Generate and submit
`generate_experiments.py` writes one sbatch script per run into
`generated_scripts/` and a run directory per run under `--results-dir`.
`orchestrate.py` selects and submits them. `generate_experiments.py`
writes the paths it is given into those scripts unquoted, so it accepts
only letters, digits and `. _ - + /` in them (no spaces or other shell
characters) and stops otherwise; `orchestrate.py` does not check them.

```bash
cd /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/runs
python3 ../sites/shaheen/2026-WOIV-scripts/generate_experiments.py \
    --repo-path /scratch/kressjm/Visualization_Vignettes/ \
    --bin-path /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/install/ \
    --results-dir /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/runs/

# Submit by simulation node count, grid size (L) or workload; --dry-run lists them.
python3 ../sites/shaheen/2026-WOIV-scripts/orchestrate.py \
    --results-dir /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/runs/ \
    --paper paper2 --nodes 64 --submit
python3 ../sites/shaheen/2026-WOIV-scripts/orchestrate.py \
    --results-dir /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/runs/ \
    --paper paper2 --grid 1024 --dry-run
```

Do not run the orchestrator from the Python environment made for the
analysis scripts: inside a run that environment breaks Catalyst. Each job
activates it (`--perf-env`, default `/scratch/$USER/perf_env`) only after
the run, to reduce its timings.

Before submitting, run the same jobs at small scale on the workstation with
`sites/kw61316/run_generator_locally.py` (see that site's README).

The generator leaves an initialisation run directory that already holds
`data/checkpoint.bp` alone (its settings belong to that checkpoint), so
results directories can link to existing checkpoints.

`--grid` exists to submit one grid size at a time, for example to stage only
that size's restart files on fast storage.

Paper 2 workloads: baseline, ADIOS2 data, and for Ascent and Catalyst data,
slices (`render`), `volume` and `isosurface`; inline for strong and weak
scaling, in transit for three sizes and a staging-node sweep at 4096 nodes.
In transit ADIOS2 data uses the reader's `adios_writer` backend, so the
staging nodes write the data. Paper 1's jobs are unchanged (501 steps).

The volume workloads are comparable between the backends: both render `v`
over the full grid with the same colours, opacity ramp and range (0 to 1).

Knobs to turn during scale testing:
* **Fan-in:** the staging node counts in `TRANSIT_CONFIGS` and
  `TRANSIT_SWEEP_CONFIGS` (see Fan-in below).
* **Ascent volume samples:** `--volume-samples-per-cell` (default 9). Ascent
  takes `samples` per ray across the whole grid; about 9 per cell crossed
  keeps the image free of banding that changes with the rank count, which
  is 63,851 samples at 4096^3. Fewer is cheaper.

## Transport matrix (#72 step 1)
`--paper xport` selects 16 short in transit jobs (101 steps, 6 outputs):

* SST data plane: RDMA or MPI;
* reader: Ascent or Catalyst slices;
* launch: one MPMD `srun` (`mpmd`), or two `srun` steps, one per program,
  sharing the job's VNI (`steps`: `#SBATCH --network=job_vni` and
  `srun --network=job_vni`, so SST can connect across steps);
* fan-in in tasks: 16:1 (8 + 4 nodes, 1024^3) or 128:1 (64 + 4 nodes, 2048^3).

```bash
python3 ../sites/shaheen/2026-WOIV-scripts/orchestrate.py \
    --results-dir /scratch/kressjm/Visualization_Vignettes/Miniapps/gray-scott/runs/ \
    --paper xport --submit
```

## Scaling runs (#72 step 2)
`--paper scale` selects 12 jobs: RDMA, Ascent and Catalyst slices, MPMD and
two-step launch, at 256 + 16, 512 + 32 and 1024 + 64 nodes (4096^3 from the
existing checkpoint, 128:1 fan-in in tasks, 101 steps, 45 minute limit).

Node limits: the `workq` QOS caps each user at 2048 nodes across all running
jobs (`sacctmgr show qos workq`), so 1024 simulation nodes plus readers is
the largest power-of-two simulation that fits. The `ex` partition allows up
to 4608 nodes but needs permission to use; these jobs stay on `workq`.

Each job prints `PHASE` lines (seconds since the epoch): `job_start`,
`run_start`, `run_end` and `post_end`. With the performance log's
`restart_read_s` and the `writer_open` timer (the SST rendezvous wait) they
give setup, startup, steps and shutdown separately.

In `steps` jobs each step's exit status is printed (`Simulation exit status:
N, reader exit status: M`), and the job's status is the first non-zero one. If the first step to end
failed, the other is stopped (as `--kill-on-bad-exit` does for MPMD).

## After the runs
Each run's job first saves its own batch script as `<results>/<id>_job.sbat`
and the job-wide network and allocator settings it exported (`FI_*`,
`CM_*`, `MALLOC_*`, `MPICH_*`, `Sst_*`, `ADIOS2_*`) as
`<results>/<id>_env.txt`, so runs made with different settings can be told
apart. Thread settings are not in that file because each `srun` sets its
own (the in transit reader runs 24 OpenMP threads, the simulation 3); read
them from the saved script.

When a run ends, its job submits a one-node job, `reduce.sbat` in the run
directory, and exits, so the run's nodes are released at once (reducing
tens of thousands of per-rank files on a 1088-node allocation used to keep
it idle for minutes, once for over half an hour, #72). The reduction job
writes `reduce-<jobid>.out` and produces:

* `<results>/<id>_writer.csv`, from the newest run directory under `perf/`,
  with that run's `metadata.json` and `summary.json` copied beside it as
  `<id>_metadata.json` and `<id>_summary.json`;
* `<results>/<id>_reader.csv`, from `reader_timers/` (in transit runs);
* `perf/` and `reader_timers/` are then compressed to `.tar.gz`, to save inodes.

`large-runs/audit_runs.py --results-dir <results>` lists runs that are missing, failed
(time limit, out of memory, crash) or still running. If a run's reduction
job could not be submitted, its Slurm log says `REDUCE_SUBMIT_FAILED`
(`grep -l REDUCE_SUBMIT_FAILED <results>/*/slurm-*.out`); if it was
submitted but failed, check `<run>/reduce-*.out`. Either way,
`sbatch <run>/reduce.sbat` redoes that run's reduction, for any experiment
(`xport_*`, `scale_*` or `paper2_*`); it first restores `perf/` and
`reader_timers/` from their `.tar.gz` if an earlier reduction archived them.
Only one reduction of a run runs at a time (`<run>/reduce.lock`); a reduction
killed at its time limit leaves the lock behind, so remove it by hand before
rerunning.
`large-runs/reduce.sh` covers only the `paper2_*` runs: it reduces each one's
`perf/` again into `summary_<scale>_<workload>.csv`, and
`large-runs/scalability_plotting.py` plots those. It skips a run whose
`perf/` was archived, so restore that first:
`tar -xzf <run>/perf.tar.gz -C <run>`.

## Lessons from Shaheen III at scale

**MPMD jobs overlap unless told not to.** For `srun sim : reader`, Slurm
packs tasks as densely as it can, and without explicit settings it puts the
reader ranks on the simulation's nodes. The simulation plus a VTK-m render
then runs out of memory. Give each side `--exclusive`, `--nodes`,
`--ntasks-per-node` and `--cpus-per-task`; the generator does.

**VTK-m indexes with 32-bit integers.** With one reader rank per node the
local partition grew to 4.36 billion points per rank, past 2^31, and
contouring crashed with SIGSEGV. Keep points per rank under 2.1 billion,
without so many ranks that the per-rank VTK-m overhead fills the node's
memory. The generator uses 8 reader ranks of 24 threads per staging node.

**Connection storms.** At 512 simulation nodes and 32 or more staging nodes,
SST builds a peer-to-peer mesh across about 33,000 ranks. The Slingshot NIC's
queues (PTEs) and memory registration caches can be exhausted by that many
simultaneous connections, and pinned zero-copy memory makes it worse. An
overloaded NIC, or a rank killed by out-of-memory during the handshake,
shows up as `PERM_VIOLATION` or `PTLTE_NOT_FOUND` errors on many ranks.

**Fan-in.** With 32,768 simulation tasks sending to 256 staging tasks
(128:1), the staging side dropped connections and segfaulted in
`CP_sendToPeer`. Keep the ratio of tasks at 16:1 to 32:1 (1,024 to 2,048
staging tasks for that case). The ratios in the generator's transit
configurations are node ratios: with 64 simulation ranks and 8 reader
ranks per node, 16:1 in nodes is 128:1 in tasks. #72 measures which ratio
holds up.

**SST data plane.** At about 32,768 tasks, SST over the MPI data plane
overwhelmed the control plane with connection requests, so the generator
uses RDMA for in transit runs. #72 retests MPI against RDMA with the current
launch setup.

**Timeouts.** The reader waits `sst_open_timeout_s` seconds (default 600)
for the stream to open (#78): ADIOS2's default of 60 s ran out while the
simulation read a multi-terabyte checkpoint. `OpenTimeoutSecs` is SST's only
timeout; there is no `ControlTimeoutSecs`. A shutdown that hangs in SST's
RDMA teardown is bounded by `teardown_timeout_s` (#75).

**Other engines and transports.** SST over WAN (TCP) needs
`ControlModule=select`; with `epoll` it aborts at once. SSC uses MPI
one-sided communication and is fast, but with ADIOS2 created on a split
communicator (not `MPI_COMM_WORLD`) the writers and readers never see each
other and the job hangs.

**glibc mmap threshold.** Every generated job exports
`MALLOC_MMAP_THRESHOLD_=33554432`. That fixes the size at which glibc serves
an allocation with mmap at its 32 MiB maximum, where by default it moves as
the program frees large blocks. ADIOS2 2.13.0-rc1 made the reader's SST
RDMA step slower: 9.0 s instead of 7.2 s for the 64 + 4 node f128 Ascent
job (12 Nov 2026). Reverting one commit (c76c0ae40) removes the slowdown,
and so does this setting, with the commit in place. A 64 times larger
libfabric registration cache (`FI_MR_CACHE_MAX_COUNT`) does not.

| Build | Default | Threshold fixed |
|---|---|---|
| 2.13.0-rc1 | 9.02 s | 7.19, 7.09, 7.22 s |
| rc1 with c76c0ae40 reverted | 7.16 s | 7.12 s |
| 2.12.0 | 7.07 s | 7.25 s |

None of that commit's code runs for our reads: each reader's slab covers
whole writer blocks in the two fast dimensions, so no request has gaps
and the new per-run table is never built. What the commit changes for us
is the size of ADIOS2's internal read request, from 96 to 120 bytes (one
added member). The revert with an unused 24 byte member put back is as
slow as rc1 (9.08 and 9.56 s, against 8.93 s for rc1 and 7.39 s for the
revert that day). So the slowdown follows the memory layout, not any
added work, which is why fixing the allocator's threshold cures it.

The extra time is in the reader's calls to the Slingshot driver
(`/dev/cxi0`): 10.7 s on rc1, 3.4 s with the threshold fixed, 1.7 s with the
revert. The number of calls stays about 7,000 on rc1 either way (2,700 with
the revert), so it is the cost of each call that drops. A standalone SST
reader making the same requests does not slow down, so the miniapp's other
allocations (meshes, rendering) are probably part of it. With 2.12.0, which
the runs use now, runs with and without the setting are within run to run
spread (7.11 and 7.43 s in two earlier default runs). Keep the setting
until ADIOS2 explains or removes the sensitivity, then measure again
before removing it.

**Errors from every rank.** A reader rank that threw used to print nothing,
because only world rank 0 printed and in an MPMD job that is a simulation
rank. Both programs now print fatal errors from every rank (#78).

**Slurm job end.** `--wait=N` ends the whole step N seconds after its first
task exits, which can kill readers still writing. `--wait=0` means no
limit. Without `--wait`, Slurm uses `SLURM_WAIT` from the environment if
set, else the site's `WaitTime`, which is 0 on Shaheen III
(`scontrol show config`). The generator sets no `--wait`, so a reader can
finish its last steps; on another site, check `WaitTime` and that
`SLURM_WAIT` is unset. A stuck
shutdown is bounded by `teardown_timeout_s` (#75) instead. It keeps
`--kill-on-bad-exit=1`, which acts only when a program exits non-zero: if
the reader crashes, the simulation would otherwise block on its next SST
step until the time limit. In #72 step 1 it ended jobs whose readers
crashed in about 1.5 minutes. The two-step launch does the same for its
steps.

**Lustre.**
* One write larger than 2 GiB fails (`MAX_RW_COUNT`); an ADIOS2 aggregator
  with a 17 GB payload deadlocked or crashed. Keep the payload per
  aggregator under 2 GiB, or use one aggregator per node.
* Thousands of tasks creating files at once (`EveryoneWrites`) lock up the
  metadata server. BP5's default aggregation (`TwoLevelShm`, one aggregator
  per node) avoids that. `MaxOpenFilesAtOnce` does not help here: ADIOS2
  documents it as a reader-side limit on how many subfiles one process
  keeps open, for datasets with more subfiles than `ulimit -n` allows.
* Many small files: keep the stripe count low (`lfs setstripe -c 1`). The
  generator stripes each run's `data/` across all OSTs (`-c -1`) because
  BP5 aggregation writes a few large files.

**BP5 aggregation and shared memory.** BP5 coordinates writers through
`/dev/shm`. Several aggregators on one node each take their buffer (4 GB by
default), exhaust the node's memory, and get killed mid-write, leaving
truncated (about 3 MB) files. Use exactly one aggregator per node
(`NumAggregators` = staging nodes; that is also BP5's default), as the
generator's `AnalysisOutput` IO does. Leave `MaxShmSize` at its default:
ADIOS2 documents it as needing at least twice the largest per-process write
and says there is no point in more than 4 GB.

**Headless Catalyst.** On compute nodes without a display, Catalyst must
render through OSMesa (`VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow`,
see the top of this file). ParaView's `lib` directory must also be on
`LD_LIBRARY_PATH`: OSPRay loads its modules (Embree, OpenVKL) from there at
run time. Without it every reader rank segfaults in OpenGL setup
(`glad_gl_get_extensions`) before the first image (#72 step 1). The
generator's jobs set both.

**Catalyst renders with OSPRay.** The Paper 2 Catalyst templates (slices,
isosurface, volume) use OSPRay, the CPU ray tracer: it is faster than
OSMesa's software rasteriser and is the like-for-like comparison with
Ascent's VTK-m ray tracer. Paper 1's template is unchanged.
