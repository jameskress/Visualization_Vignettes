# Regression and Performance Testing

This `test_suite.py` script runs performance and regression tests for **VisIt** and **ParaView** on **Ibex** and **Shaheen**. It also provides a convenient method to run all examples in the **ParaView** or **VisIt** directories without running each one manually.

> ⚠️ **Important:** In all examples below, replace paths like `~/Visualization_Vignettes/` with the actual path to your cloned repository. HPC paths are written using variables like `$SCRATCH` to be easily copy-pasted.
> ⚠️ **Important:** You must use the `fetchData.sh` script before running these tests for them all to work.

---

## What This Suite Does

When you run `test_suite.py`, it performs several actions for each test vignette:

1. **Regression Test:** Runs the vignette and compares its outputs against the baselines stored in that test's `Testing/Baseline/` directory.
2. **Performance Test:** Records execution time, memory usage, and CPU usage for the run.
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

`--bless` records both the images (up to `--max-baseline-images`, default 5)
and the structured results JSON. Review the diff before committing: a blessed
baseline is an assertion about what correct looks like.

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

Some vignettes read datasets that are generated rather than downloaded:

```bash
# ex09 (both suites) -- four mesh topologies plus a shared scalar field
pvbatch ../data/make_topology_datasets.py

# ex11 ParaView -- regenerate per ParaView major version
pvbatch ../ParaView_Vignettes/ex11_pvStateVerification/ex11_make_state.py

# ex11 VisIt -- regenerate per VisIt version
visit -cli -nowin -s ../VisIt_Vignettes/ex11_visitStateVerification/ex11_make_state.py
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
