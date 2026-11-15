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

**Reader decomposition.** `--reader-decomposition brick` makes each reader
read a 3D brick aligned with the simulation's blocks instead of a slab
along the slowest axis: at 262144 writers and 2048 readers, each reader
owns 128 writer blocks (4 x 4 x 8) and, with the planes it shares with its
neighbours, requests parts of 225 (5 x 5 x 9), instead of pieces of at
least 4096. Measured on
the 64 + 4 node f128 Ascent job (three runs each, 15 Nov 2026), the two
take the same time per reader step (7.7 s slab, 7.8 s brick): brick spends
longer in `EndStep` and less in rendering. The images differ in about 0.1%
of pixels, nearly all by two levels or less, with no seams. The default
stays `slab`. The experiment IDs do not include the decomposition, so
generate slab and brick runs into different `--results-dir`s; the
generator refuses to regenerate an in transit run with the other one.

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
  keeps degenerate triangles.
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
2048 x 2048) and the PNG 0.24 s. A Catalyst script that raises an exception
does not stop the reader: `Vis_Time` drops to near zero and the run looks
fast. In `<id>_catalyst.csv` such a step has `execute` but no `update`,
`render` or `capture`, and the reader's stderr has the Python traceback.
