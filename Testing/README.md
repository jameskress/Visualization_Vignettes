# Regression and Performance Testing

This `test_suite.py` script runs performance and regression tests for **VisIt** and **ParaView** on **Ibex** and **Shaheen**. It also provides a convenient method to run all examples in the **ParaView** or **VisIt** directories without running each one manually.

> ⚠️ **Important:** In all examples below, replace paths like `~/Visualization_Vignettes/` with the actual path to your cloned repository. HPC paths are written using variables like `$SCRATCH` to be easily copy-pasted.

> ⚠️ **Important:** You must use the `fetchData.sh` script before running these tests for them all to work. 

---

## What This Suite Does

When you run `test_suite.py`, it performs several actions for each test vignette:

1.  **Regression Test:** Runs the test script and compares any generated text or image outputs against a "baseline" version stored in that test's `baseline/` directory.
2.  **Performance Test:** Records execution time, memory usage, and CPU usage for the run.
3.  **Data Logging:** Saves the new performance metrics into a `performance_metrics_*.json` file in the test's `Testing/` directory.
4.  **Plot Generation:** Updates the performance graphs (`.png` files) inside that same `Testing/` directory, showing the new run alongside all previous ones.

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
pip3 install pandas matplotlib psutil scipy
deactivate

# 2. ParaView GPU Environment (for Shaheen GPU)
python3 -m venv $SCRATCH/testing_paraview_gpu_env
source $SCRATCH/testing_paraview_gpu_env/bin/activate
pip3 install pandas matplotlib psutil scipy
deactivate

# 3. VisIt Environment (CPU & GPU)
python3 -m venv $SCRATCH/testing_visit_env
source $SCRATCH/testing_visit_env/bin/activate
pip3 install pytz six pyparsing psutil pandas matplotlib scipy
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
    1.  Name the output JSON and plot files (e.g., `performance_metrics_ibex-cpu.json`).
    2.  Allow the plotting script to correctly group runs from the same machine.
* **`--paraview_version` / `--visit_version`**: The version number of the software being tested. This is saved as metadata in the JSON logs.
* **`--non_gpu_machine`**: A flag that tells the test script to enforce a CPU-only execution path. This is required for CPU-only ParaView modules (`-mesa`) to prevent them from trying to find a GPU.

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
| gtx1080ti | `--gres=gpu:gtx1080ti:1`| `ibex-egl-gtx1080ti` |

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

This suite performs regression testing by comparing output files (like images or text) to a "baseline" stored in each test's `baseline/` directory.

* **If a test runs and `baseline/` is empty:** The script will *create* a new baseline by copying the contents of the `output/` directory into it. You will see a log message like "No baseline found, creating one...".
* **If a baseline exists:** The script will compare the new `output/` files with the `baseline/` files. If they differ, the test will be marked as "failed."
* **How to Update a Baseline:** If a test fails due to a change you *expected* (e.g., you improved an image), you must **manually delete the old files** in that test's `baseline/` directory. The *next* time you run the test, it will see an empty directory and create a new baseline from the latest output.

---

## 🤖 Continuous Integration (GitHub Actions)

A GitHub Actions workflow runs `test_suite.py` for both ParaView and VisIt on every commit.

### How to Find Build Artifacts

Artifacts (logs, plots, and data) are attached to the specific workflow run that created them.

1.  Click the **"Actions"** tab at the top of the repository.
2.  Click on the specific **workflow run** you want to inspect.
3.  On the summary page for that run, scroll to the bottom to find the **"Artifacts"** section.
4.  You can download the files (usually as a `.zip` archive) from there.

> 💡 **Note:** GitHub artifacts are temporary and automatically expire (default is 90 days).
