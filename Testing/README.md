# Regression and Performance Testing

This `test_suite.py` script runs performance and regression tests for **VisIt** and **ParaView** on **Ibex** and **Shaheen**. It also provides a convenient method to run all examples in the **ParaView** or **VisIt** directories without running each one manually.

> ⚠️ **Important:** In all examples below, replace paths like `~/Visualization_Vignettes/` with the actual path to your cloned repository. HPC paths are written using variables like `$SCRATCH` to be easily copy-pasted.
> ⚠️ **Important:** You must use the `fetchData.sh` script before running these tests for them all to work.

Two companion documents:

* [`LOCAL_VALIDATION.md`](LOCAL_VALIDATION.md), the current status of every
  vignette under each tool version, the defect log behind the fixes, and the
  measurements behind the baseline and tolerance decisions.
* [`OFFLINE_SETUP.md`](OFFLINE_SETUP.md), preparing the environment and the
  data for a machine with no network, and the Shaheen and Ibex runbooks.

---

## What This Suite Does

When you run `test_suite.py`, it performs several actions for each test vignette:

1. **Regression Test:** Runs the vignette and compares its outputs against the baselines stored in that test's `Testing/Baseline/` directory.
2. **Performance Test:** Records execution time, memory usage, and CPU usage for the run. Peak memory is sampled from the vignette's own process tree while it runs, `resource.getrusage(RUSAGE_CHILDREN)` reports a high-water mark over every child the harness has ever reaped and never decreases, so after one large vignette every later one in the same invocation reported *its* peak instead of their own.
3. **Data Logging:** Saves the new performance metrics into a `performance_metrics_*.json` file in the test's `Testing/` directory.
4. **Plot Generation:** Updates the performance graphs (`.png` files) inside that same `Testing/` directory, showing the new run alongside all previous ones.

### Five independent failure gates

A vignette fails if **any** of these fails. All five feed the suite's exit
code; previously only the last one did, which is why a vignette could render
a black frame, or crash outright, and still leave CI green.

| Gate | Artifact | What it catches |
| :--- | :--- | :--- |
| **Process exit code** | `Testing/run_result.json` | A vignette that crashed, aborted, or hit its timeout. |
| **Image comparison** | `Testing/image_comparison_results.json` | A rendering change, a missing frame, or a resolution change. |
| **Numeric comparison** | `Testing/results_comparison.json` | A metric that drifted beyond tolerance, an assertion the vignette itself failed, or a metric it stopped reporting. |
| **CSV extracts** | `Testing/csv_comparison_results.json` | A declared numerical extract whose values moved beyond tolerance, or whose row count changed. |
| **Text comparison** | `Testing/text_comparison_results.json` | A change against the legacy `known_good_value.txt`. Unchanged in behaviour. |

### How image comparison works now

* **Resolution mismatches fail.** Output is no longer rescaled to the
  baseline's dimensions before diffing. A job that requested EGL, silently
  fell back to software, and rendered at a different size used to compare
  clean; it now reports `SIZE MISMATCH`.
* **Diffs run at native resolution**, and the threshold is a **fraction of
  total pixels** (`--image-tolerance`, default `0.001`) rather than a flat
  count. A flat 1000-pixel budget meant 24% of a thumbnail and 0.012% of a 4K
  frame.
* **Comparison is driven from the baseline list**, not from whatever the run
  emitted, so a vignette that stops producing one of its frames reports
  `MISSING OUTPUT` instead of passing with fewer images.
* **An image the run produced that no baseline covers is reported, not failed.**
  Blessing records at most `--max-baseline-images` (default 5), so a ten-frame
  animation has five uncovered frames by design; those are listed as
  `NOT BASELINED`, which does not fail. `NO BASELINE`, a missing baseline for an
  image the comparison set does cover, still fails. Raise
  `--max-baseline-images` to cover more frames.

### Numeric comparison

Vignettes from `ex07` onward write `Testing/<vignette>_results.json` holding
deterministic `metrics`, wall-clock `timings`, and named `assertions`. Only
`metrics` is regression-compared, with `--rtol`/`--atol`; timings never are,
because a wall-clock baseline fails whenever the node is busy and teaches
people to ignore red tests.

Adding a **new** metric never breaks an existing baseline. Dropping one does.
Per-metric tolerances can be set in the baseline JSON under `_tolerances`.

### Numeric CSV extracts

`ex12` in both suites regression-tests **numbers rather than pixels**. It
writes a CSV of per-timestep query results and declares it:

```python
ctx.add_numeric_extract(
    "ex12_pvExtractRegression_measurements.csv",
    key_columns=("timestep",),
    rtol=1e-6,
    atol=1e-9,
)
```

The declaration is what routes the file into `verify.compare_csv`. The
harness reads the list back out of the vignette's results JSON, compares each
declared file in `output/` against the copy in `Testing/Baseline/` cell by
cell, and `--bless` copies them into the baseline directory alongside the
images.

Three details are deliberate:

* **Only declared files are compared.** `ctx.write_timing_csv()` also writes
  a CSV into `output/`, and a wall-clock file compared against a baseline is
  a test that fails whenever the node is busy. Nothing is inferred from the
  directory listing.
* **`key_columns` matches rows by identity, not position**, so a vignette
  that emits its rows in a different order still passes, while a row that
  genuinely vanished still fails.
* **A changed row count is a failure**, even when every surviving row
  matches. Extracting a different number of timesteps is a deliberate
  change, and a deliberate change wants a re-bless rather than a silent pass.

`ignore_columns` skips values that legitimately move between runs -- a
hostname, a wall time -- which is what makes it safe to keep timings in the
same file as the measurements.

---

## Initial Setup: Python Environments

> **No network on the target machine?** See
> [`OFFLINE_SETUP.md`](OFFLINE_SETUP.md). Do not copy a virtual environment:
> a venv records absolute paths in `bin/activate` and in every console
> script's shebang, so it half-works when moved, which is worse than failing.
> `./make_offline_bundle.sh` collects the five packages as wheels (52 MB) to
> install with `pip --no-index` on the other side. That document also carries
> the full Shaheen and Ibex runbooks.



Before running tests, you must create Python environments to install necessary packages.

> 💡 **Note:** On systems like Shaheen, compute nodes do not have internet access. You **must run the `pip install` commands on a login node** *after* creating the environment.

We will create three environments in your `$SCRATCH` directory:

```bash
# Set your scratch path (if not already set)
export SCRATCH="/ibex/scratch/${USER}" # or /scratch/${USER} on Shaheen

# 1. ParaView CPU Environment
python3 -m venv $SCRATCH/testing_paraview_env
source $SCRATCH/testing_paraview_env/bin/activate
pip3 install pandas numpy pillow matplotlib psutil scipy
deactivate

# 2. ParaView GPU Environment (for Shaheen GPU)
python3 -m venv $SCRATCH/testing_paraview_gpu_env
source $SCRATCH/testing_paraview_gpu_env/bin/activate
pip3 install pandas numpy pillow matplotlib psutil scipy
deactivate

# 3. VisIt Environment (CPU & GPU)
python3 -m venv $SCRATCH/testing_visit_env
source $SCRATCH/testing_visit_env/bin/activate
pip3 install pytz six pyparsing psutil pandas numpy pillow matplotlib scipy
deactivate
```

---

## Understanding the Script Arguments

All commands use the same basic structure:

```bash
python test_suite.py <base_directory> --test_type <type> --machine_name <name> ...
```

* **`<base_directory>`** (Positional): The path to the root `Visualization_Vignettes` directory. The script uses this to find all the sub-folders (e.g., `ParaView_Vignettes`, `VisIt_Vignettes`).
* **`--test_type`** (Required): `ParaView` or `VisIt`. Tells the script which set of tests to run.
* **`--machine_name`** (Required): A **critical** string used to:
    1. Name the output JSON and plot files (e.g., `performance_metrics_ibex-cpu.json`).
    2. Allow the plotting script to correctly group runs from the same machine.
* **`--paraview_version` / `--visit_version`**: The version number of the software being tested. This is saved as metadata in the JSON logs.
* **`--non_gpu_machine`**: A flag that tells the test script to enforce a CPU-only execution path. This is required for CPU-only ParaView modules (`-mesa`) to prevent them from trying to find a GPU.
* **`--no-metrics`** (alias `--ephemeral`): Run and compare exactly as usual, but append nothing to the committed performance history. See [The performance history](#the-performance-history).
* **`--run-id ID`**: Tag every record this invocation writes. Defaults to a generated id; pass one explicitly to group a ParaView run and a VisIt run into a single logical run.

---

## 🧪 Running the Tests

### Local Machine

This assumes you have a local `venv` (e.g., `~/testing_paraview_env`) and the repo is in your home directory.

#### ParaView

```bash
export PARAVIEW_PATH="<path-to-your-paraview-install>/bin"
source ~/testing_paraview_env/bin/activate
cd ~/Visualization_Vignettes/Testing
python test_suite.py ~/Visualization_Vignettes/ \
  --test_type ParaView \
  --paraview_version 5.13.1 \
  --machine_name local-machine
```

#### VisIt

```bash
export VISIT_PATH="<path-to-your-visit-install>/bin/"
source ~/testing_visit_env/bin/activate
cd ~/Visualization_Vignettes/Testing
python test_suite.py ~/Visualization_Vignettes/ \
  --test_type VisIt \
  --visit_version 3.4.1 \
  --machine_name local-machine
```

---

### Ibex

#### Ibex CPU (ParaView)

```bash
# 1. Load module
module load paraview/5.13.1-gnu-mesa

# 2. Request an interactive job
srun --cpus-per-task=12 --ntasks=1 --time=00:40:00 --mem=100G --pty /bin/bash

# 3. Once in the job, run the tests
source $SCRATCH/testing_paraview_env/bin/activate
cd $SCRATCH/Visualization_Vignettes/Testing
python test_suite.py $SCRATCH/Visualization_Vignettes/ \
  --test_type ParaView \
  --paraview_version 5.13.1 \
  --machine_name ibex-cpu \
  --non_gpu_machine
```

#### Ibex CPU (VisIt)

```bash
# 1. Load modules
module load visit/3.4.1
module load ffmpeg

# 2. Request an interactive job
srun --cpus-per-task=12 --ntasks=1 --time=00:40:00 --mem=100G --pty /bin/bash

# 3. Once in the job, run the tests
source $SCRATCH/testing_visit_env/bin/activate
cd $SCRATCH/Visualization_Vignettes/Testing
python test_suite.py $SCRATCH/Visualization_Vignettes/ \
  --test_type VisIt \
  --visit_version 3.4.1 \
  --machine_name ibex-cpu
```

#### Ibex GPU (ParaView)

```bash
# 1. Load module
module load paraview/5.13.1-gnu-egl

# 2. Request an interactive GPU job (use table below)
srun <gpu-flag> --cpus-per-task=12 --ntasks=1 --time=00:40:00 --mem=100G --pty /bin/bash

# 3. Once in the job, run the tests (use table below)
source $SCRATCH/testing_paraview_env/bin/activate
cd $SCRATCH/Visualization_Vignettes/Testing
python test_suite.py $SCRATCH/Visualization_Vignettes/ \
  --test_type ParaView \
  --paraview_version 5.13.1 \
  --machine_name <machine-name>
```

**GPU Options:**

| GPU Type | `srun` Flag (`<gpu-flag>`) | Python Flag (`<machine-name>`) |
| :--- | :--- | :--- |
| v100 | `--gres=gpu:v100:1` | `ibex-egl-v100` |
| a100 | `--gres=gpu:a100:1` | `ibex-egl-a100` |
| rtx2080ti | `--gres=gpu:rtx2080ti:1` | `ibex-egl-rtx2080ti` |
| p6000 | `--gres=gpu:p6000:1` | `ibex-egl-p6000` |
| p100 | `--gres=gpu:p100:1` | `ibex-egl-p100` |
| gtx1080ti | `--gres=gpu:gtx1080ti:1` | `ibex-egl-gtx1080ti` |

#### Ibex GPU (VisIt)

```bash
# 1. Load modules
module load visit/3.4.1
module load ffmpeg

# 2. Request an interactive job (any GPU)
srun --gres=gpu:1 --cpus-per-task=12 --ntasks=1 --time=00:40:00 --mem=100G --pty /bin/bash

# 3. Once in the job, run the tests
source $SCRATCH/testing_visit_env/bin/activate
cd $SCRATCH/Visualization_Vignettes/Testing
python test_suite.py $SCRATCH/Visualization_Vignettes/ \
  --test_type VisIt \
  --visit_version 3.4.1 \
  --machine_name ibex-gpu
```

---

### Shaheen3

#### Shaheen3 CPU (ParaView)

```bash
# 1. Load module
module load paraview/5.13.1-mesa

# 2. Request an interactive job (use table below)
srun <srun-flags> --pty /bin/bash

# 3. Once in the job, run the tests
source $SCRATCH/testing_paraview_env/bin/activate
cd $SCRATCH/Visualization_Vignettes/Testing
python test_suite.py $SCRATCH/Visualization_Vignettes/ \
  --test_type ParaView \
  --paraview_version 5.13.1 \
  --machine_name <machine-name> \
  --non_gpu_machine
```

**CPU Options:**

| Node Type | `srun` Flags (`<srun-flags>`) | Python Flag (`<machine-name>`) |
| :--- | :--- | :--- |
| workq | `--cpus-per-task=32 --ntasks=2 -p workq --time=00:40:00 --mem=200G -A k01` | `shaheen3-cpu` |
| ppn | `--cpus-per-task=32 --ntasks=2 -p ppn --time=00:40:00 --mem=200G -A k01` | `shaheen3-mesa-ppn` |

#### Shaheen3 CPU (VisIt)

```bash
# 1. Load module
module load visit/3.4.1

# 2. Request an interactive job (use table below)
srun <srun-flags> --pty /bin/bash

# 3. Once in the job, run the tests
source $SCRATCH/testing_visit_env/bin/activate
cd $SCRATCH/Visualization_Vignettes/Testing
python3 test_suite.py $SCRATCH/Visualization_Vignettes/ \
  --test_type VisIt \
  --visit_version 3.4.1 \
  --machine_name <machine-name>
```

**CPU Options:**

| Node Type | `srun` Flags (`<srun-flags>`) | Python Flag (`<machine-name>`) |
| :--- | :--- | :--- |
| workq | `--cpus-per-task=32 --ntasks=2 -p workq --time=00:40:00 --mem=300G -A k01` | `shaheen3-cpu` |
| ppn | `--cpus-per-task=32 --ntasks=2 -p ppn --time=00:40:00 --mem=300G -A k01` | `shaheen3-ppn` |

#### Shaheen3 GPU (ParaView)

```bash
# 1. Load module
module load paraview/5.13.1-egl

# 2. Request an interactive GPU job
srun --cpus-per-task=32 --ntasks=1 -p ppn -G 1 --time=00:40:00 --mem=200G -A k01 --pty /bin/bash

# 3. Once in the job, run the tests
source $SCRATCH/testing_paraview_gpu_env/bin/activate
cd $SCRATCH/Visualization_Vignettes/Testing
python test_suite.py $SCRATCH/Visualization_Vignettes/ \
  --test_type ParaView \
  --paraview_version 5.13.1 \
  --machine_name shaheen3-ppn-gpu-L40
```

---

## Reading the plots

Every vignette writes six PNGs into its `Testing/` directory on each run, two
per metric (execution time, peak memory, CPU). They are generated, not
committed.

* **`<metric>_comparison.png` -- trend.** One small panel per configuration.
  A configuration's runs are plotted against **its own run number**, 1..N, so
  they are evenly spaced and no line is ever drawn across a gap belonging to
  another machine. y is autoscaled per panel, because the question a trend
  panel answers is "did THIS configuration move". Marker shape is the tool
  version. Runs recorded before the current `metrics_schema` sit behind a
  grey band with a dashed divider, for the metrics whose definition changed
  there.
* **`<metric>_latest.png` -- comparison.** One bar per configuration, most
  recent run, labelled with the version and the date. "Is Shaheen slower than
  the workstation" is not a question about time, and answering it with a time
  series is what made the old plot unreadable. Configurations whose newest run
  predates the current schema are left out rather than drawn as a bar nobody
  can trust.

`<suite>/combined_execution_time_plot.png` shows the most recent execution
time for every vignette on every configuration as grouped bars, log scale
because ex06 is fifty times the next vignette.

**Why the x axis is a run number and not a date.** It used to be a date, then
an index into the union of every configuration's timestamps, and both had the
same problem: with eleven configurations and sixty-seven runs between them,
each configuration occupied a narrow band and then drew a straight line across
the whole figure through sixty positions where it had no data. The axis
carried sixty-seven rotated timestamps, most belonging to somebody else.
Per-configuration run numbers remove the problem rather than moving it; the
dates are still on the ticks, thinned to five per panel.

## How Baselines Work

Regression testing compares output files against a baseline stored in each
test's `Testing/Baseline/` directory.

**Baselines are never created automatically.** A missing baseline is a
FAILURE, reported as `NO BASELINE`. The suite used to create one from the
current output immediately *before* comparing against it, which meant a first
run always passed and a deleted baseline silently re-blessed itself -- so a
brand new vignette could never fail, and neither could one whose baseline
someone had removed.

### Recording a baseline

```bash
# 1. Run the test and LOOK at what it produced in output/.
python test_suite.py ../ --test_type ParaView --test_number 7 --machine_name my-machine

# 2. Only once you are satisfied, record it.
python test_suite.py ../ --test_type ParaView --test_number 7 --machine_name my-machine --bless

# 3. Re-run without --bless to confirm it now passes.
python test_suite.py ../ --test_type ParaView --test_number 7 --machine_name my-machine
```

`--bless` records the images (up to `--max-baseline-images`, default 5), the
structured results JSON, and any declared numeric CSV extracts. Review the diff
before committing: a blessed baseline is an assertion about what correct looks
like.

**Clear `output/` first.** Nothing in the harness does, `--clean` only touches
`Testing/`, and `ex12` counts the files it produced, so a stale `.vtp` or `.png`
from an earlier run with a different `--steps` ends up in the baseline.

### Updating a baseline

When a test fails because of a change you *expected*, re-run with `--bless`.
There is no need to delete anything first -- blessing overwrites.

---

## Running in Parallel

`--ranks` and `--nodes` flow all the way through: to `mpirun`/`srun` for
ParaView, and to `OpenComputeEngine` for VisIt. ParaView vignettes previously
ran only at `-np 1`, so the parallel path had no coverage at all.

```bash
# ParaView on 8 ranks via mpirun
python test_suite.py ../ --test_type ParaView --ranks 8 --launcher mpirun \
    --machine_name my-machine

# ParaView on 16 ranks across 2 nodes via srun
python test_suite.py ../ --test_type ParaView --ranks 16 --nodes 2 \
    --launcher srun --machine shaheen --machine_name shaheen3-cpu

# VisIt: the engine gets the ranks, the client is never wrapped in a launcher
python test_suite.py ../ --test_type VisIt --ranks 8 --nodes 2 \
    --machine ibex --machine_name ibex-cpu
```

Useful related flags:

| Flag | Purpose |
| :--- | :--- |
| `--launcher {auto,mpirun,srun,none}` | How to launch `pvbatch`. `auto` probes the node. |
| `--threads N` | Threads per rank. Defaults to `$SLURM_CPUS_PER_TASK`. |
| `--timeout N` | Seconds before a vignette is killed and marked failed. Default 3600. |
| `--no-offscreen` | Do not force offscreen rendering. Required by `ex11`, which runs under `xvfb-run`. |
| `--image-tolerance F` | Fraction of pixels allowed to be different. Default `0.001`. |
| `--vignette-arg ARG` | Forward an extra flag verbatim to every vignette. Repeatable. |

### Rendering determinism

Two things are pinned so that an image baseline means something.

**GPU selection.** On a node with more than one GPU the driver does not place
work consistently, and a single-rank render job was only ever going to use one
device anyway, so for `--ranks 1` the harness sets `CUDA_VISIBLE_DEVICES=0` and
says so in the log. An explicit `CUDA_VISIBLE_DEVICES` in the environment always
wins, which is what Slurm `--gres=gpu` provides, and nothing is pinned for a
multi-rank run.

**VisIt configuration.** The VisIt CLI is launched with `-noconfig`. Without it
VisIt reads `~/.visit/config` at startup, saved annotation, save-window,
window-size and colour-table state, and a blessed baseline becomes partly a
function of whose home directory ran the suite.

Two consequences of that are worth knowing before you read a VisIt log:

* **`-noconfig` also hides VisIt's own colour tables.** VisIt starts with 157
  colour tables normally and **18** with `-noconfig`, because 129 of the missing
  ones ship as `.ct` files under `$VISITARCHHOME/resources/colortables/` and are
  loaded by the same code path. `viridis`, `plasma`, `magma` and `Blues` are all
  in that group. VisIt does not refuse an unknown table name at the point of
  use: it accepts it, fails the plot asynchronously, and every later query on
  that plot returns `None`. Vignettes therefore load what they need explicitly
  through `vc.ensure_color_table()`, which reads the `.ct` out of the install.
  Because those files ship with VisIt, this is identical on Shaheen and Ibex.
* **`~/.visit` can silently substitute a different VisIt.** A host profile that
  names an install path makes the client start an engine from *that* build, not
  from the one you invoked, and makes it parallel and scalable-rendering when
  you asked for neither. `-noconfig` is what stops that.

### VisIt's exit code is not the verdict

`visit -cli` returns **250 whether the script succeeded or not**, on a clean
run, on a Python traceback, and on a crashed compute engine alike. Gating on it
would mark every VisIt run as failed.

So for VisIt the harness records the exit code but does not use it. The verdict
comes from the vignette's own results JSON, and that file must have been written
**after this run started**, otherwise a vignette that dies before writing
anything would inherit the previous run's verdict. A timeout fails regardless.

`run_result.json` says which rule was applied:

```json
{
  "returncode": 250,
  "exit_code_is_authoritative": false,
  "visit_launcher_exit_code": 250,
  "verdict_source": "results JSON status=ok",
  "succeeded": true
}
```

In the console the line to read is `Vignette passed (results JSON status=ok)`.

### Rehearsing a parallel VisIt run on a workstation

`--machine local` never contacts a scheduler, but above one rank it now starts a
real parallel engine through VisIt's own bundled `mpirun`:

```bash
python test_suite.py ../ --test_type VisIt --visit_version 3.4.2 \
  --machine_name <name>-np8 --ranks 8 --no-metrics
```

Use it to find a parallel problem before spending queue time on one.

Bless from it only where the baseline is meant to be parallel.
`ex06_visitLargeData` is the one such case: its scene is built from overlapping
translucent plots, which are composited in a partition-dependent order, so it is
blessed at the eight ranks its `.sbat` scripts request and turns its own image
gate off (with a warning) at any other rank count. Opaque vignettes are
bit-identical at one rank and at eight, measured.

### How VisIt's compute engine is launched

The VisIt client is never wrapped in `mpirun` or `srun`. Parallelism belongs
to the compute engine, which the vignette starts through
`OpenComputeEngine`. Which arguments that gets depends on where the client is
running, and the two cases need genuinely different ones:

| Where the client runs | Launcher passed | Partition / account / walltime |
| :--- | :--- | :--- |
| Inside a Slurm allocation (`$SLURM_JOB_ID` set) -- a `.sbat` job, or an `salloc` shell | `-l srun` | **Omitted.** A job step inherits them. |
| On a login node | `-l sbatch/srun` | Passed as `-p`, `-b`, `-t`. |

This follows the site's `~/.visit/customlauncher`, whose KAUST job submitters
engage only when all three of these hold:

```python
if self.parallelArgs.parallel and \
   self.sectorname().startswith("login") and \
   self.domainname() == "ibex.kaust.edu.sa":
```

The middle condition is the decisive one. From a login node the custom
submitter takes over, and it is an **sbatch** submitter with an **srun**
sublauncher -- `LauncherAndSubLauncher()` splits the launcher name on `/`, so
the string has to be `sbatch/srun` for that branch to be taken. A bare
`-l srun` would run the engine on the login node itself.

From inside an allocation the custom submitter does not engage at all, and
asking for an sbatch launcher there would submit a second job from inside the
first and then wait for it to schedule. `-l srun` starts the engine as a job
step of the allocation already held. Partition, account and walltime are
deliberately dropped in that case: they become `srun --partition=...
--time=...`, which is redundant at best and rejected outright when it
disagrees with the allocation.

`Testing/vignette_common.py` decides this from `$SLURM_JOB_ID` and logs which
profile it chose, because both failure modes look identical from the outside
-- a hung `OpenComputeEngine` -- and knowing which was attempted is most of
the diagnosis. It also warns when `--ranks`/`--nodes` exceed the allocation,
since `srun` rejects that with a message about resources that reads like a
queue problem rather than a configuration one.

### The Xvfb vignettes

`ex11` verifies the on-display path a GUI user takes, so it must not force
offscreen rendering:

```bash
xvfb-run -a --server-args="-screen 0 1024x1024x24" \
  python test_suite.py ../ --test_type ParaView --no-offscreen \
      --machine_name my-machine
```

---

## The performance history

Each vignette keeps a history at
`<vignette>/Testing/performance_metrics_<machine_name>.json`, and those files
are **committed to git**. That is what makes long-term comparison possible,
and it is also why a throwaway run should stay out of them.

### Keeping a run out of the history

```bash
python test_suite.py ../ --test_type ParaView --machine_name my-machine --no-metrics
```

`--no-metrics` (alias `--ephemeral`) changes nothing about what runs or what
is compared. The vignette executes, images are diffed, numbers are compared,
and the exit code means what it always meant. The only difference is that
nothing is appended.

The performance regression gate is skipped under `--no-metrics` as well, and
says so. It compares the two most recent records in the history file; with
this run absent, it would be comparing two *earlier* runs and reporting the
difference as if it belonged to this one.

The flag propagates: `test_suite.py` passes it to `run_tests.py`, which
records it in `run_result.json`, exports `VV_NO_METRICS=1`, and forwards
`--no-metrics` to the vignette itself. A vignette keeps no history of its own
-- its results JSON is a comparison input, not a log -- so there it only
appears in the output, which is what you want when you are reading a log
afterwards and wondering whether that run counted.

### What the gate calls a regression, and what it only reports

The gate compares the two most recent records in a history file. What it does
with a difference depends on *why* the two records differ, and this is the
same for ParaView and VisIt.

| The two runs differ by | Gate behaviour |
| :--- | :--- |
| Nothing but the numbers, same tool version | **Regression.** Over 10% on a metric fails the run and lands in `significant_performance_changes`. |
| Tool version (6.0.1 against 6.1.0, 3.4.1 against 3.4.2) | **Reported, not failed.** Printed with both version numbers, either direction, any size, and recorded under `version_comparisons`. |
| `metrics_schema` | **Refused.** The comparison is skipped and says so. |

Those three are genuinely different situations:

* A version change is a real difference in the software, and seeing it is a
  large part of why this suite exists. VisIt 3.4.1 costs 2.6x the memory of
  3.4.2 on `ex02`; a new release that got slower is worth knowing about. It
  does not fail the run, because the newest record is often deliberately an
  *older* build, such as the cluster version kept as a local reference, where
  "slower and fatter" is the expected answer rather than a problem. Read the
  direction in the message before drawing a conclusion.
* A `metrics_schema` change means the recorded field measured something else.
  Before schema 4, memory came from `RUSAGE_CHILDREN`, a high-water mark over
  every child the harness had reaped. Comparing that against a process-tree
  sample says nothing about either version, so the number is withheld rather
  than labelled. It is the only case where the gate hides something.

`--machine_name` names a machine and a rendering configuration, never a tool
version. Both versions of a tool belong in the same history file, with the
version recorded inside each record, which is how `shaheen3-cpu` has carried
VisIt 3.4.1 and 3.4.2 together since 2024 and how the ParaView files carry
5.13.1 alongside 6.x. Splitting them by file name hides exactly the
comparison the table above exists to produce.

### Cleaning up records that are already committed

`Testing/manage_metrics.py` edits the history files without disturbing their
schema or formatting: `indent=4`, insertion order untouched, trailing newline
preserved, written through a temporary file and renamed.

**Look first.**

```bash
# Everything, summarised: one row per file, then the runs grouped by run_id
python3 manage_metrics.py --list-runs

# One vignette or one machine, record by record, with indices
python3 manage_metrics.py --list-runs --vignette ex07_pvScaling
python3 manage_metrics.py --list-runs --machine-name my-laptop --detail

# For a script
python3 manage_metrics.py --list-runs --json
```

**Then prune.**

| Command | Effect |
| :--- | :--- |
| `--remove-latest` (`--pop`) | Removes the newest record from each selected file. |
| `--rollback N` | Removes the newest N records from each selected file. |
| `--remove-run RUN_ID` | Removes every record carrying that `run_id`, wherever it is. |

```bash
# Undo the last suite run everywhere
python3 manage_metrics.py --rollback 1 --yes

# Undo three runs, but only for one machine
python3 manage_metrics.py --rollback 3 --machine-name my-laptop --yes

# Undo one specific run even though later runs came after it
python3 manage_metrics.py --remove-run 20260906T101500-3f9c1a --yes
```

Narrow what is touched with `--machine-name`, `--test-type`, `--vignette`, or
`--file PATH` (repeatable, and bypasses discovery entirely).

**The unit of removal is one record: one vignette's result from one run.** A
suite run writes one record into each vignette's file, so removing the newest
record from every file is what undoes one suite run. `--rollback 3` with no
filters removes the last three suite runs.

Safety: every removal prints exactly which records will go before touching
anything. `--dry-run` stops there. Without `-y`/`--yes` you are asked to
confirm, and if stdin is not a terminal the tool refuses rather than guessing
-- an unattended script cannot delete history by accident. The files are
tracked in git in any case, so `git diff` shows what went and
`git checkout -- <path>` puts it back.

### run_id

Records written from now on carry a `run_id` shared by every vignette in one
`test_suite.py` invocation, which is what makes `--remove-run` precise and
`--list-runs` groupable. Records written before this existed carry only a
timestamp; they are listed and removed by timestamp exactly as before, and
nothing about them changed.

---

## One-time data preparation

Some vignettes read datasets that are generated rather than downloaded, and
none of the generated ones is portable: two are locked to a ParaView version,
one to a VisIt version, one holds absolute paths, and one is a converted copy
that goes stale when its source changes. One command handles all of it,
rebuilding only what is missing or stale:

```bash
python3 prepare_machine.py           # generate what is needed
python3 prepare_machine.py --check   # verify only; non-zero exit if not ready
python3 prepare_machine.py --force   # regenerate regardless
```

### The two time series, and why there are two

`data/varying_data/varying*.vtk` carries geometry and a scalar and **nothing
that says which timestep it is**. Both ParaView and VisIt therefore invent a
time from the file's position in the list, and they agreed on that invention
until VisIt 3.4.2 changed it from the state index to zero.

`data/make_time_series.py` converts the same twenty timesteps to XML `.vtr`
with `TIME` and `CYCLE` in each file's field data, a `series.pvd` for ParaView
and a `series.visit` for VisIt. All three builds in use here then read the same
real values:

```
timestep  0    1     2
cycle     0    100   200
time      0.0  0.05  0.10
```

ex05 puts that on the frame, in both suites: `Cycle: 300    Time: 0.15` in the
top-left corner. VisIt uses a `Text2D` annotation with its own `$cycle` and
`$time` macros; ParaView uses a `PythonAnnotation` reading `CYCLE` out of field
data, because `AnnotateTimeFilter` formats the time and nothing else. So the
frame is also the quickest way to see what a reader made of a series.

**ex05 and ex12 read the XML series**, because time is their subject.
**ex07, ex10 and ex11 keep the legacy series**, because ex11's ParaView state
exists to exercise `LegacyVTKReader` through a saved `.pvsm` and the other two
only need some data. Keeping both is deliberate: one shows what a reader does
when the file tells it the time, the other shows what it does when the file
does not.

The XML series is generated per machine and is not committed. `prepare_machine.py`
builds it and reports it stale when the source series has grown.

It finds `pvbatch` and `visit` the way `run_tests.py` does -- `$PARAVIEW_PATH`
and `$VISIT_PATH` first, then `PATH` -- and skips a tool that is not installed
rather than failing. It will not start `fetchData.sh` on your behalf; that is a
4.3 GB download and it says so instead.

`--check` is worth putting at the top of a job script.

### Why this is checked rather than trusted

Getting it wrong is quiet. An AMR hierarchy written by ParaView 6.1.0 opens
without complaint under 6.0.1, which then reads 216 points and 125 cells where
6.1.0 wrote 842 and 605. Nothing errors. `ex09` simply reports different numbers
and fails its numeric gate for a reason that looks like a regression in the
vignette.

So the fixtures carry their provenance and the vignettes check it:
`topologies_manifest.json` records the generating ParaView, a `.pvsm` already
records its own, and `ex09` and `ex11` refuse to run against a fixture from a
different major.minor -- naming the command that fixes it. A fixture with no
recorded version is warned about rather than failed, so an older checkout still
runs.

The underlying generators, if you need them individually:

```bash
pvbatch ../data/make_topology_datasets.py
pvbatch ../ParaView_Vignettes/ex11_pvStateVerification/ex11_make_state.py
visit -cli -nowin -noconfig -s ../VisIt_Vignettes/ex11_visitStateVerification/ex11_make_state.py
```

`ex10` needs nothing prepared. Its colour maps ship beside it
(`ex10_custom_colormap.xml` for ParaView, `ex10_ember.ct` and
`ex10_categorical.ct` for VisIt) and are loaded at run time, so no colour
table has to be installed into `~/.visit` first.

`data/fetchData.sh` is still required for the large datasets used by `ex06`.

---

## 🤖 Continuous Integration (GitHub Actions)

A GitHub Actions workflow runs `test_suite.py` for both ParaView and VisIt on every commit.

> **Keep `--machine_name` stable.** It names the metrics file. When it is
> omitted the name falls back to the container hostname, which differs on
> every CI run, so each run writes a fresh history with a single sample --
> and the performance-change detector needs two. Pass a fixed value such as
> `--machine_name ci-linux-x86_64` and persist the metrics JSONs between runs
> or the performance gate can never fire.

### How to Find Build Artifacts

Artifacts (logs, plots, and data) are attached to the specific workflow run that created them.

1. Click the **"Actions"** tab at the top of the repository.
2. Click on the specific **workflow run** you want to inspect.
3. On the summary page for that run, scroll to the bottom to find the **"Artifacts"** section.
4. You can download the files (usually as a `.zip` archive) from there.

> 💡 **Note:** GitHub artifacts are temporary and automatically expire (default is 90 days).
