# Stack (since 17 Nov 2026)

Builds and runs here use one stack; `config.bash` and `MODULES.sh` point at it:

- ParaView 6.2.1 (Catalyst 2.0), our own superbuild in `software/paraview-6.2.1-gcc13-build` (script `software/build-paraview-6.2.1-gcc13.sh`, the same options as the 6.0.1 build, Viskores off). Not the `paraview/6.2.1-egl` module: its VTK carries its own Viskores (64-bit IDs, TBB), which shares symbols with Ascent 0.9.6's Viskores (32-bit IDs) in the reader and breaks the build. Before 17 Nov the Catalyst numbers came from the 6.0.1 superbuild in `software/paraview-build`, so they are not comparable with later runs.
- GCC 13.3.1 (`gcc-native/13.2`, the same compiler as the center's 6.2.1 module) and cray-mpich 8.1.32. Build on login5, which has the limits for long builds.
- ADIOS2 `release_213` at 8d7270164, built with GCC 13 as a minimal transport build: MPI, SST and BP5, with curl, HDF5, OpenSSL and the compressors off. A ParaView superbuild bundles its own curl and HDF5. An ADIOS2 built against the system curl and OpenSSL shares the `libcurl.so.4` soname with ParaView's copy and binds to it at run time; that was the suspected cause of a crash at exit after `catalyst_finalize` with the module (under test). Build script: `software/build-adios2-r213-8d7270164-gcc13.sh`.
- Ascent 0.9.6 (Conduit 0.9.9, Viskores, 32-bit IDs), built with GCC 13 and our patch `patches/ascent-0.9.6-local-mesh-index.patch` (see "Building Ascent": without it inline Ascent at 64 ranks per node runs out of memory above about 150,000 ranks). Its build script brings HDF5 2.0.0 (`libhdf5.so.320`), while ParaView ships HDF5 1.14 (`libhdf5.so.310`). So a reader with Catalyst loaded holds both, with the same function names; with Ascent 0.9.5 both were `.310` and one copy loaded. It is the first suspect for any HDF5 error or crash at exit in a Catalyst run (under test, 17 Nov 2026).
- Darshan is still the GCC 12.3 build in `software/darshan-3.4.7-install`; it is only preloaded for `--telemetry`. `build-darshan.sh` now installs to `darshan-3.4.7-gcc<major>-install` and refuses to overwrite, so a GCC 13 rebuild cannot replace the install earlier telemetry ran with; pass the new prefix with `--darshan-prefix`.
- `generate_experiments.py --bin-path` must be a Gray-Scott build against the same ParaView as `CATALYST_LIB_PATH`; the settings check refuses a results directory whose runs used another Catalyst.

Paper 1 Catalyst jobs generated from this tree also use this 6.2.1 build. Reproducing the published Paper 1 runs needs the older trees and the 6.0.1 superbuild.

# Running with Catalyst on a workq node: set the OSMesa window first

The Catalyst implementation in `software/paraview-build` (6.0.1, used until 17 Nov 2026) is an EGL build. The generator's jobs still set the OSMesa window below with the 6.2.1 superbuild, so the render path matches the earlier runs. On a
`workq` node, which has no GPU, its EGL window creation falls into the system
Mesa (`libEGL_mesa` / `libgallium`) and segfaults in `_glapi_add_dispatch` at
the first render, on a handful of ranks, before any image is written (21 Oct
2026, core backtrace). The superbuild also carries OSMesa, so tell VTK to use
its own offscreen window and EGL is never touched:

```bash
export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow
# OSPRay (used by the Paper 2 Catalyst scripts) loads its modules from here:
export LD_LIBRARY_PATH=/scratch/kressjm/Visualization_Vignettes/software/paraview-6.2.1-gcc13-build/install/lib:$LD_LIBRARY_PATH
srun ... ./gray-scott --settings-file=settings.json
```

The simulation alone (`output_type: none`) is unaffected; only the Catalyst
render path needs it. A 256^3 run on one node (64 ranks x 3 threads) with a
JPG every 10 steps is the HPC Saudi 2026 live demo.

# Running ctest

Run the tests in a one-node job, not on a login node. `MPIEXEC_EXECUTABLE`
is `srun` here, and the render and ghost-volume checks take its
`MPIEXEC_NUMPROC_FLAG` (`-n`) from CMake (#139). Two things the job needs:

- the OSMesa window, as above, or the render check's default EGL window fails;
- Python packages for the checks: the tests use `/usr/bin/python3.11` with
  numpy, Pillow and h5py from the user site, but `~/.local` on a compute
  node is `/scratch/<user>/.local`, not the login node's. Install them there,
  or point `PYTHONUSERBASE` at a copy of the login node's user site.

```bash
#SBATCH --nodes=1
source sites/shaheen/MODULES.sh
export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow GALLIUM_DRIVER=llvmpipe
# Once, from a login node: copy the login node's user site where jobs see it.
#   mkdir -p /scratch/$USER/pyuser/lib/python3.11
#   cp -a ~/.local/lib/python3.11/site-packages /scratch/$USER/pyuser/lib/python3.11/
export PYTHONUSERBASE=/scratch/$USER/pyuser
unset DISPLAY
cd build && ctest --output-on-failure
```

All 17 tests passed this way on 22 Nov 2026 (ParaView 6.2.1 superbuild dev
tree, 1 to 4 ranks).

# Building Ascent
Ascent 0.9.6 from its tag, with our patch, in Release (`build_ascent.sh`
defaults to Debug), GCC 13, MPI, OpenMP and 32-bit IDs. Build on login5.
Ascent did not pass the `cc` and `CC` compiler wrappers to all of its sub
builds, hence `CC`/`CXX` and the host config.

```bash
module load PrgEnv-gnu/8.6.0 gcc-native/13.2 cmake/3.28.3
module unload cray-libsci cray-python
export CRAYPE_LINK_TYPE=dynamic
export CC=$(which cc) CXX=$(which CC)

git clone --recursive -b v0.9.6 https://github.com/alpine-dav/ascent.git
cd ascent
git apply <repo>/Miniapps/gray-scott/sites/shaheen/patches/ascent-0.9.6-local-mesh-index.patch

cat > shaheen-host-config.cmake << EOL
# Forcefully add the C++17 standard flag to the compiler flags.
# This is more direct than CMAKE_CXX_STANDARD and harder for Umpire to ignore.
set(CMAKE_CXX_FLAGS "\${CMAKE_CXX_FLAGS} -std=c++17" CACHE STRING "C++ Compiler Flags" FORCE)
# Also add the filesystem library to the linker flags for good measure.
set(CMAKE_EXE_LINKER_FLAGS "\${CMAKE_EXE_LINKER_FLAGS} -lstdc++fs" CACHE STRING "Linker Flags" FORCE)
EOL

env prefix=<build root> install_dir=<install dir> build_config=Release build_jobs=16 \
    enable_mpi=ON enable_openmp=ON enable_64bit_ids=OFF \
    ./scripts/build_ascent/build_ascent.sh -H shaheen-host-config.cmake
```

`build_ascent.sh` skips any dependency whose install directory already
exists, so to rebuild only Ascent, point `install_dir` at a directory that
links the existing dependency installs (`conduit-v0.9.9`, `viskores-1.2.0`
and so on) and has no `ascent-checkout`, and use a new `prefix`: an old
build tree keeps its cached install prefix and would install over the
previous Ascent.

**The patch** (`patches/ascent-0.9.6-local-mesh-index.patch`, 23 Nov 2026).
On every `Execute()`, Ascent's `AddPublishedMeshInfo()` calls Conduit's
MPI `generate_index`. That gathers every rank's mesh index schema to every
rank, as JSON (about 3.3 KB per rank here), and parses all of them, so each
rank briefly holds about 34 KB per rank in the job. Nothing in a run uses
the result; it only feeds `ascent.info()`, the `save_info` action and the
web interface. Inline Ascent at 64 ranks per node peaked at 1.0 GB per rank
with 16,384 ranks, 2.7 GB with 65,536, 6.95 GB with 196,608 (the job was
killed) and 7.9 GB with 212,992, where the nodes ran out of memory at the
first render. The patch builds the index from the rank's own domain with
the global domain count, which is the same index when every rank publishes
the same mesh, as Gray-Scott does. At 32,768 ranks (256 nodes, 128 ranks
per node, 64^3 cells per rank, inline volume) it took the mean peak RSS
per rank from 1410 to 515 MB and the time per rendered step from 1.30 to
0.51 s; 4096 ranks: 188 to 164 ms. Frames are bit-identical at 512, 4096
and 32,768 ranks. Ascent and Conduit `develop` still have the gather
(checked 23 Nov 2026). Ascent timings from the patched build are not
comparable with earlier ones.

# ADIOS2
The current build is the one in Stack above (release_213 at 8d7270164, minimal
options); do not rebuild with default options, which turn on HDF5 and curl.

History: 2.12 or newer was needed for in transit runs. With 2.11, SST over RDMA on Shaheen III hung or performed
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

So `generate_experiments.py` writes no Kombyne jobs by default, and Paper 1
on Shaheen has no Kombyne points. Before this, it always wrote
`paper1_func_N0064_inline_kombyne_data` and `_render`, and with a build
without Kombyne every rank stopped at once with
`Invalid output_type: kombyne` (srun then reports the remaining tasks as
`Killed`; it is not an out-of-memory kill). `--with-kombyne` adds the two
jobs back for a build configured with `ENABLE_KOMBYNELITE=ON`; the
generator then checks that the `gray-scott` in `--bin-path` records
`kombynelite` among its enabled backends and stops if it does not (a
binary built before the run metadata recorded its backends also stops).
Without the flag, the generator also deletes those two scripts from
`--output-dir` if an earlier generation left them, since `orchestrate.py`
submits every `*.sbat` it finds there.

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
# Kombyne: only the 2026 WOIV runs have these (made on Ibex; see Kombyne above).
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

## Repeats and large runs

Every measured run is generated three times (`--repeats`, default 3), as
`<id>_r01`, `<id>_r02` and `<id>_r03`, each with its own results directory
and job; Paper 1's runs and the initialisations stay single (the repeats
share the checkpoint). Each run's settings record `repeat_of`, `repeat`
and `repeats`. One run is easily skewed by a noisy node or a busy file
system (the Catalyst start-up swings between 6 and 25 s on the same
build, Catalyst reader performance below), so a configuration is judged by
the median of its repeats, as the regression suite does with `--repeat`.

`orchestrate.py --submit` shuffles the submission order (the seed is
printed; `--seed` reproduces an order, `--no-shuffle` keeps name order), so
one configuration's repeats are spread over time rather than run back to
back. It appends one line per submission (time, seed, run, nodes, Slurm job)
to `<results-dir>/submissions.tsv`.

`corpus_index.py` writes `<prefix>_repeats.csv` next to the index: per
configuration, the number of runs and, for the reader and writer step,
`Vis_Time`, `ADIOS_Wait` and io times, the median, minimum, maximum, spread
and the outlier runs (further from the median than 3 scaled median absolute
deviations, at least 10% of the median and at least 50 ms). With only two
usable runs (a repeat failed) a spread over 25% is flagged instead. It prints the configurations
with an outlier. Rerun an outlier as a fourth repeat rather than dropping
it, and keep it in the corpus with its flag.

Large runs (since 21 Nov 2026):
* `workq` caps a job at 2048 nodes; the generator adds `#SBATCH --qos=ex`
  to larger jobs and gives them at least an hour (start-up grows with the
  node count).
* James's standing OK covers jobs up to about 3500 nodes, and a few over
  (the 3536-node 3328 + 208 layout: its ADIOS2 transport run was clean on
  21 Nov 2026, job 16126972, 6 min 38 s; validate one Ascent and one Catalyst
  run at that size before queueing its repeats). `orchestrate.py` holds anything
  above 3500 nodes except the sizes in `APPROVED_SIZES` (3536) (the 4096-node strong, weak, hero and staging-sweep
  runs) unless `--allow-over-limit <name part>` names it, which needs his
  approval for those runs.
* The in transit ladders (`SCALE_CONFIGS`, `PIPE_CONFIGS`,
  `ADIOS_SWEEP_CONFIGS`) run to 2048 + 128, 3072 + 192 and 3328 + 208 nodes
  (13 dragonfly groups), 4096^3 inline strong scaling adds 2048, 3072 and 3328 nodes, and `hero3072` (3072 +
  192 at 8192^3) is the strong-scaling point below the 4096-node hero run.
  3072 is exactly 12 of Shaheen III's 256-node dragonfly groups. A node
  count that is not a power of two splits L unevenly by at most one cell
  per rank (at 3072 nodes, 85 or 86 cells in z at 4096^3).

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

**Tiled rendering is off** (Ascent 0.9.6, 20 Nov 2026). Ascent 0.9.6
renders in 1024 x 1024 tiles by default; 0.9.5 did not tile. At our
2048 x 2048 images tiling only costs time, so every Paper 2 Ascent render
(slices, volume, isosurface) sets `tiled_rendering: "false"`
(`ASCENT_TILED_RENDERING` in the generator; `--ascent-tiled-rendering`
turns tiling back on for A/B runs), and the run's settings record
it as `ascent_tiled_rendering` (`settings-stage.json` in transit,
`settings.json` inline, and so in the reader's and simulation's
`metadata.json`, and the corpus index's `ascent_tiled_rendering` column),
so tiled and untiled runs can be told apart. Paper 1's
templates stay as they ran (#71). The key needs Ascent 0.9.6; regenerating
into a results directory written before it stops with an error, so use a
new `--results-dir`. Reader `total_step` in seconds, two runs
per arm, shuffled; 64 + 4 nodes with slab, planes read and no SMT, the
larger runs with the current defaults (brick, plane exchange, SMT):

| Nodes | Pipeline | 0.9.5 | 0.9.6 tiled (default) | 0.9.6 untiled |
|---|---|---|---|---|
| 64 + 4 | Slices | 3.02 | 3.42 | 3.02 |
| 64 + 4 | Volume | 3.06 | 3.09 | 3.08 |
| 64 + 4 | Isosurface | 6.43 | 10.68 | 6.09 |
| 512 + 32 | Slices | | 3.11 | 2.89 |
| 512 + 32 | Volume | | 2.80 | 2.82 |
| 512 + 32 | Isosurface | | 10.08 | 5.59 |
| 1024 + 64 | Slices | | 1.73 | 1.60 |
| 1024 + 64 | Volume | | 1.58 | 1.58 |
| 1024 + 64 | Isosurface | | 5.14 | 2.90 |

The cost is all in rendering on each rank. The isosurface's
`exec_main_scene` (render plus composite, `--ascent-timings`), mean / max
over ranks, falls from 6.05 / 6.36 to 1.58 / 1.89 s at 512 + 32 nodes and
from 3.04 / 3.33 to 0.82 / 1.11 s at 1024 + 64; the contour is unchanged.
The gap between the slowest rank and the mean, where compositing and
waiting show up, is the same with and without tiles (0.31 s at 512 + 32,
0.29 s at 1024 + 64), so compositing is unchanged and tiling makes each
rank's local render 3.7 to 3.8 times slower. Images: tiled and untiled
frames differ in about 420 pixels per 2048^2 slice frame and 1,170 per
isosurface frame, all on silhouette edges (not tile seams), the same at
both scales; volume frames are unaffected. Each setting reproduces its own
frames run to run. Untiled 0.9.6 slices are bit-identical to 0.9.5; 0.9.6
volume frames differ from 0.9.5 in 50 to 125 pixels because 0.9.6 fixes
0.9.5's speckle bug (stray pixels with blue 0).

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
* every Paper 2 data run writes every output step, inline and in transit
  (only Paper 1's inline data runs keep `overwrite_last_step`, as that paper
  did). Overwriting replaces the previous step's files, which made the
  Catalyst write 63% slower per step in a 64+4 A/B (Ascent +2.4%, 24 Nov
  2026), so inline and in transit data runs must not differ in it;
* for runs whose output is one file per simulation rank (Catalyst and
  Ascent data runs, inline and in transit, and the baselines), the run's
  `data/` is deleted first, after its file count and bytes are written to
  `<results>/<id>_data_output.json`. A 3328-node Catalyst data run left
  213,025 files (one per rank), and the data runs of one sweep would fill
  the 2M-inode `/scratch` quota on their own (22 Nov 2026). The write cost
  is in the timers; the output itself is not read afterwards. ADIOS2 data
  runs get the same treatment: few files, but full fields (one 3072 + 192 in
  transit run wrote 12 TB, nearly filling the 31 TiB quota, 23 Nov 2026).
  Render images and the initialisations' checkpoints are kept. Ascent's data
  output is written in the run directory itself (`ascent_data.cycle_*` and
  its `.root`), outside `data/`, so until 24 Nov 2026 this cleanup missed it
  (about 5 TB of the sweep). It now records and deletes those as well; the
  record says `"scope": "data+ascent"`, and a record written before (without
  it) has Ascent's leftover output added to it before that is deleted. A
  run's `reduce.sbat` holds the cleanup it was generated with: regenerate
  the results directory before resubmitting the reduction of a run made
  earlier, or its Ascent output stays. Resubmit it with the run's own job
  ID (not a reduction's), `sbatch --export=ALL,RUN_JOB_ID=<run job>
  <run>/reduce.sbat`: without it, a run that already has a record keeps
  its output.

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

**Catalyst renders with OSPRay.** The Paper 2 Catalyst slice and isosurface
templates use OSPRay, the CPU ray tracer (the volume template does not: see
"Catalyst volume images"): it is faster than
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
volume frame changes in 674 pixels, all on those overlays (those volume
frames drew no volume; see "Catalyst volume images"). Each arm's frames
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

## Catalyst node-local staging

The first Catalyst step of an in transit reader costs far more than the
steps after it, and most of that is start-up: Python starts in the first
`catalyst_execute`, and importing `paraview.simple` and VTK's extension
modules pages hundreds of shared libraries in from Lustre. At 64 + 4 nodes
the slices' step 0 took 21.4 s, of which 11 s were imports (13.2k major page
faults on one reader rank); `strace` shows only 1.5 s in file system calls,
because the page-ins of `mmap`ed libraries are not system calls. Node page
cache left by an earlier job did not predict a fast or slow run.

`generate_experiments.py --catalyst-stage` copies ParaView's `lib/` to
`/tmp/gs-catalyst-<job ID>` (local disk on Shaheen compute nodes, not tmpfs)
on the reader nodes alone, before `PHASE run_start`, and removes it after
the run. The directory is created with mode 700 and must not exist yet;
each node checks its copy of the tarball against the recorded sha256 before
unpacking it, and checks that Catalyst's libraries are there after. The copy
is timed as `PHASE stage_start` / `stage_end` in the job output, apart from
the run, and `<results>/<id>_stage.txt` records the times, the tarball and
what the reader resolves from the copy (`ldd` on a reader node; the
telemetry's `ldd.txt` shows the job-wide environment). The reader then loads Catalyst from the copy:
`CATALYST_IMPLEMENTATION_PREFER_ENV=1` with `CATALYST_IMPLEMENTATION_PATHS`
(ahead of the `catalyst_lib_path` the reader passes to `catalyst_initialize`),
`CATALYST_LIB_DIR` for the plugins (#126) and the copy first on
`LD_LIBRARY_PATH`. `catalyst_lib_path` in the run's settings stays the
Lustre install, which names the build; `catalyst_stage` beside it records
the method, the directory, the tarball and its sha256, and the generator
refuses to mix staged and unstaged runs in one results directory. Only in
transit Catalyst readers launched as one MPMD `srun` are staged: the
two-step launch does not fix which nodes the reader gets.

A staged job names each program's nodes: the job's first nodes for the
simulation and its last for the readers, given as `--nodelist` to both parts
of the MPMD `srun` and to every staging step (`<id>_stage.txt` lists the
reader nodes). Without the names, Slurm does not put the second program on
the job's last nodes. In job 16139690 (64 + 4) the copy went to
nid02813-02816 and the readers ran on nid02811-02812 and nid02815-02816;
the 16 readers without a copy loaded ParaView from Lustre, and the
isosurface failed with `Plugin 'AcceleratedAlgorithms' not found`, since the
plugin path it takes from `CATALYST_LIB_DIR` did not exist on their nodes.
With the names, a 4 + 2 test ran the readers on the staged nodes and wrote
its images.

Three things are needed besides the option:

- **The tarball**, once per ParaView install:
  `sites/shaheen/build-catalyst-stage.sh <install>` writes
  `<build dir>-lib.tar` and `.sha256` beside the build directory (for the
  6.2.1 superbuild, `software/paraview-6.2.1-gcc13-build-lib.tar`, 0.9 GB:
  `lib/` without `.debug` and static archives). The superbuild's LLVM,
  OpenVKL, OSPRay modules, Embree, Mesa and `libcatalyst` name the install's
  `lib/` by its absolute path in their own `DT_RPATH`, which the loader
  searches before `LD_LIBRARY_PATH`, so the script rewrites those paths in
  the packed copy to `$ORIGIN`-relative ones (622 libraries). Without that,
  46 libraries of the staged reader still came from Lustre. The generator
  checks the tarball against its `.sha256` before recording it.
- **A reader linked with `DT_RUNPATH`:** add `-DGS_READER_RUNPATH=ON` to the
  build's CMake options (`config.bash` leaves it off). The reader is linked
  with `--disable-new-dtags` by default, and its `DT_RPATH`, which names the
  Lustre install, beats `LD_LIBRARY_PATH`. With `RUNPATH` the job-wide
  `LD_LIBRARY_PATH` (ParaView's `lib/` first) also decides between libraries
  that ParaView and Ascent both ship: in practice `libz.so.1`, which then
  comes from ParaView's zlib 1.3.1 instead of Ascent's (also 1.3.1). Ascent's
  own libraries carry their own `RPATH`. Ascent slices from the two builds
  differed by at most one pixel in one frame (channel difference 1 or 2),
  as much as two runs of one build differ.
- **#126** for the isosurface: its script loads the AcceleratedAlgorithms
  plugin by path from `CATALYST_LIB_DIR`. By name, ParaView finds the plugin
  only from the install it was built in, and a staged isosurface fails in
  its first step; without #126 the generator refuses to stage it.
- The generator refuses `--catalyst-stage` for a reader without
  `DT_RUNPATH` (`readelf -d` on `--bin-path`'s `analysis-reader`).

The methods: `tar` has each reader node read the tarball from Lustre,
`sbcast` copies it to a placeholder step on the reader nodes (so the other
nodes get nothing) and each node unpacks it, `auto` picks `sbcast` from
`CATALYST_STAGE_SBCAST_MIN_NODES` (128) reader nodes. That threshold is an
estimate: at 32 reader nodes `tar` took 1.2 to 3.9 s and `sbcast` 8.3 to
8.8 s, and neither has been timed above 32. Those times are from before each
node checked the tarball's sha256 and the job recorded `ldd`; with both, at
4 reader nodes, `tar` took 4.5 s and `sbcast` 10.1 s, and the frames stayed
identical.

Results at 512 + 32 nodes (22 Nov 2026, the RUNPATH build with #126, two
runs per arm, interleaved; first update is the range over reader ranks of
the time from `catalyst_initialize` to the first pipeline update):

| Pipeline | Arm | Copy (s) | Step 0 (s) | First update (s) | Steps 1+ (s) |
| :--- | :--- | ---: | ---: | ---: | ---: |
| slices | Lustre | | 26.4, 23.4 | 26.8 to 30.4 | 0.88, 0.89 |
| slices | staged | 3.9 (tar), 8.8 (sbcast) | 2.8, 2.9 | 5.0 to 5.4 | 0.89, 0.88 |
| isosurface | Lustre | | 44.7, 51.7 | 29.8 to 39.2 | 16.22, 16.78 |
| isosurface | staged | 1.2 (tar), 8.3 (sbcast) | 22.1, 23.7 | 5.0 to 6.4 | 16.38, 16.44 |

Every frame of every run was byte-identical within each pipeline, staged or
not. A probe of one reader's `/proc/<pid>/maps` found 362 or 363 files of the
6.2.1 install mapped from Lustre in each Lustre run and none in each staged run
(all from `/tmp`). Staging takes 20 to 30 s off the first step, the steady
state is unchanged, and the isosurface's first step still costs 6 to 7 s
more than its later ones. At 64 + 4 nodes the slices' step 0 went from 21.4 s
to 6.5 to 7.8 s with an earlier, partial stage (46 libraries still from
Lustre); the fully staged isosurface's step 0 was 20.3 to 20.5 s.

## Inline Catalyst hang

In the first Paper 2 sweep (22 to 23 Nov 2026), 20 of 21 inline Catalyst
render, volume and isosurface runs stopped in their first render and slept
until the 2 h limit, from 8 to 3072 nodes. The one that ended (64 nodes)
wrote 0-byte images. Inline `catalyst_io` runs, with no rendering, were
fine. Node telemetry showed every rank go idle about a minute into the run,
and a probe of the stuck ranks found their main threads waiting on Lustre
locks (`ldlm_completion_ast`, in a page fault, not a system call) next to
Mesa's shader cache thread (`disk$0`).

llvmpipe, which the Paper 2 jobs use (Paper 1 keeps softpipe), caches its
compiled shaders in `~/.cache/mesa_shader_cache`. In a Shaheen job `~` is
`/scratch/$USER`, so the cache is on Lustre, and every rank on every node
maps its index file to write it. The jobs that hung all wrote to it (its
directories and index carry the sweep's times). At 8 nodes (512 ranks), the
same job:

| Mesa shader cache | Runs | Result |
|---|---|---|
| Default, already holding the job's shaders | 2 | ended in 104 s |
| New, empty directory (`MESA_SHADER_CACHE_DIR`) | 3 | all hung |
| Off (`MESA_SHADER_CACHE_DISABLE=true`) | 5 | ended in 33 to 80 s |

The cache-off runs covered the render, volume and isosurface scripts,
once with ParaView's libraries staged to node-local `/tmp`. The cache only
spares a later process the compile; each rank keeps its shaders in memory
for the run either way. `generate_experiments.py` therefore exports
`MESA_SHADER_CACHE_DISABLE=true` in every Paper 2 job, inline and in
transit. Paper 1 jobs are unchanged: softpipe compiles nothing.

## Catalyst volume images

Every Catalyst volume frame from the Paper 2 template, inline and in
transit, showed only the background, the orientation axes and the scalar
bar: the same 40374-byte PNG at every step of every run. ParaView 6.2 does
not volume-render, with OSPRay, the partitioned image data Catalyst hands the
script (one image block per rank), and its volume representation has no
OSPRay mode (`VolumeRenderingMode` offers Smart, Ray Cast Only and GPU
Based). The same script with ray tracing off draws the volume. Merging the
blocks into one dataset ran out of memory at 1024^3 on one node, and
resampling to one image would break the template's like-for-like match with
Ascent (same data, no resampling).

The volume template therefore renders with VTK's volume ray caster
(`EnableRayTracing=0`), on the CPU through Mesa's llvmpipe; the slice and
isosurface templates keep OSPRay. At 1024^3 (the 8-node checkpoint, step
65000), against a serial `pvbatch` reference that resamples the same data to
one image and renders it with OSPRay:

| Image | Mean difference | Pixels > 32 levels apart (of 4.2 M) |
|---|---|---|
| Inline, 8 nodes, against in transit, 8 + 2 | 0.65 | 0 |
| Inline, 8 nodes, against inline, 1 node | 0.37 | 0 (none > 8) |
| Inline, 8 nodes, against the OSPRay reference | 5.3 | 133,213 |
| In transit, 8 + 2, against the OSPRay reference | 5.5 | 137,992 |

The Catalyst frames agree with each other at any rank count. The reference
differs evenly, by about 5 levels inside the cube, and more at its silhouette,
where VTK's ray caster accumulates less opacity over the short paths near
the edges. A serial `pvbatch` render of the 64 blocks with VTK's mapper is
not a reference: it ran out of texture units and dropped blocks.

**Timings of the earlier volume runs measure no volume.** The old template,
rerun at 8 + 2, wrote the same blank frame at all 6 steps, with 0.030 s of
IceT render time and 0.21 s of Catalyst execute time per step. The fixed
template took 1.02 s and 1.65 s. Catalyst volume times from runs made before
this change are the cost of drawing an empty frame, the axes and the scalar
bar, and writing the PNG, not of volume rendering, and need rerunning.

## Reader overwrite (`--transit-data-overwrite`)

The 8192^3 in transit hero data runs write 25 TB or more each, more than
`/scratch` holds. `generate_experiments.py --transit-data-overwrite` (off by
default) sets `overwrite_last_step` in the reader's settings for in transit
Catalyst (`catalyst_io`) and Ascent data runs, so the reader replaces its
last output instead of writing one per step (analysis/README.md). The
simulation's SST output and ADIOS2 data runs are unchanged.

A/B at 64 + 4 nodes (2048^3 checkpoint, 3 output steps, 24 Nov 2026), 3 runs
per mode, interleaved. Each cell is the median of the runs, with the
smallest and largest run in brackets; each run's value is its median over
output steps 1 and 2 (step 0 writes no existing file in either mode).

| Catalyst data | No overwrite | Overwrite | Change |
|---|---|---|---|
| Reader write (`Vis_Time`), steps 1+ | 6.15 s [6.01, 6.29] | 10.04 s [9.77, 10.06] | +63% |
| Reader write, step 0 | 5.82 s [5.71, 5.98] | 5.81 s [5.77, 5.86] | 0% |
| Reader `ADIOS_Wait`, steps 1+ | 0.19 s [0.17, 0.25] | 0.005 s [0.005, 0.006] | -97% |
| Reader step (`total_step`), steps 1+ | 8.31 s [8.17, 8.49] | 12.07 s [11.78, 12.22] | +45% |
| Reader `Step_Latency`, steps 1+ | 11.06 s [11.00, 11.31] | 12.76 s [12.47, 12.79] | +15% |
| Simulation SST write, outputs 2+ | 4.69 s [4.69, 4.84] | 4.63 s [4.59, 4.73] | -1% |
| Simulation loop | 11.9 s [11.9, 12.3] | 11.8 s [11.8, 12.1] | -1% |
| Output written | 440 GB, 99 files | 147 GB, 33 files | |

| Ascent data | No overwrite | Overwrite | Change |
|---|---|---|---|
| Reader write (`Vis_Time`), steps 1+ | 97.2 s [96.7, 97.6] | 99.5 s [99.3, 100.4] | +2.4% |
| Reader write, step 0 | 98.1 s [97.8, 99.2] | 97.8 s [97.6, 99.5] | 0% |
| Reader `ADIOS_Wait`, steps 1+ | 0.006 s | 0.006 s | 0% |
| Reader step (`total_step`), steps 1+ | 99.4 s [98.7, 99.8] | 101.8 s [101.6, 102.7] | +2.4% |
| Reader `Step_Latency`, steps 1+ | 148.3 s [147.6, 149.4] | 149.6 s [149.4, 151.1] | +1% |
| Simulation SST write, outputs 2+ | 51.0 s [50.6, 51.5] | 50.8 s [50.6, 51.6] | 0% |
| Simulation loop | 104.6 s [103.9, 105.6] | 104.3 s [103.7, 105.7] | 0% |
| Output written | 337 GB, 99 files | 112 GB, 33 files | |

**Overwrite changes the reader's write.** Writing over the files of the
previous step costs Catalyst 3.9 s more per step (+63%) and Ascent 2.3 s
(+2.4%); the first write, with no file to replace, costs the same in both
modes, so the extra time is the replacement of existing Lustre files. The
Catalyst reader, now slower than the simulation, no longer waits for data
(`ADIOS_Wait` near zero). The simulation was unaffected here: with 3
outputs, SST's queue absorbed the slower reader. With more outputs, a
reader that falls behind would hold the simulation once the queue fills.

**The last step's data is the same in both modes.** Catalyst: the piece
files are the same size and differ in 3 bytes (the time value, 2 against
0); `u`, `v` and `vtkGhostType` are byte-identical. Ascent: all 23 datasets
of the sampled domains match except `state/cycle` (2 against 0); runs of
one mode differ only in HDF5 file metadata. Runs of one mode wrote
identical Catalyst files.

## Flash storage (the `bandwidth` pool)

Shaheen III's `/scratch` has a flash pool (`bandwidth`) beside the default
disk pool (`capacity`); a directory is put on it with `lfs setstripe --pool
bandwidth`. Each user may keep 1 TiB there. We tested whether it speeds up
the data runs' writes (24 Nov 2026): inline ADIOS2 data, weak scaling,
write time per output step (the median of each run's 3 output steps), 3
runs per pool, made one at a time.

| Simulation | Data per step | `capacity` (default) | `bandwidth` (flash) |
|---|---|---|---|
| 8 nodes, 1024^3 | 17 GB | 1.34, 1.44, 1.45 s | 1.74, 1.75, 1.76 s |
| 64 nodes, 2048^3 | 137 GB | 1.36, 1.38, 1.41 s | 1.77, 1.77, 1.83 s |

**Flash was about 25% slower** (0.35 s more per step), at both sizes, and
the groups do not overlap. The write time stays flat from 8 to 64 nodes on
both pools while the data per step grows 8 times, so neither pool's
bandwidth is the limit at these sizes: the time is per-node work in ADIOS2
and the Lustre client, and flash adds a fixed cost there. Larger runs could
not be tested: one 4096^3 step (1.1 TB) is more than the flash quota.

Reading the restart checkpoint from flash was not tested. That read is not
in the timed loop (2048^3 about 3 s, 4096^3 11 to 48 s, 8192^3 127 to 151 s
from the default pool), and only the 2048^3 checkpoint fits the quota.

So the sweep writes to the default pool only, and we did not ask KSL for
flash space.
