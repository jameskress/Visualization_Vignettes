# Regression and Performance Testing

This `test_suite.py` script runs performance and regression tests for **VisIt** and **ParaView** on **Ibex** and **Shaheen**. It also provides a convenient method to run all examples in the **ParaView** or **VisIt** directories without running each one manually.

**Results:** the [results dashboard](https://jameskress.github.io/Visualization_Vignettes/dashboard/)
shows the latest result of every vignette on every configuration and how its
measurements moved across tool versions and runs, rebuilt from the committed
history on every change ([how it works](#the-results-dashboard)). To put
another machine on it, see [Add your site](ADD_YOUR_SITE.md).

> ⚠️ **Important:** In all examples below, replace paths like `~/Visualization_Vignettes/` with the actual path to your cloned repository. HPC paths are written using variables like `$SCRATCH` to be easily copy-pasted.
> ⚠️ **Important:** You must use the `fetchData.sh` script before running these tests for them all to work.

Two companion documents:

* [`LOCAL_VALIDATION.md`](LOCAL_VALIDATION.md), the current status of every
  vignette under each tool version, the defect log behind the fixes, and the
  measurements behind the baseline and tolerance decisions.
* [`RUNBOOK.md`](RUNBOOK.md), how to run the suite on a workstation, Ibex,
  Shaheen `workq` and Shaheen `ppn`, for ParaView and VisIt, online or
  air-gapped, with a troubleshooting table.

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
> [`RUNBOOK.md`](RUNBOOK.md). Do not copy a virtual environment:
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
* **`--repeat N`**: Run the selected vignettes N times, in N passes over the whole selection, and record every run (each record carries `repeat: {index, of}`). One run is easily skewed by whatever else the host was doing; three or more outvote a disturbed run and give the dashboard a spread to test a difference against. Every pass runs every gate and the run fails if any pass does. The performance gate and drift judge the median of the N runs against earlier runs, never one repeat against another. `record_local_run.sh` uses 3 (`REPEAT=`). Cannot be combined with `--bless`, `--submit` or `--generate-metrics`.
* **`--run-id ID`**: Tag every record this invocation writes. Defaults to a generated id; pass one explicitly to group a ParaView run and a VisIt run into a single logical run.

---

## 🧪 Running the Tests

The suite is pinned to **ParaView 6.2.1** and **VisIt 3.5.0** (`CURRENT_PINS`
in `dashboard.py`; on the clusters `ParaView_Vignettes/MODULES.sh` and
`VisIt_Vignettes/MODULES.sh` load them). [`RUNBOOK.md`](RUNBOOK.md) covers
every machine in full, including air-gapped use; the short versions follow.

Every run compares; only a run without `--no-metrics` appends to the
committed history. Use `--no-metrics` while experimenting, and record one run
per configuration with `--run-id <id> --repeat 3` (see
[The performance history](#the-performance-history)).

### Local machine

This assumes a `venv` per tool (e.g., `~/testing_paraview_env`) and the repo in
your home directory.

#### ParaView

```bash
export PARAVIEW_PATH="<path-to-your-paraview-6.2.1>/bin"
source ~/testing_paraview_env/bin/activate
cd ~/Visualization_Vignettes/Testing
python test_suite.py ~/Visualization_Vignettes/ \
  --test_type ParaView \
  --paraview_version 6.2.1 \
  --machine_name local-machine --no-metrics
```

#### VisIt

```bash
export VISIT_PATH="<path-to-your-visit-3.5.0>/bin/"
source ~/testing_visit_env/bin/activate
cd ~/Visualization_Vignettes/Testing
python test_suite.py ~/Visualization_Vignettes/ \
  --test_type VisIt \
  --visit_version 3.5.0 \
  --machine_name local-machine --no-metrics
```

A recorded run of both tools, three repeats, ex11 under Xvfb, from the same
`Testing/` directory: `./record_local_run.sh <run-id> <machine_name>` (RUNBOOK
section 4).

---

### Clusters: the batch scripts

The normal way to run the suite on Ibex and Shaheen is one batch script per
tool and machine, submitted from `Testing/` in the clone. Each loads the pinned
modules through `MODULES.sh`, prepares the fixtures, runs every vignette, and
runs ex11 under Xvfb where the node has it.

| Configuration (`--machine_name`) | ParaView | VisIt |
| :--- | :--- | :--- |
| Ibex CPU (`ibex-cpu`) | `sbatch ibex_pv_suite.sbat` | `sbatch ibex_visit_suite.sbat` |
| Ibex GPU (`ibex-egl-<gpu>`; VisIt `ibex-gpu`) | `sbatch --gres=gpu:1 --constraint=<gpu> --ntasks=4 --cpus-per-task=4 --export=ALL,VARIANT=egl,GPU=<gpu> ibex_pv_suite.sbat` | `sbatch --gres=gpu:1 --constraint=a100 --ntasks=8 --cpus-per-task=2 --mem=90G --export=ALL,VARIANT=gpu ibex_visit_suite.sbat` |
| Shaheen `workq` (`shaheen3-cpu`) | `sbatch shaheen_pv_suite.sbat` | `sbatch shaheen_visit_suite.sbat` |
| Shaheen `ppn`, Mesa (`shaheen3-mesa-ppn`) | `sbatch --export=ALL,VARIANT=mesa shaheen_ppn_pv_suite.sbat` | |
| Shaheen `ppn`, GPU (`shaheen3-ppn-gpu-L40`; VisIt `shaheen3-ppn`) | `sbatch shaheen_ppn_pv_suite.sbat` | `sbatch shaheen_ppn_visit_suite.sbat` |

* The scripts do not use the environments from the setup above. They
  activate their own: on Ibex `$VV_IBEX_SW/venvs/vv` (default
  `/ibex/scratch/$USER/hpcsaudi`), on Shaheen
  `$SCRATCH_IOPS/sw/testing_paraview_env` and `testing_visit_env`, with numpy
  for ParaView's Python in `sw/pv-site` beside them. Make them once per
  machine before the first submission: RUNBOOK section 5 (Ibex), 6 and 7
  (Shaheen).
* VisIt does not build the shared fixtures (`data/topologies`,
  `data/varying_series_xml`); ParaView's preparation does. Run the ParaView
  suite in the clone first and let it finish, or copy those directories from
  a clone that has them (RUNBOOK section 5). Submitting both at once does not
  order them.
* Ibex GPUs: `a100`, `v100`, `p100`, `rtx2080ti`, `gtx1080ti` (`p6000` is
  retired). Ibex caps CPUs per GPU (16 on an A100, 6 on a V100: use
  `--ntasks=2 --cpus-per-task=3` there); a GPU job takes no `--partition`.
* The default is `--no-metrics`. For the one recorded run, add
  `EXTRA="--run-id <configuration>-$(date +%F) --repeat 3"` (with `--export`,
  inside it). `TESTS="5 6"` runs a subset.
* `VV_PARAVIEW_MODULE` / `VV_VISIT_MODULE` select another build. Test each
  build in its own clone: the generated fixtures are per ParaView version.
* Three repeats triple the time; the longest current suite is 11 minutes,
  within the scripts' 2-hour limit.

### Clusters: interactive, for debugging

```bash
srun <the resources from the table, as srun flags> --pty /bin/bash
cd $SCRATCH/Visualization_Vignettes
source ParaView_Vignettes/MODULES.sh mesa     # or egl; VisIt: source VisIt_Vignettes/MODULES.sh
cd Testing
python test_suite.py ../ --test_type ParaView --paraview_version 6.2.1 \
  --machine_name <configuration> --test_number 3 --no-metrics
```

The batch scripts set up a few site details this skips (the ParaView wrapper
that keeps its `PYTHONPATH` from other Pythons, the Ibex module tree); see
RUNBOOK sections 5 to 7 before recording anything this way.

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
| `--no-offscreen` | Do not force offscreen rendering. Required by `ex11`, which runs under `Scripts/run_with_display.sh`. |
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
python test_suite.py ../ --test_type VisIt --visit_version 3.5.0 \
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
XVFB_SCREEN=1024x1024x24 ../Scripts/run_with_display.sh \
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

### A vignette whose input is not there

`ex06` is the only vignette whose inputs are not in the repository. The
cyclone multiblock and the rainfall silo are 5.7 GB extracted, fetched once
by `data/fetchData.sh`, and deliberately not committed. A fresh clone that has
not run that script, and CI, which has no business downloading it, are both
expected states.

So `ex06` checks for them first, and if they are absent it reports **SKIPPED**
and stops:

```text
Vignette SKIPPED: cyclone-chapala-2015-11-02_00-00-00-mb.vtm is not present.
This vignette needs the 5.7 GB extracted dataset; run data/fetchData.sh once
to get it.
```

A skip is neither a pass nor a failure:

* No gate runs against it. There are no images, results or extracts to
  compare, so every gate would be measuring this run's nothing against the
  baseline's something.
* Nothing is appended to the performance history. The recorded time would
  describe the existence check, and a 0.3 s record in a history of 190 s ones
  would make the next real run look like a catastrophic regression.
* It does not fail the suite. `test_suite.py` still exits 0.
* It is reported, in the run output and under `skipped_tests` in the summary
  report. A suite that silently passes a vignette which never ran is lying
  about its coverage.

This is for an input that is absent *by design*. Anything the repository
ships or generates uses `ctx.dataset(key)` instead, which raises, because a
missing generated fixture is a setup problem worth stopping for.

### What the gate calls a regression, and what it only reports

The gate compares the two most recent records in a history file. What it does
with a difference depends on *why* the two records differ, and this is the
same for ParaView and VisIt.

| The two runs differ by | Gate behaviour |
| :--- | :--- |
| Nothing but the numbers, same tool version | **Regression.** Over 10% on a metric fails the run and lands in `significant_performance_changes`. |
| Tool version (6.0.1 against 6.1.0, 3.4.1 against 3.4.2) | **Reported, not failed.** Printed with both version numbers, either direction, any size, and recorded under `version_comparisons`. |
| `metrics_schema` older than 5 | **Refused.** The comparison is skipped and says so. Schema 6 only added fields, so 5 and 6 compare (`MIN_COMPARABLE_SCHEMA` in `metrics.py`). |

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

### What a record holds (metrics schema 8)

Schemas 6, 7 and 8 added fields and changed the meaning of none, so their CPU
and memory compare with schema 5's. Schema 8 adds one memory scope: a run
whose ranks srun launched on a single-node job records its exact peak
(`step-vmhwm-single-node`, below). The gate, drift and the dashboard compare
memory only within one scope, so those runs start a new memory series rather
than being compared with Slurm's sampled figures. Every field below is optional: a record carries it
only when it could be measured, and never fills a gap from another run.

| Field | What it is |
| :--- | :--- |
| `verdicts` | Each gate's raw result for this run: `run` (bool), `image` and `csv` (`PASS`, `FAIL` or null when the vignette has none), `image_statuses` (count per image status), `numeric` (the results-JSON comparison status), `text` (legacy log match, or null), and `passed`, the comparison gates' verdict as the summary judges them. The gates are raw; `passed` applies the summary's GPU exemption, and `gpu_exempt` is set when it did (ex00 and ex08 on a `--non_gpu_machine`). The performance gate is not in `passed`: it compares this record with the history after it is written, so its verdict is in the summary report. |
| `build` | `tool`, `version`, `launcher` (pvbatch, srun, visit), `ranks`, `opengl_window` (the VTK window class the harness chose) and `id`: the first 12 hex digits of the SHA-256 of the tool executable's resolved path, following a small wrapper script's `exec`. The path itself is not recorded, because on the clusters it is a module path. Same id, same install. |
| `baseline` | `ref` (`--baseline-ref`, null for the working tree), `commit` (the last commit to touch this vignette's `Testing/Baseline/` at that ref) and `image_sources` (how many images were judged against the shared set and how many against `Baseline/<machine_name>/`). |
| `repo` | `commit` of the checkout that ran, and `dirty` when tracked files other than the history files were modified. |
| `io_read_mb`, `io_write_mb` | Storage reads and writes summed over the sampled process tree (`/proc/<pid>/io` `read_bytes`, `write_bytes`), scope `io_scope: child-tree-proc-io`. Each sample sums one walk of the tree, which counts a reaped child once (in its parent) and never twice; the run records the largest sum, a lower bound that misses the last fraction of a second and an orphan's I/O after it leaves the tree (`LOCAL_VALIDATION.md` 4b.16). A run that finds its input in the page cache reads almost nothing, so a first run after a reboot or a cache flush reads far more than the next. Local-tree runs only. |
| `io_rchar_mb`, `io_wchar_mb` | Every read and write call, cached or not (`rchar`, `wchar`). |
| `peak_processes`, `peak_threads` | The most processes and threads the tree had at once. |
| `energy_joules` | Energy the run used, recorded only when the Slurm job owned every CPU of every node it held, because both sources count whole nodes. `energy_scope` says which: `slurm-steps-whole-nodes` (sum of `ConsumedEnergyRaw` over the run's steps, for srun runs) or `node-pm-counters` (`/sys/cray/pm_counters/energy` before and after, for runs on the harness's node, with `energy_cpu_joules` and `energy_memory_joules` beside it). Never recorded on Shaheen's shared or ppn partitions, nor on the workstation. |
| `load_1m_at_start`, `load_1m_at_end` | The host's one-minute load average when the vignette started and when it ended (the end figure, schema 7, includes the vignette's own processes). Context, not a measurement of the run: a start and end both well above the vignette's own rank count say the host was shared, and that is the first thing to look at when a time swings. |
| `repeat` | `{index, of}` when the run was one of N (`--repeat`, schema 7). The gate and drift fold a repeated run into one by its median (`drift.collapse_repeats`). |
| `job_owns_its_nodes` | Whether the Slurm job held every CPU of its nodes (`SLURM_JOB_CPUS_PER_NODE` against the node's CPU count). False outside Slurm. |
| `opengl_window` | `VTK_DEFAULT_OPENGL_WINDOW` as launched (ParaView). |
| `machine_info.cpu_model`, `.logical_cpus`, `.memory_total_gb` | The host's hardware. |
| `machine_info.os_release`, `.cpu_governor`, `.gpus` | What a system update changes (schema 7): the OS release (`PRETTY_NAME`), the CPU frequency governor, and each visible GPU's name and driver from `nvidia-smi`. Read once per invocation; left out when it cannot be read. With the kernel `release` and `build.id`, a step in a history can be tied to a system change. |
| `machine_info.cpu_driver`, `.cpu_boost`, `.cpu_max_mhz`, `.smt_active`, `.numa_nodes`, `.thp`, `.hugepages_2m`, `.cpu_microcode`, `.kernel_cmdline_digest` | The node settings a maintenance can change without changing the OS name (schema 8, #140; the same set the Gray-Scott telemetry records): frequency driver, turbo boost, maximum frequency, SMT, NUMA nodes, transparent and 2 MB huge pages, CPU microcode, and the first 12 hex digits of the SHA-256 of `/proc/cmdline` (the command line itself can name hosts and paths). The dashboard lists the first values and every change per configuration under System settings. |
| `step_hwm_mb` | The exact peak memory of the vignette's processes on this node (schema 8, #140): `VmHWM`, the kernel's high-water mark of each process's resident set, read 10 times a second for every process carrying the run's step name (`VV_SLURM_STEP_NAME`, which srun's tasks and VisIt's engine inherit), summed per process like Slurm's figure (so RSS, shared pages counted per process). Slurm samples task memory at most once a second, so a 2 s step gets one sample; this does not miss the peak unless a process reaches it in its last 0.1 s. Slurm runs only. For a run whose ranks srun launched (Shaheen, and VisIt's engine on Ibex and Shaheen) in a one-node job (`job_nodes`), it is also the run's memory figure: `memory_usage_mb` takes it, with `memory_measurement_scope: step-vmhwm-single-node`, and Slurm's figure stays beside it as `slurm_memory_mb` with its scope in `slurm_memory_scope` (absent when Slurm never sampled a step). On Shaheen, Slurm's 1 s figure was 0.5 to 7% below this on steps of 4 s or more and 22 to 57% below on short peaks (#140). It covers every process of the run, the srun client and VisIt's CLI and viewer included, all as RSS, where Slurm's figure added the local tree as PSS, so for VisIt the first exact figures sit somewhat higher for that reason too. A multi-node job keeps Slurm's figure, since the poller reads only its own node; a local process tree keeps PSS, which counts shared pages once. `step_hwm_processes` and `step_hwm_samples` say what it covered; `step_hwm_mean_sample_s` is the cost of one scan. |
| `power_mean_node_w`, `power_peak_node_w` (and `_cpu_w`, `_memory_w`), `temp_peak_cpu_c`, `power_samples` | Node, CPU and memory power during the vignette and the hotter CPU's peak temperature, from `/sys/cray/pm_counters` once a second (schema 8). Whole-node jobs on Cray nodes only, like `energy_joules`. For srun runs, whose `energy_joules` comes from Slurm, the pm_counters split is recorded too: `energy_pm_node_joules`, `energy_cpu_joules`, `energy_memory_joules`. |
| `gpu_telemetry`, `gpu_memory_peak_mib`, `gpu_power_peak_w` | Per visible GPU, from one `nvidia-smi -lms 1000` running for the vignette's duration (schema 8): peak memory used, mean and peak utilisation and power. `gpu_memory_peak_mib` and `gpu_power_peak_w` are the busiest GPU's. A GPU the vignette did not use is still listed, and on the workstation the display's own use is included. |

All of it is read in the passes the harness already made: a few extra `/proc`
reads per 0.25 s sample, one more `sacct` field, two file reads on a Cray
node, one `git log` per vignette, and one `nvidia-smi` query per invocation.
Schema 8 adds one thread per vignette: a `/proc` scan 10 times a second
under Slurm (about 5 ms each with 1,300 processes on the workstation), a
pm_counters read once a second, and one `nvidia-smi` process. On a Shaheen
compute node one scan took 7 ms, about 7% of one core of 192, and setting
`SLURM_ACCTG_FREQ=task=1` did not change suite times (510.4 s against
510.4 s at the 600 s default, #140).

## The results dashboard

`Testing/dashboard.py` turns every committed history file into a static site.
Beside it, `Testing/site_pages.py` writes the Pages landing page and the
[gallery](https://jameskress.github.io/Visualization_Vignettes/gallery/):
each vignette's default baseline images (`Testing/Baseline/*.png|jpg`),
ParaView ex00 to ex12 first, then VisIt ex00 to ex12, frames in their
natural order, with small previews when Pillow is installed. Per-site
baseline sets are counted, not shown. The landing page says what the project
is, gives the headline numbers from the records (vignettes, configurations,
tool versions, the latest pass rate) and links to everything else. A new
vignette number needs its one-line description in `ABOUT` in `dashboard.py`;
`test_site_pages.py` fails until it has one. `.github/workflows/dashboard.yml`
publishes all three, and rebuilds them when a baseline changes. The design
(#106) was agreed from a mock-up, after a look at Codespeed, ASV, Perfherder,
LNT and ReFrame.

The **index** leads with a summary line (latest passes, failures, stale
configurations, drift warnings, the pinned builds) and a short "How to read
this". A tool switch shows one tool at a time; without script both show.
Then:

* *What the upgrade changed.* One version pair for every machine, named in
  the heading (for example ParaView 6.0.1 &rarr; 6.2.1), with a selector for
  the other pairs against the pinned build. Each cell is the vignette's median
  time at the pinned build against its median at the older version, from runs
  of the same vignette code, as a percentage. A cell is coloured only when the
  change is real: at least 10% (`MIN_CHANGE`) and Welch's t-test on the runs at
  the two versions gives p below 0.05 (`SIG_P`), the rule Perfherder uses.
  Five steps: dark and light blue faster (more than 20%, 10 to 20%), no fill
  within the noise, light and dark red slower. A dotted number had one run at
  a version, so there is no spread to test it against; `--repeat 3` fixes
  that. A change exactly at 10% counts, and one whose mean moved the other way
  from its median is not coloured, since the t-test compares means. Below it,
  the **biggest changes**: the real ones, largest first, as in ASV, each
  linking to the vignette's page.
* *Speed by version.* The whole suite's time at each version against the
  same machine's current one, the geometric mean over vignettes of the
  median-time ratio. One chart puts every machine on a shared axis, coloured
  by site and labelled directly; then one panel per machine on its own scale,
  never narrower than 0.8&times; to 1.25&times; so noise does not look like a
  cliff, with the 1&times; line always drawn.
* *Did everything pass?* A heatmap per tool of vignette by configuration,
  grouped by site: the latest result of each vignette there.
* *System changes.* The 20 most recent OS, kernel, GPU driver and CPU
  governor changes on active configurations, from both tools' records
  (`PLATFORM_FIELDS`); every change is also marked on the run histories. A
  setting seen for the first time is not a change.
* *Which machine is fastest?* Each vignette's latest time on every active
  configuration at the pinned version, on a log scale, coloured by site. Only
  runs of the vignette's newest known revision are set side by side.

Run histories, on vignette and configuration pages, follow the layout of
`plot_metrics.py`: **x is the machine's own run number**, so the months
between runs leave no gaps (dates are in the tooltips and the tables). Colour
and marker shape are the tool version: one blue ramp, light for old and dark
for new, with a shape per version, so versions read in colour, shape and
print. A hollow marker is not comparable with the latest run. A dashed amber
line marks the first run after a system change; hover it for what changed.

**Only runs of the same vignette revision are compared.** The vignettes
change too: ex00 to ex06 were rewritten on 17 September 2026 and several
have changed since, so a 2024 run of ParaView 5.13.1 measured a different
test from a 6.2.1 run today. `dashboard.py` reads from git which revision of
each vignette every record ran. A clean record with a `repo.commit`
(schema 6) gets the revision at that commit. Any other record, an older one
or one run from a dirty checkout, is bounded: no earlier than the last change
committed before it ran, no later than the code current when its record was
committed (`git blame` of the history file). If the vignette changed inside
those bounds the record may have run code committed after it, so it gets a
revision of its own and is never compared. A revision
is a change to the vignette's own Python files that changes their code
(compared as syntax trees, so comments, docstrings and layout do not count).
Generated data fixtures (`data/*.py`) are not followed. Both summary charts
compare within one revision; on a configuration page the runs of older
revisions are drawn hollow, and drift is judged within a revision. Each run's revision is in its table and in
`records.json` (`vignette_revision`). The build needs the git history; in a
copy without it every run is compared, and the build says so.

A vignette's latest result (the heatmap, the tables, staleness) is its last
run of the newest version the configuration has run, so a backfill of older
builds on today's vignettes, recorded later, does not replace it.

Then the table of active configurations (last run, version, latest results,
drift count) and the table of retired ones.

Each **vignette page** (`v-<vignette>.html`) shows one vignette on every
active machine: its latest result there, and a run-history panel per machine
for execution time and for peak memory. Each **configuration page** has, per
vignette, the result strip, a run-history chart per metric (metrics whose
every value is under 1 MB or 1 J left out as noise), drift, and every run with
its build and baselines. `records.json` holds every
record flattened with its configuration, site, tool and vignette, for analysis
elsewhere. The host name each record carries (`machine_info.node`, a compute
node on the clusters) is left out of all of it, as are executable paths.
Configuration names are the history files' names, except where a file is
named after a host: `PUBLIC_NAMES` in `dashboard.py` gives those a public
name (`KW61316.kaust.edu.sa` is published as `workstation`), in the page
names, the tables, `records.json` and the run ids. A dotted configuration
name with no public name stops the build, so a new host name cannot reach
the site.

How to read the results:

| Shown | Meaning |
| :--- | :--- |
| pass, fail | every comparison gate's verdict, recorded from metrics schema 6 |
| ran OK, run failed | an older record: it says only whether the vignette's own run succeeded |
| unknown | the oldest records, which say neither |
| drift n/a | no vignette there has the three earlier comparable runs the drift rule needs |
| stale | no run for 30 days, or the last run used an older version than the suite pins (`CURRENT_PINS` in `dashboard.py`; move it with the pinned builds) |
| &middot; in the upgrade table | no runs of the same vignette code at both versions on that machine: not compared |
| retired | listed in `Testing/retired_configurations.json`: never stale, left out of the summary charts, history and page kept |

Nodes and GPU types come and go while the vignettes stay. When one leaves the
suite, add its configuration to `Testing/retired_configurations.json` with the
date and a reason; leave its history files in place. Delete the entry if the
hardware comes back. A malformed file stops the dashboard build rather than
putting every retired configuration back on the front page as stale.

```json
"ibex-egl-p6000": {"since": "2026-11-16", "reason": "the P6000 nodes were removed from the suite's runs"}
```

```bash
# The Pages layout: the landing page at the root, dashboard/ and gallery/
python3 Testing/dashboard.py --out _site/dashboard   # standard library only
python3 Testing/site_pages.py --out _site            # Pillow optional
cp _site/root/index.html _site/
python3 -m http.server --directory _site             # look at it
```

`.github/workflows/dashboard.yml` builds it on a GitHub-hosted runner and
publishes it to <https://jameskress.github.io/Visualization_Vignettes/dashboard/>
on every master push that changes a history file, the generator, the
retired list or a vignette script; a pull
request builds it and attaches the site as an artifact. Pages serves the
`gh-pages` branch, which also holds the Docker badge at its root; each
workflow replaces only its own files there. The dashboard workflow replaces
`dashboard/` and `gallery/` whole and writes the landing page as the root
`index.html` (published with `keep_files`, so the badge stays).

### Harness unit tests

`.github/workflows/harness-tests.yml` runs these on a GitHub-hosted runner
whenever a `Testing/` Python file, this README or a `MODULES.sh` changes. They
need only psutil and run in about a second.

| Test | What it checks |
| :--- | :--- |
| `test_io_sampler.py` | the process-tree I/O sum, with the reap order scripted, plus one real non-dumpable child (Linux) |
| `test_repeats.py` | `--repeat` runs folded to their median for the gate and drift |
| `test_docs_pins.py` | every module name and `--paraview_version` / `--visit_version` in the commands of this README and `ADD_YOUR_SITE.md`, and the default the `MODULES.sh` scripts load, matches `CURRENT_PINS` in `dashboard.py`. Move the pins and the recipes together. |
| `test_check_submission.py` | `check_submission.py`, the checks a pull request of results must pass ([Add your site](ADD_YOUR_SITE.md)), and that every committed history file passes them |
| `test_site_pages.py` | the gallery and landing page generator: default baseline set only, previews that never collide with each other or an image, URL-encoded paths, and every vignette number has its description in `ABOUT` |
| `test_dashboard_redesign.py` | the dashboard's Welch t-test (checked against SciPy), the five change classes, system changes per run and their markers on the run charts, the version colour ramp, and the upgrade table's like-for-like cells |

```bash
python3 -m unittest -v Testing/test_io_sampler.py Testing/test_repeats.py Testing/test_docs_pins.py Testing/test_check_submission.py Testing/test_site_pages.py Testing/test_dashboard_redesign.py
```

## Drift warnings

The performance gate compares the last two runs and fails at 10%.
`Testing/drift.py` asks a different question: is this run unusual for this
vignette, against many earlier runs? It warns and never fails the suite.

For each of execution time, CPU seconds, peak memory, Slurm disk read and
write, process-tree storage read and write, and energy, the history is the
earlier runs of the same vignette in the same history file (so the same
configuration), with the same tool version, metrics schema 5 or later (any
schema for execution time), and the same measurement scope. Of those, the
latest 20 are summarised by their median and median absolute deviation
(MAD). A run is flagged when all three hold:

| Condition | Why |
| :--- | :--- |
| at least 3 earlier runs | fewer cannot say what normal is; the run gets no verdict |
| \|x - median\| >= 4 x 1.4826 x MAD, or MAD is 0 | outside this history's own noise (about four sigma) |
| \|x - median\| >= the relative floor x median and >= the absolute floor | big enough to be worth reading about |

| Metric | Relative floor | Absolute floor |
| :--- | ---: | ---: |
| execution time, CPU seconds | 25% | 2 s |
| peak memory | 25% | 64 MB |
| disk and storage read, write | 50% | 16 MB |
| energy | 25% | 500 J |

A faster or smaller run is flagged as readily as a slower one: either way
something changed. The thresholds and the measurement behind them are in
`LOCAL_VALIDATION.md` section 4b.16; they live at the top of `drift.py`.

Warnings appear three ways: a `DRIFT (warning)` line under the vignette and a
`Drift warnings` block at the end of the harness output, a `drift_warnings`
list in `<tool>_<machine>_summary_report.json` (and `drift` on the vignette's
`test_results` entry), and a highlighted point and row on the dashboard. They
never set `any_tests_failed`. Like the gate, the check runs only when this run
appended a record, so `--no-metrics` runs report none.

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
