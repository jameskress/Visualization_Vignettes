# Regression and Performance Testing

This `test_suite.py` script runs performance and regression tests for **VisIt** and **ParaView** on **Ibex** and **Shaheen**. It also provides a convenient method to run all examples in the **ParaView** or **VisIt** directories without running each one manually.

> ⚠️ **Important:** In all examples below, replace paths like `/ibex/scratch/kressjm/` or `/home/kressjm/` with your own user paths.

---

## 🐍 Initial Setup: Python Environments

Before running tests on HPC systems, you need to create Python virtual environments (`venv`) to install necessary packages.

> 💡 **Note:** On systems like Shaheen, compute nodes do not have internet access. You **must run the `pip install` commands on a login node** *after* creating the environment.

### 1. ParaView Environment

This environment is needed for all ParaView HPC test runs.

```bash
# Create the environment
python3 -m venv /ibex/scratch/kressjm/testing_paraview_env

# Activate it
source /ibex/scratch/kressjm/testing_paraview_env/bin/activate

# Install packages (run on a login node)
pip3 install pandas matplotlib psutil scipy

# You can now deactivate
deactivate
```

### 2. VisIt Environment

This environment is needed for all VisIt HPC test runs.

```bash
# Create the environment
python3 -m venv /ibex/scratch/kressjm/testing_visit_env

# Activate it
source /ibex/scratch/kressjm/testing_visit_env/bin/activate

# Install packages (run on a login node)
# We install the superset of packages needed for both Ibex and Shaheen
pip3 install pytz six pyparsing psutil pandas matplotlib scipy

# You can now deactivate
deactivate
```

---

## 🧪 Running the Tests

### 💻 Local Machine

#### ParaView
```bash
export PARAVIEW_PATH="<path-to-your-paraview-install>/bin"
source <path-to-your-paraview-venv>/bin/activate
cd Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/Visualization_Vignettes/ \
  --test_type ParaView \
  --paraview_version 5.13.1
```

#### VisIt
```bash
export VISIT_PATH="<path-to-your-visit-install>/bin/"
source <path-to-your-visit-venv>/bin/activate
cd Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/Visualization_Vignettes/ \
  --test_type VisIt \
  --visit_version 3.4.1
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
source /ibex/scratch/kressjm/testing_paraview_env/bin/activate
cd Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/Visualization_Vignettes/ \
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
source /ibex/scratch/kressjm/testing_visit_env/bin/activate
cd Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/Visualization_Vignettes/ \
  --test_type VisIt \
  --visit_version 3.4.1 \
  --machine_name ibex-cpu
```

#### Ibex GPU (ParaView)

This test can be run on multiple GPU types.

```bash
# 1. Load module
module load paraview/5.13.1-gnu-egl

# 2. Request an interactive GPU job
#    Replace <gpu-flag> with the correct value from the table below
srun <gpu-flag> --cpus-per-task=12 --ntasks=1 --time=00:40:00 --mem=100G --pty /bin/bash

# 3. Once in the job, run the tests
#    Replace <machine-name> with the correct value from the table below
source /ibex/scratch/kressjm/testing_paraview_env/bin/activate
cd Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/Visualization_Vignettes/ \
  --test_type ParaView \
  --paraview_version 5.13.1 \
  --machine_name <machine-name>
```

**GPU Options:**

| GPU Type | `srun` Flag (`<gpu-flag>`) | Python Flag (`<machine-name>`) |
| :--- | :--- | :--- |
| v100 | `--gres=gpu:v100:1` | `ibex-egl-v100` |
| rtx2080ti | `--gres=gpu:rtx2080ti:1` | `ibex-egl-rtx2080ti` |
| p6000 | `--gres=gpu:p6000:1` | `ibex-egl-p6000` |
| p100 | `--gres=gpu:p100:1` | `ibex-egl-p100` |
| gtx1080ti | `--gres=gpu:gtx1080ti:1`| `ibex-egl-gtx1080ti` |
| a100 | `--gres=gpu:a100:1` | `ibex-egl-a100` |

#### Ibex GPU (VisIt)
```bash
# 1. Load modules
module load visit/3.4.1
module load ffmpeg

# 2. Request an interactive job (any GPU)
srun --gres=gpu:1 --cpus-per-task=12 --ntasks=1 --time=00:40:00 --mem=100G --pty /bin/bash

# 3. Once in the job, run the tests
source /ibex/scratch/kressjm/testing_visit_env/bin/activate
cd Visualization_Vignettes/Testing
python test_suite.py /ibex/scratch/kressjm/Visualization_Vignettes/ \
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

# 2. Request an interactive job (choose workq or ppn)
#    For workq nodes:
srun --cpus-per-task=32 --ntasks=2 -p workq --time=00:40:00 --mem=200G -A k01 --pty /bin/bash
#    For PPN nodes:
srun --cpus-per-task=32 --ntasks=2 -p ppn --time=00:40:00 --mem=200G -A k01 --pty /bin/bash

# 3. Once in the job, run the tests (use the matching machine_name)
source /scratch/kressjm/testing_paraview_env/bin/activate
cd Visualization_Vignettes/Testing

#    If on workq:
python test_suite.py /scratch/kressjm/testing/Visualization_Vignettes/ \
  --test_type ParaView \
  --paraview_version 5.13.1 \
  --machine_name shaheen3-cpu \
  --non_gpu_machine

#    If on PPN:
python test_suite.py /scratch/kressjm/testing/Visualization_Vignettes/ \
  --test_type ParaView \
  --paraview_version 5.13.1 \
  --machine_name shaheen3-mesa-ppn \
  --non_gpu_machine
```

#### Shaheen3 CPU (VisIt)
```bash
# 1. Load module
module load visit/3.4.1

# 2. Request an interactive job (choose workq or ppn)
#    For workq nodes:
srun --cpus-per-task=32 --ntasks=2 -p workq --time=00:40:00 --mem=300G -A k01 --pty /bin/bash
#    For PPN nodes:
srun --cpus-per-task=32 --ntasks=2 -p ppn --time=00:40:00 --mem=300G -A k01 --pty /bin/bash

# 3. Once in the job, run the tests (use the matching machine_name)
source /scratch/kressjm/testing_visit_env/bin/activate
cd Visualization_Vignettes/Testing

#    If on workq:
python3 test_suite.py /scratch/kressjm/testing/Visualization_Vignettes/ \
  --test_type VisIt \
  --visit_version 3.4.1 \
  --machine_name shaheen3-cpu

#    If on PPN:
python3 test_suite.py /scratch/kressjm/testing/Visualization_Vignettes/ \
  --test_type VisIt \
  --visit_version 3.4.1 \
  --machine_name shaheen3-ppn
```

#### Shaheen3 GPU (ParaView)
```bash
# 1. Load module
module load paraview/5.13.1-egl

# 2. Request an interactive GPU job
srun --cpus-per-task=32 --ntasks=1 -p ppn -G 1 --time=00:40:00 --mem=200G -A k01 --pty /bin/bash

# 3. Once in the job, run the tests
source /scratch/kressjm/testing_paraview_gpu_env/bin/activate
cd Visualization_Vignettes/Testing
python test_suite.py /scratch/kressjm/testing/Visualization_Vignettes/ \
  --test_type ParaView \
  --paraview_version 5.13.1 \
  --machine_name shaheen3-mesa-ppn-gpu
```

---

## Continuous Integration

A **GitHub Actions workflow** is set up to run automatically on each commit to this repository. This workflow runs the `test_suite.py` for both ParaView and VisIt. If all tests pass, the workflow run will be marked as successful (with a green check).

Artifacts from these runs are saved for review. Please note: **GitHub artifacts are temporary and automatically expire** (the default is 90 days).

### How to Find Build Artifacts

Unlike GitLab, GitHub does not have a single, permanent URL for artifacts. Instead, artifacts are attached to the specific workflow run that created them.

1.  Click the **"Actions"** tab at the top of the repository.
2.  Click on the specific **workflow run** you want to inspect.
3.  On the summary page for that run, scroll to the bottom to find the **"Artifacts"** section.
4.  You can download the files (usually as a `.zip` archive) from there.