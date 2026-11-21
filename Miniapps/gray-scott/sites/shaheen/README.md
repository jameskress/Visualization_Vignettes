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

# Kombyne
Kombyne-lite does not run on Shaheen III. Its prebuilt archive calls Open
MPI symbols directly and fails to link against Cray MPICH (`undefined
reference to 'ompi_mpi_int'`), which is why `config.bash` keeps
`ENABLE_KOMBYNELITE=OFF`. It failed for the 2026 WOIV paper and again for
the #71 recheck (8 Nov 2026). Every Kombyne run so far was on Ibex with an
Open MPI built with C++ bindings (`sites/ibex/README.md`): the paper's
Kombyne jobs on 32 nodes (1,024 ranks, the footnote in
`2026-WOIV-scripts/plot_performance.py`), and the #71 recheck at 1024^3 on
64 ranks. Running Kombyne at scale here needs a build of the full Kombyne
from source against Cray MPICH.

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
# directory (steps/node_*.jsonl, or steps/rank_*.jsonl before schema 4).
# The summary CSV is the same, so
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

## In transit reader costs
`--paper pipe` selects the `pipe_*` jobs: Ascent and Catalyst slices,
volume and isosurface, RDMA, one MPMD `srun`, 101 steps (6 outputs), at
64 + 4 nodes (`f128`, 2048^3) and at 256 + 16, 512 + 32 and 1024 + 64 nodes
(4096^3), all 128:1 in tasks, except the isosurface at 256 + 16 nodes,
which runs out of memory (below). `--ascent-timings` turns on Ascent's
per-filter timings (`ascent_filter_times_<rank>.csv` in the run directory,
one file per rank, so leave it off for production runs).

Measured on the Ascent reader, 15 Nov 2026, ADIOS2 2.13.0-rc1, slab
decomposition. Times are the reader's `total_step` in seconds, averaged over
ranks and over output steps 1 to 5 (step 0 is first-touch warm-up).
"Before" is #103 with the new timers only; "after" is this change. At 64 + 4
and 256 + 16 nodes the arms ran at the same time, two runs each; at
512 + 32 the volume pair and at 1024 + 64 every pair ran one job at a
time, back to back (all six 1088-node jobs within 23 minutes), because the
`workq` limit of 2048 nodes per user, shared with other runs, did not fit
them together. Read those as single runs, with the usual cross-batch spread
of up to 2 s per step. Two arms run back to back inside one allocation do
not work: the second `srun` waits for ever ("Requested nodes are busy")
after the first one's teardown.

| Nodes | Field per reader | Slices | Volume | Isosurface |
|---|---|---|---|---|
| 64 + 4 | 2.2 GB | 5.34 -> 2.97 | 4.26 -> 3.07 | 9.75 -> 6.51 |
| 256 + 16 | 4.4 GB | 12.4 -> 6.75 | 8.43 -> 5.46 | out of memory, both |
| 512 + 32 (after with SMT) | 2.2 GB | 8.52 -> 3.96 | 3.96 -> 2.81 | 12.4 -> 9.19 |
| 1024 + 64 | 1.1 GB | 6.29 -> 3.25 | 1.96 -> 1.73 | 6.42 -> 4.66 |

Every image matches the "before" run within the spread two "before" runs
show between themselves: at most a few pixels per 2048^2 frame, on the
bounding box lines and axis labels.

**Where the time went.** Two things, both the reader's own memory
handling, neither the transport:

* *Fresh field buffers every step.* The reader declared its two field
  buffers inside the step loop, so every step allocated, zero-filled and
  page-faulted them, and freed them at the end. That was the time left in
  `Blueprint_Time` after `ADIOS_EndStep`: the new `Read_Alloc` timer
  measures 1.0 to 1.15 s per step at 64 + 4 nodes (2.2 GB per field per
  reader), 2.3 s at 256 + 16 and 0.23 s at 1024 + 64; `Read_Setup` (the
  selection bookkeeping) and `Mesh_Build` (the Blueprint mesh) are under
  1 ms. The buffers now live as long as the reader (Ascent and
  `adios_writer` here, Catalyst in #111). Alone, that
  takes 64 + 4 node slices from 5.0 to 3.7 s, volume from 4.2 to 3.2 and
  the isosurface from 9.6 to 8.7.
* *The allocator.* With the job-wide 32 MiB `MALLOC_MMAP_THRESHOLD_` (see
  "glibc mmap threshold" below), every VTK-m block larger than that is
  mapped when allocated and unmapped when freed, so each step faulted the
  same memory in again. The isosurface took 7.8 million minor faults
  (about 30 GB) and 41 s of system CPU per reader rank per step at 64 + 4
  nodes; the slices about 2 GB. The reader now runs with
  `MALLOC_MMAP_MAX_=0 MALLOC_TRIM_THRESHOLD_=137438953472`
  (`READER_MALLOC_ENV` in the generator), so freed blocks stay in the heap
  for the next step: isosurface system CPU falls to 1.9 s, slices
  3.8 -> 3.0 s and isosurface 8.7 -> 6.5 s per step. The simulation does
  not get it. The price is memory: the 64 + 4 node isosurface's peak RSS
  per reader rank rose from 26.5 to 31.7 GB (8 per node, 370 GB per node).
  It helps Catalyst's readers too (64 + 4 nodes: slices 4.8 -> 3.8 s,
  isosurface 23.9 -> 20.3 s, identical images; peak reader RSS of the
  isosurface 27.7 -> 30.5 GB), so every backend gets it, except in Paper 1's
  jobs, which keep the setup they ran with (#71).

The per-step page faults are recorded as counters (`minflt_*`, analysis
README) next to the timers.

**Ascent's own time** (`--ascent-timings`, 64 + 4 nodes, after):

* Slices: about 0.1 s per slice filter, but the slice normal to z, the
  slab axis, lies in one reader's slab, and that rank spends 0.3 s on it
  (0.8 s at 256 + 16 and 1024 + 64) while the others wait; then
  rendering and compositing, 0.25 s. A brick decomposition would share the
  z slice among readers; it was not measured here.
* Volume: rendering and compositing, 0.9 s.
* Isosurface: contour 1.7 s, then rendering the triangles and compositing,
  2.4 s. At this point of the run the v = 0.1 surface fills the whole cube
  with fine structure, so the triangle count is large.
* Ghost cells: the reader publishes an all-zero `ascent_ghosts` field
  (every cell is owned). Ascent still runs a ghost strip over it: 0.09 s
  per step on the whole mesh plus a pass after each pipeline. Leaving the
  field out (measured, not done) saves 0.05 to 0.25 s per step with the
  allocator setting, more without it.

**Threads.** The reader's 24 OpenMP threads per rank, bound `close` to
cores, are as fast as `spread` and 0.1 s faster than unbound. Both hardware
threads of the same 24 cores (48 threads, `--reader-smt`) save another
0.5 s on the 64 + 4 node isosurface, 0.1 s on volume and 0.05 s on slices.
Catalyst gains the same (64 + 4 nodes, two runs each, frames
bit-identical): isosurface 18.78 -> 18.25 s, slices 3.49 -> 3.44 s, volume
2.65 -> 2.62 s; its reader keeps `OMP_PROC_BIND=false` and gets
`LP_NUM_THREADS=48`. A node has 192 cores with two hardware threads each,
and without this the second thread of every reader core sat idle; the
reader now uses it. So it is on by default (`--no-reader-smt` turns it
off). It drops the job-wide `--hint=nomultithread` in in transit jobs; the
simulation's `srun` keeps its own, so the simulation still runs one thread
per core. Paper 1 jobs keep the setup they ran with.

**Isosurface at 256 + 16 nodes runs out of memory**, before and after:
each reader holds 4.4 GB per field, and the contour of a surface that fills
the domain needs more than a node's 370 GB across 8 readers. The same
holds for any 4096^3 isosurface with 16 staging nodes. Either use more
staging nodes for that size (32, as at 512 + 32, keeps 2.2 GB per reader)
or drop it from the matrix.

## After the runs
Each run's job first saves its own batch script as `<results>/<id>_job.sbat`
and the job-wide network, allocator and Mesa settings it exported (`FI_*`,
`CM_*`, `MALLOC_*`, `MPICH_*`, `Sst_*`, `ADIOS2_*`, `GALLIUM_*`, `LP_*`) as
`<results>/<id>_env.txt`, so runs made with different settings can be told
apart. Thread settings are not in that file because each `srun` sets its
own (the in transit reader has 24 cores per rank, bound for Ascent and
unbound for Catalyst; the simulation 3); read them from the saved script.

When a run ends, its job submits a one-node job, `reduce.sbat` in the run
directory, and exits, so the run's nodes are released at once (reducing
tens of thousands of per-rank files on a 1088-node allocation used to keep
it idle for minutes, once for over half an hour, #72). The reduction job
writes `reduce-<jobid>.out` and produces:

* `<results>/<id>_writer.csv`, from the newest run directory under `perf/`,
  with that run's `metadata.json` and `summary.json` copied beside it as
  `<id>_metadata.json` and `<id>_summary.json`;
* `<results>/<id>_reader.csv`, from `reader_timers/` (in transit runs);
* both CSVs have per-step mean, min, max, 25th and 75th percentile for
  every timer and counter the logs hold: the reader's `ADIOS_Wait` (its
  BeginStep), `ADIOS_EndStep`, `Blueprint_Time` and `Vis_Time`, the
  writer's `io` (BeginStep, Put and EndStep), `halo` and counters
  (`c_<name>`). Summaries reduced before this was added hold only the
  writer's five timers; re-run `reduce_timers.py` on the archived
  `reader_timers.tar.gz` to get the rest;
* `<results>/<id>_catalyst.csv`, from `catalyst_timers/` (in transit
  Catalyst runs; see "Catalyst reader performance");
* `perf/`, `reader_timers/` and `catalyst_timers/` are then compressed to
  `.tar.gz`, to save inodes.

`large-runs/audit_runs.py --results-dir <results>` lists runs that are missing, failed
(time limit, out of memory, crash) or still running. If a run's reduction
job could not be submitted, its Slurm log says `REDUCE_SUBMIT_FAILED`
(`grep -l REDUCE_SUBMIT_FAILED <results>/*/slurm-*.out`); if it was
submitted but failed, check `<run>/reduce-*.out`. Either way,
`sbatch <run>/reduce.sbat` redoes that run's reduction, for any experiment
(`xport_*`, `scale_*` or `paper2_*`); it first restores `perf/`,
`reader_timers/` and `catalyst_timers/` from their `.tar.gz` if an earlier
reduction archived them.
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

**Reader parameters.** Until 14 Nov 2026 the reader built ADIOS2 with no
XML, so `ControlModule=epoll` reached the writers only and every reader ran
on `select()`. That was harmless while each reader stayed under 1024 writer
connections, but a slab reader at 262144:2048 reaches at least 4096 writers
and would hang as the reproducer did (ADIOS2 #5272). The generated XML now
has an `AnalysisInput` block with `ControlModule=epoll` and the data plane,
which the reader loads; its rank 0 prints the parameters in use. Runs
before that date had readers on `select()`.

**Reader decomposition: brick is the default (16 Nov 2026).** Each in
transit reader reads a 3D brick aligned with the simulation's blocks
(`--reader-decomposition brick`, now the default) instead of a slab along
the slowest axis (`--reader-decomposition slab`, the old default and the
layout of every earlier run). At 262144 writers and 2048 readers a brick
owns 128 writer blocks (4 x 4 x 8); a slab takes pieces of at least 4096.
Each piece also holds its neighbour's first plane on every axis where it is
not the last, so the pieces meet; the reader now takes those planes from
the neighbouring readers over MPI (`--reader-shared-planes exchange`, the
default) instead of from the writers (`read`, the old way).

How it got here, all on the f128 and Paper 2 jobs:

1. *Brick looked no better (15 Nov, planes read from the writers).* At
   64 + 4 nodes the two took the same time per Ascent step (7.7 s slab,
   7.8 s brick): brick rendered faster but spent longer in `EndStep`.
2. *The read was the cost.* With the readonly reader (no visualization) at
   64 + 4, `EndStep` was 2.08 s slab and 2.80 s brick: 0.73 s per step of
   pure transport. A brick's shared planes on the x and y faces are strided
   in the writer blocks; a slab's are contiguous.
3. *Exchanging the planes removes it.* Reading only the owned box and
   taking the planes from the neighbouring readers (16 Nov, 2 runs per arm,
   one shuffled batch), seconds per reader step:

   | Reader | Planes | Step | `EndStep` | `Halo_Exchange` |
   |---|---|---|---|---|
   | readonly, slab | read | 2.08 | 2.08 | 0 |
   | readonly, slab | exchange | 2.06 | 2.04 | 0.018 |
   | readonly, brick | read | 2.80 | 2.80 | 0 |
   | readonly, brick | exchange | 2.09 | 2.06 | 0.026 |
   | Ascent slices, slab | read | 3.09 | 2.06 | 0 |
   | Ascent slices, slab | exchange | 3.03 | 2.03 | 0.041 |
   | Ascent slices, brick | read | 3.48 | 2.89 | 0 |
   | Ascent slices, brick | exchange | 2.77 | 2.17 | 0.029 |

4. *Brick then wins at every size, on every pipeline, for both backends.*
   Both with exchange (16 Nov; 512 + 32: 2 runs per arm, concurrent;
   1024 + 64: 1 run per arm), total seconds per reader step, slab -> brick:

   | Nodes | Backend | Slices | Volume | Isosurface |
   |---|---|---|---|---|
   | 512 + 32 | Ascent | 4.10 -> 2.85 | 2.98 -> 2.86 | 7.91 -> 6.69 |
   | 512 + 32 | Catalyst | 6.21 -> 3.09 | 2.91 -> 2.85 | out of memory -> 20.35 |
   | 1024 + 64 | Ascent | 2.95 -> 1.57 | 1.78 -> 1.66 | 4.71 -> 3.90 |
   | 1024 + 64 | Catalyst | 5.18 -> 1.79 | 2.05 -> 1.61 | not run |

   `EndStep` is now the same for both (2.18-2.27 s at 512 + 32, 1.09-1.17 s
   at 1024 + 64). `Halo_Exchange` is 0.016-0.03 s for a brick and
   0.07-0.24 s for a slab, whose shared plane is a whole 4096^2 plane.
   Against planes read from the writers, a brick's `EndStep` at 1024 + 64
   drops from 1.47-1.54 s to 1.13-1.17 s. The Catalyst isosurface at
   512 + 32, out of memory with slabs (33-34 GB per rank peak, both runs),
   fits with bricks, so every cell of the matrix runs for both backends.

The images: brick with exchange and brick with planes read are identical
(0 to 12 pixels). Slab and brick differ only in the speckle of Ascent's
volume rendering (where the rays sample), with no seams; brick volume
images are stable across node counts (32 pixels between 512 + 32 and
1024 + 64), slab images are not (6768 pixels).

What this shows: how the readers divide the data matters as much as how
fast the transport is. A brick lines each reader up with whole writer
blocks, so each reader talks to fewer writers and renders a compact
piece, but only once nothing forces the transport to fetch scattered
data. A single plane per face, read from the writers, cost more than the
whole rendering gain; moved to a reader-to-reader exchange it costs
about 0.03 s, and brick becomes the faster layout everywhere we measured
(up to 2.9 times faster for Catalyst slices at 1024 + 64), with less
memory per reader.

The experiment IDs do not include the decomposition or the plane setting,
so generate each combination into its own `--results-dir`; the generator
refuses to regenerate an in transit run with different settings, and
settings written before an option existed count as slab and `read`.

**Other engines and transports.** SST over WAN (TCP) needs
`ControlModule=select`; with `epoll` it aborts at once. SSC uses MPI
one-sided communication and is fast, but with ADIOS2 created on a split
communicator (not `MPI_COMM_WORLD`) the writers and readers never see each
other and the job hangs.

**Telemetry.** `generate_experiments.py --telemetry` (off by default)
records, for every run:

* `node_sampler.sh`, one task per node started with `srun --overlap` just
  before the run: Cray `pm_counters` (node, CPU and memory power and
  cumulative energy, CPU temperatures), `/proc` CPU ticks, available memory
  and load, and the Slingshot NIC's sent and received bytes and its NACK
  and retry counters, at 1 Hz, in `telemetry/<job id>/nodes/<host>.csv` (one directory per job, so a
  resubmitted run never mixes samples with an earlier job's).
  The sampler step runs with `--network=no_vni --mpi=none`: with Slurm's
  defaults it was given Slingshot network resources and a PMI wire-up it
  does not use, and MPI_Init in the run's own step then failed on some
  nodes (`fi_getinfo() failed ... No data available`). Both 1920 + 128 node
  sweep runs and one 64 + 4 run were lost that way. All of it is
  readable without privileges. Shaheen's CPU nodes have one NIC each
  (`cxi0`). On 2 nodes, a step using every core ran no slower with the
  sampler beside it (2.725 s per task alone, 2.75 s with it, 2.745 s alone
  again) and started without waiting.
* An environment snapshot: the job's settings variables, `module list`,
  `ldd` of both binaries, the source revision and `scontrol show job`.
* The platform and the network, before the run (`node_platform.sh`):
  * one line per node in `platform_nodes.txt`: kernel, CPU frequency
    driver, governor, boost and maximum, CPU count, NUMA nodes, memory,
    huge pages, 1-minute load, NVIDIA driver, NIC firmware, link speed and
    state; a node that differs from the rest shows up there;
  * the full detail of one node in `platform.txt`: `lscpu`, `numactl -H`,
    `cxi_stat`, OS release, `fi_info --version`, Slurm's version and the
    kernel command line;
  * `scontrol show topology` in `topology.txt`: Slurm's network tree. On
    Shaheen III that is 288 leaf switches of 16 nodes (named by hardware
    location, `x1005c0r3`) and 18 dragonfly groups of 256 nodes
    (`group4` is cabinet x1005, nid00001 to nid00256); traffic between
    groups crosses the global links that every job shares.

  The reduction copies them beside the results as `<id>_tel_platform*.txt`
  and `<id>_tel_topology.txt`. Each probe is limited to 120 s; the probes add
  two Slurm steps before the run, so the in transit run is step 3 (3+0 the
  simulation, 3+1 the reader).
* When a resubmitted job's reduction finds results from an earlier job, it
  clears that job's exports and keeps its archives as
  `<dir>.job<old job>.tar.gz`; a run also sets aside timer directories an
  earlier job left unreduced as `<dir>.before<job>`. Nothing reads either
  afterwards: delete them by hand when no longer wanted.
* `SLURM_ACCTG_FREQ=task=30,energy=30`, so steps get memory and energy
  figures (Shaheen samples every 600 s by default).
* Darshan 3.4.7 (`build-darshan.sh <software dir>`; Shaheen has no Darshan
  module), preloaded only into the run's own `srun` commands: every file
  read and write, through POSIX, MPI-IO and STDIO, with Lustre striping, in
  `telemetry/<job id>/darshan/`. It does not see SST's network transfers,
  which the NIC counters cover. On the 64 + 4 node f128 Ascent run it logged
  the 2048^3 checkpoint restart (137 GB read, about 37000 opens) and the
  images and logs (200 MB written), and reader steps took 4.75 and 5.44 s
  with it against 5.28 s without. `--no-darshan` leaves it out.
* Cray MPICH's NIC counter summary for the run's MPI traffic
  (`MPICH_OFI_CXI_COUNTER_REPORT=2`): minimum, mean and maximum over the
  job's NICs of traffic, pauses, NACKs and cache behaviour, printed when MPI
  finalizes and saved by the reduction.

The run's job passes its ID to the reduction job (`RUN_JOB_ID`; to rerun a
reduction by hand, `sbatch --export=ALL,RUN_JOB_ID=<run job> reduce.sbat`),
which then saves `sacct` for every step (`<id>_sacct.txt`), the Darshan
logs and their `darshan-parser` totals (`<id>_darshan/`), the MPICH counter
summary (`<id>_mpich_cxi_summary.txt`), the job they belong to
(`<id>_tel_job.txt`: a reduction of another job of the same experiment
removes all of these first),
writes `<id>_telemetry.json` (energy per run and per step's nodes, mean
power, CPU use, NIC bytes and retries) and archives the per-node samples.
An in transit run is one heterogeneous step: `.1+0` is the simulation and
`.1+1` the reader. Slurm reports no CPU or energy for the reader component,
so the sampled figures are the only ones for its nodes. On the 64 + 4 node
f128 Ascent run the simulation's nodes sampled 1.47 MJ against sacct's
1.54 MJ (its window is slightly longer), and the reader's 4 nodes 72.7 kJ
against sacct's 0. Prefer the sampled energy: sacct polls energy every 30 s
here, and on the 256 + 16 node `readonly` sweep run it gave the simulation
step 9.66 MJ against 13.06 MJ sampled, and the sampler's own step 0. CPU use
is a fraction of all hardware threads, including the second thread of each
core that the jobs leave idle.

**Corpus index.** `2026-WOIV-scripts/corpus_index.py <out prefix>
<results dir> ...` writes one row per run (any `<id>_job.sbat`) to
`<out prefix>.csv` and `.jsonl`: what was run (nodes, ranks, backends,
grid, decomposition, ADIOS2 version, build), headline numbers (simulation
and reader step times over steps 1 and up, the writer's io, the reader's
wait (BeginStep), EndStep, build and vis times, sampled energy and power, Darshan bytes) and the path of every
artifact. Provenance and placement columns:

* `sim_git_commit`, `sim_git_describe`, `reader_git_commit`: the commit
  each program was built from. Builds from `git archive` (as on Shaheen)
  get it from `cmake/git_archive_commit.txt`, which `git archive` fills in;
  a tree copied another way can set `GS_SOURCE_COMMIT` when it is built.
  Builds before this was added say `unknown`. An exported tree cannot tell
  that a file was changed after the export, so never patch one in place
  (copying a single file over it, say): export again with `git archive`, or
  the build will claim a commit it does not hold.
* `adios2_library`: the ADIOS2 library the simulation actually loaded (its
  install directory names the build, for example the 653c9e3 commit).
* `platform_*`: rank 0's node (kernel, OS, CPU governor and boost, NUMA
  nodes, memory, NVIDIA driver, load at start, whether the job owned its
  nodes), and from `platform_nodes.txt` how many nodes were listed, how many
  distinct platforms they have (1 when every node matches; load is left
  out), the NIC firmware versions seen and the highest node load at start
  (`platform_max_load_1min`: a node another job was using shows up there).
* `placement_*`: from the job's node list, the simulation's hostnames and
  the topology, the dragonfly groups and leaf switches the simulation and
  the readers span, and how many groups they share. For runs from before
  the topology capture, pass a saved topology: `corpus_index.py --topology
  topology-20261116.txt ...` (`/scratch/kressjm/vv-telemetry` has one). The
  node lists of past runs are in their telemetry, so their placement can be
  rebuilt; the 2816 + 128 sweep runs, for example, spread the simulation
  over 16 to 18 of the 18 groups and the 128 reader nodes over 1 group and
  9 switches.
 Missing inputs leave their columns empty. The reduction of a
large run can take a while: 65536 per-rank timer files took over 54
minutes, so the reduction job's limit is 4 hours.

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
and the new per-run table is never built. (A `brick` reader, below, is
different. Its owned box lines up with writer blocks when every reader
boundary falls on a writer boundary. `L` dividing evenly by both rank counts
is enough but not needed: at `L` = 66 four writers split an axis at 17, 34
and 50 and two readers at 33 (no match), while at `L` = 67 four writers
split at 17, 34 and 51 and two readers at 34 (a match). Even then, the plane it reads from each
neighbour cuts into the next writer blocks in the fast dimensions, so at
4096^3 with 262144 writers and 2048 readers an interior brick owns 4 x 4 x 8
blocks but requests parts of 5 x 5 x 9. Its requests can have gaps, and that
code may run.) What the commit changes for us
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
Ascent's VTK-m ray tracer. Paper 1's template is unchanged. Measured at
64 + 4 nodes with the fixes below (two runs each): slices 1.60 s per step
with OSPRay against 2.45 and 2.60 s with llvmpipe on 24 threads; the
isosurface 43.5 s against 50.7 and 51.5 s.

## Catalyst reader performance

The in transit Catalyst reader rendered 5 to 13 times slower than Ascent's
(`Vis_Time` 13.7 s per step against 1.1 s at 64 + 4 nodes, 28 s against
4.3 s at 256 + 16). Two settings in the generated jobs did it; neither is
in ParaView or the reader.

* **The reader ran on one core.** The reader's `srun` set
  `OMP_PLACES=cores OMP_PROC_BIND=close`. The OpenMP runtime binds the
  process's main thread to its first place, one core, at start-up, and
  every thread that OpenMP does not create inherits that mask: OSPRay's and
  VTK's TBB pools and llvmpipe's threads. A probe of a running reader showed
  each rank's `Cpus_allowed_list` as a single core (`0`, `24`, `48`, ...),
  and the old runs used about 16 CPU seconds in a 17 s step. Ascent's VTK-m
  threads are OpenMP threads, each bound to its own core, so Ascent was not
  affected.
* **Mesa's reference rasteriser.** The job exported `GALLIUM_DRIVER=softpipe`
  and `LP_NUM_THREADS=1`. OpenGL still draws around OSPRay (the image blit,
  IceT's buffers, the scalar bar, the orientation axes), and softpipe took
  about 6 s of each 2048 x 2048 frame. llvmpipe is Mesa's JIT rasteriser.
* `OSPRAY_THREADS` does nothing: OSPRay 2.7 reads `OSPRAY_NUM_THREADS`. Once
  unbound, its TBB pool uses the rank's 24 cores without it (setting
  `OSPRAY_NUM_THREADS=24` changed nothing), so the generator no longer sets
  either.

The generator now gives the Catalyst reader `OMP_PROC_BIND=false
LP_NUM_THREADS=24` and the job `GALLIUM_DRIVER=llvmpipe`. The Ascent reader
keeps its binding: unbound, Ascent's slice step took 1.45 and 1.53 s
against 1.07 and 1.15 s. Paper 1 jobs keep the settings they were run with.

Slices, mean seconds per step over steps 1 and up (two runs per arm,
submitted together in shuffled order; the ADIOS2 2.13.0-rc1 build of PR
#103, so Ascent has its in-place mesh):

| Nodes | Catalyst before: `Vis_Time` / total | Catalyst after | Ascent |
| :--- | :--- | :--- | :--- |
| 64 + 4 | 13.94, 13.91 / 17.34, 17.11 | 1.59, 1.62 / 4.92, 4.95 | 1.07, 1.15 / 5.15, 5.03 |
| 256 + 16 | 27.34, 27.38 / 34.07, 34.05 | 4.29, 4.53 / 10.85, 11.19 | 4.95, 5.04 / 12.45, 12.53 |
| 512 + 32 | 24.95, 25.11 / 27.82, 27.99 | 3.88, 4.39 / 6.85, 7.36 | 5.17, 4.71 / 8.98, 8.56 |
| 1024 + 64 | 23.73 / 25.23 (10 Nov, one run) | 4.14, 4.69 / 5.65, 6.22 | 4.95, 5.28 / 6.50, 6.85 |

Volume `Vis_Time`: at 64 + 4, Catalyst 6.61 and 7.27 s before, 1.51 and
1.28 s after, Ascent 1.05 and 1.04 s; at 512 + 32, Catalyst 6.78 and 6.79 s
before, 0.48 and 0.63 s after, Ascent 0.54 and 1.08 s. The 1024 + 64
"before" in the slice table is the 10 November run of an older build, not
part of the A/B (the queue was shared, so that arm was dropped).

**Renders.** Unbinding changes no pixel. llvmpipe instead of softpipe
changes 68,000 to 86,000 of the 4.2 million pixels of a slice frame, almost
all by one level (OSPRay's image as Mesa blits it); the 236 pixels that
change by more than 32 levels are the orientation axes' lines and the
scalar bar's labels, the same 236 at 64 + 4, 256 + 16 and 512 + 32. A
volume frame changes in 674 pixels, all on those overlays. Each arm's frames
were identical from run to run. The same 4096^3 data rendered on different
reader counts differs only at slab seams: 102 to 108 pixels between 256 + 16
and 512 + 32, before and after alike, and 44 to 48 between 512 + 32 and
1024 + 64 after.

**The isosurface** was slow for other reasons: at 64 + 4 nodes after the
fixes above, 44 s per step, against 6.2 s for Ascent. The stage timers
showed Contour 21.7 s, GhostCells 8.4 s and OSPRay 11 to 13 s on rank 0.

* ParaView 6.0's Contour runs serial synchronized templates on image data.
  Its `FastMode` property should switch to flying edges, which is
  multithreaded, but `vtkPVContourFilter::ContourUsingSuperclass` copies
  every setting to the filter it runs except that one, so setting it changes
  nothing (43.4 and 43.7 s). The template now uses the `FlyingEdges3D` filter
  from ParaView's `AcceleratedAlgorithms` plugin, with Contour's normals and
  scalars. It is also the algorithm VTK-m's contour (Ascent) uses. About 2%
  of pixels change, by 1 to 3 levels and at most 78, as isolated pixels over
  the surface: flying edges triangulates ambiguous cells differently and
  keeps degenerate triangles. ParaView issue
  [#23459](https://gitlab.kitware.com/paraview/paraview/-/work_items/23459)
  reports the `FastMode` bug. The script loads the plugin by its path in the
  install the job's `CATALYST_LIB_DIR` points at, found at run time for the
  running ParaView's version: with ParaView 6.2.1, both the Shaheen
  module and our own GCC 13 superbuild, Catalyst does not find the install's
  plugin list, so loading it by name stops the run with "Plugin
  'AcceleratedAlgorithms' not found" (6.0 found it). `PV_PLUGIN_CONFIG_FILE`
  would also fix that, but ParaView force-loads every plugin in that list on
  every rank.
* GhostCells copies every array it is given, and `u` is not drawn. The
  template now passes only `v` and the ghost flags: bit-identical frames,
  44 to 38 s. With both `u` and flying edges' working arrays, a 64 + 4 run
  ran out of memory; with `v` alone it fits.
* Together: 19.5 and 20.4 s per step at 64 + 4 (filters 7.9 s, OSPRay
  11 to 12 s). OSPRay's share is the dense surface (v = 0.1 lies in the
  noise, so it has tens of millions of small triangles): VTK hands OSPRay a
  copy of the mesh every frame and Embree rebuilds its BVH. OpenGL was
  slower still (above).
* At 512 + 32 nodes (4096^3) the Catalyst isosurface runs out of memory on
  the readers at the first output, with flying edges and with Contour alike
  (two runs and one run; the reader component's sampled peak was 27.5 GB
  per rank, 8 ranks on a 384 GB node). Each rank holds as many points as at
  64 + 4, so the surface itself is the difference. Ascent's isosurface there
  takes 8.0 s per step. Fewer readers per node would fit it; that changes
  the fan-in, so it is not done here.
* With the job's old settings the 64 + 4 Catalyst isosurface also ran out
  of memory, in both runs.

**Reader allocations.** The ascent-perf work (#110) found every backend
reallocating its field buffers each step and the job's
`MALLOC_MMAP_THRESHOLD_` sending large VTK allocations to `mmap`.

* The Catalyst reader now keeps `u`, `v` and its point ghost flags across
  steps (members of `CatalystBackend`; `ReadRepartition` resizes a buffer
  only when its size changes), and refills the flags only when the piece's
  shape changes. The flags were a serial pass over every point each step;
  the `Mesh_Build` timer now reads 0.47 s on the first step and about 70 us
  after. Total seconds per step, two runs each, with the settings above:
  slices at 64 + 4 4.61 and 4.83 to 3.47 and 3.49 (`Blueprint_Time` 3.03 and
  3.23 to 2.10 and 2.11; system CPU 2.9 to 1.0 s per step), at 256 + 16
  10.72 and 10.77 to 8.81 and 8.74, at 512 + 32 6.76 and 7.32 to 6.22 and
  6.35; the isosurface at 64 + 4 23.33 and 24.93 to 23.09 and 22.80
  (`Blueprint_Time` 3.85 to 2.47). Frames are bit-identical before and after
  at all four, and still change from step to step. Peak reader memory rises
  by 0.3 to 1.0 GB, since the buffers now stay allocated between steps.
* `MALLOC_MMAP_MAX_=0 MALLOC_TRIM_THRESHOLD_=137438953472` on the reader
  (two runs each at 64 + 4, frames bit-identical) cut the slice step from
  4.95 and 4.69 s to 3.77 and 3.76 s, and the isosurface from 24.05 and
  23.74 s to 21.23 and 19.37 s, with peak reader memory on the isosurface up
  from 27.7 to 30.5 GB. #110 adds it to the reader's environment for both
  backends.

**Stage timers.** `Vis_Time` covers all of `catalyst_execute`. Each Paper 2
Catalyst script now writes ParaView's own scoped log to
`catalyst_timers/rank_<r>.log` when `GS_CATALYST_TIMERS=1`, and the reader's
`srun` turns on the `PARAVIEW_LOG_CATALYST_VERBOSITY`,
`PARAVIEW_LOG_PIPELINE_VERBOSITY` and `PARAVIEW_LOG_RENDERING_VERBOSITY`
categories (rank 0 also prints them to stderr). The reduction job runs
`catalyst_timers.py` and writes `<results>/<id>_catalyst.csv`: per step, the
mean and maximum over ranks of `execute` (`Vis_Time`), `overhead` (the
Blueprint check and Catalyst's bookkeeping, about 1 ms; the zero-copy
conversion to VTK runs inside `update`), `update` (the filters), `render`,
`icet_pass`, `icet_render` (the local OSPRay render), `icet_composite`,
`capture` and `png_write`. At 256 + 16 nodes the slice step after the fix
is filters 1.6 to 1.8 s, IceT's composite about 2.5 s (128 ranks at
2048 x 2048) and the PNG 0.24 s.

**A failing Catalyst script stops the run.** ParaView returns an error
status from `catalyst_execute` when the script fails to import or raises in
a step (102, "pipeline failed to initialize" or "failed to execute"), and
skips that pipeline on every later step. The reader and the simulation used
to ignore the status, so a broken script logged a near-zero `Vis_Time` (or
`execute` time) for steps that drew nothing, and looked like a very fast
run. Both now stop at once: every rank prints the step and status and calls
`MPI_Abort` where the error is seen, before any teardown (an SST close could
wait for its peers), and `--kill-on-bad-exit` ends the other program of an
in transit job. The Python traceback is above the error in the job's
stderr. A failed run keeps no per-step timings: they are written at the end
of the run.
