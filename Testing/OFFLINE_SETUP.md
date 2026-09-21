# Running the suite on a machine with no network

Some of our machines are offline, so everything has to be built somewhere
connected and copied over: the Python environment, the datasets, and the
repository. All three are portable if you prepare them the right way, and one
of them is not portable at all if you prepare it the obvious way.

Everything below was verified on this workstation rather than assumed.

---

## What the suite needs at run time

Nothing from the network. The harness and every vignette were checked for
`urllib`, `requests`, `curl` and `wget`; there are no calls. The only network
steps are the ones in this document, and they all happen on the connected
machine.

Five Python packages, and they are all load-bearing:

| Package | What stops working without it |
| :--- | :--- |
| `pillow` | the image gate. No image comparison runs at all. |
| `psutil` | per-vignette peak memory and whole-tree CPU. `metrics.py` omits the figure rather than recording a wrong one, so every run is missing a gate. |
| `pandas`, `numpy`, `matplotlib` | the metric history and its plots |

---

## 1. The Python environment: build a wheelhouse, not a venv

**Do not copy a virtual environment.** A venv records absolute paths in
`bin/activate` and in every console script's shebang, so one built at
`/home/you/env` does not work at `/scratch/you/env`, and one built on your
workstation does not work on a compute node with a different Python. It will
half-work, which is worse than failing.

Copy **wheels** instead, and build the venv on the target machine from them.

### On a connected machine

```bash
cd Visualization_Vignettes/Testing
./make_offline_bundle.sh                 # writes ../offline_bundle/wheelhouse
```

That is 15 wheels and about 52 MB. It is the same set for both suites; the
ParaView and VisIt environments differ only in which interpreter they are
built against, and the wheels are the same.

### On the offline machine

```bash
module load paraview/6.1.0               # or visit/3.4.1, see the runbooks below
python3 -m venv $SCRATCH/testing_paraview_env
source $SCRATCH/testing_paraview_env/bin/activate
pip install --no-index --find-links=/path/to/wheelhouse \
    pandas numpy pillow matplotlib psutil
```

`--no-index` is the important flag: without it pip will try to reach PyPI,
fail, and the error will be about a timeout rather than about a missing
wheel.

### The one thing that can go wrong

Wheels are built per Python version and per platform. `cp312` wheels do not
install into a Python 3.10. If the offline machine's `python3 --version`
differs from the connected one, build the wheelhouse with matching
constraints:

```bash
pip download -d wheelhouse --only-binary=:all: \
    --python-version 3.10 --platform manylinux2014_x86_64 \
    pandas numpy pillow matplotlib psutil
```

`make_offline_bundle.sh --python-version 3.10` does the same thing.

Check the target's Python first. On a cluster it is usually the one the
visualization module puts on `PATH`, not the system one:

```bash
module load paraview/6.1.0 && python3 --version
```

---

## 2. The data

`data/fetchData.sh` downloads a 4.3 GB archive that extracts to about 5.7 GB.
Run it on the connected machine and copy the extracted files, not the archive.

| Path | Size | Needed by |
| :--- | ---: | :--- |
| `data/varying_data/` | 19 MB | ex05, ex07, ex10, ex11, ex12 (both suites) |
| `data/noise.silo` | 11 MB | ex00-ex04 (both suites) |
| `data/varying.visit` | 4 KB | the legacy index |
| `data/currentRainfall.silo` | 145 MB | **ex06 only** |
| `data/cyclone-chapala-2015-11-02_00-00-00-mb/` + `.vtm` | 5.6 GB | **ex06 only** |

The first three are committed, so a `git clone` or a copy of the repository
already has them. Only ex06's two datasets have to be fetched and copied, and
if 5.7 GB is impractical, leave them behind: the preflight reports their
absence as a warning rather than an error and the other twelve vignettes run
normally.

```bash
# connected machine
cd Visualization_Vignettes/data && ./fetchData.sh
rsync -a --exclude 'KAUST_Visualization_Vignettes_Large_Data.zip' \
      --exclude 'topologies/' --exclude 'varying_series_xml/' \
      data/ offline-host:/scratch/you/Visualization_Vignettes/data/
```

The two excluded directories are **generated**, and copying them is the one
thing that will bite you silently. See below.

---

## 3. The generated fixtures: build them on the target, never copy them

Four inputs are produced by a tool rather than shipped, and none of them
announces a mismatch when it is wrong:

| Fixture | Locked to |
| :--- | :--- |
| `data/topologies/` | a ParaView major.minor |
| `data/varying_series_xml/` | its source series |
| `ParaView_Vignettes/ex11_pvStateVerification/ex11_state.pvsm` | a ParaView major.minor |
| `VisIt_Vignettes/ex11_visitStateVerification/ex11_visit.session` and `ex11_series.visit` | a VisIt version, and absolute paths |

An AMR hierarchy written by ParaView 6.1.0 opens under 6.0.1 and quietly reads
216 points where 842 were written. No error, no warning: ex09 simply reports
different numbers and fails its numeric gate for a reason that looks like a
regression. This is why they are gitignored and why the suite refuses to start
when they are stale.

Building them needs `pvbatch` or `visit` on the target machine, and no network:

```bash
cd $SCRATCH/Visualization_Vignettes
python3 Testing/prepare_machine.py           # build what is missing or stale
python3 Testing/prepare_machine.py --check   # verify only
```

Exit codes: 0 ready, 1 a generated fixture is missing or stale, 3 only ex06's
datasets are absent.

---

## 4. Copying the repository

```bash
git clone --depth 1 <url> Visualization_Vignettes    # on the connected machine
rsync -a --exclude '.git' --exclude '*/output/' \
      --exclude 'data/topologies/' --exclude 'data/varying_series_xml/' \
      --exclude 'data/*.zip' \
      Visualization_Vignettes/ offline-host:/scratch/you/Visualization_Vignettes/
```

Keep `*/Testing/Baseline/` and `*/Testing/performance_metrics_*.json`: those
are the blessed baselines and the committed history, and without them every
image gate reports NO BASELINE and the performance gate has nothing to compare
against.

---

## 5. Checklist before the first run

```bash
cd $SCRATCH/Visualization_Vignettes
python3 Testing/prepare_machine.py --check    # 0 or 3, not 1
source $SCRATCH/testing_paraview_env/bin/activate
python -c "import pandas, numpy, PIL, matplotlib, psutil; print('deps ok')"
which pvbatch || echo "load the ParaView module first"
```

---

# Cluster runbooks

The module strings below are the versions in use as of this writing. Confirm
with `module avail paraview` / `module avail visit`, and make
`--paraview_version` / `--visit_version` match what you loaded: that string is
recorded inside every metric record and is how a later reader knows which
build produced a number.

`--machine_name` names a **configuration**, not a run. One history file per
machine and rendering configuration, which is why `ibex-cpu` and
`ibex-egl-a100` are separate. Keep them stable: the performance gate needs two
runs under the same name before it can say anything.

## Shaheen III, CPU (`workq`)

```bash
cd $SCRATCH/Visualization_Vignettes

# --- ParaView -------------------------------------------------------------
source ParaView_Vignettes/MODULES.sh          # loads the -mesa variant
srun --cpus-per-task=32 --ntasks=2 -p workq --time=00:40:00 \
     --mem=200G -A <account> --pty /bin/bash
source $SCRATCH/testing_paraview_env/bin/activate
cd Testing
python3 prepare_machine.py --check
python test_suite.py ../ --test_type ParaView --paraview_version 6.1.0 \
  --machine_name shaheen3-cpu --machine shaheen --launcher srun \
  --image-tolerance 0.005 --non_gpu_machine \
  --run-id shaheen3-cpu-$(date +%Y-%m-%d) \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800

# --- VisIt ----------------------------------------------------------------
source VisIt_Vignettes/MODULES.sh             # loads visit/3.4.1
source $SCRATCH/testing_visit_env/bin/activate
python test_suite.py ../ --test_type VisIt --visit_version 3.4.1 \
  --machine_name shaheen3-visit-cpu --machine shaheen --launcher srun \
  --nodes 1 --ranks 8 --image-tolerance 0.005 --non_gpu_machine \
  --run-id shaheen3-visit-cpu-$(date +%Y-%m-%d) --timeout 1800
```

## Ibex, CPU

```bash
cd $SCRATCH/Visualization_Vignettes

# --- ParaView -------------------------------------------------------------
module load paraview/6.0.1-gnu-mesa
srun --cpus-per-task=12 --ntasks=1 --time=00:40:00 --mem=100G --pty /bin/bash
source $SCRATCH/testing_paraview_env/bin/activate
cd Testing
python3 prepare_machine.py                    # 6.0.1 fixtures, not 6.1.0's
python test_suite.py ../ --test_type ParaView --paraview_version 6.0.1 \
  --machine_name ibex-cpu --machine ibex --image-tolerance 0.005 \
  --non_gpu_machine --run-id ibex-cpu-$(date +%Y-%m-%d) \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800

# --- VisIt ----------------------------------------------------------------
module load visit/3.4.1 ffmpeg
source $SCRATCH/testing_visit_env/bin/activate
python test_suite.py ../ --test_type VisIt --visit_version 3.4.1 \
  --machine_name ibex-cpu --machine ibex --nodes 1 --ranks 8 \
  --image-tolerance 0.005 --non_gpu_machine \
  --run-id ibex-visit-cpu-$(date +%Y-%m-%d) --timeout 1800
```

## Ibex, GPU

One configuration per GPU type, because that is what the history files
already distinguish.

| GPU | `srun` flag | `--machine_name` |
| :--- | :--- | :--- |
| v100 | `--gres=gpu:v100:1` | `ibex-egl-v100` |
| a100 | `--gres=gpu:a100:1` | `ibex-egl-a100` |
| rtx2080ti | `--gres=gpu:rtx2080ti:1` | `ibex-egl-rtx2080ti` |
| p6000 | `--gres=gpu:p6000:1` | `ibex-egl-p6000` |
| p100 | `--gres=gpu:p100:1` | `ibex-egl-p100` |
| gtx1080ti | `--gres=gpu:gtx1080ti:1` | `ibex-egl-gtx1080ti` |

```bash
module load paraview/6.0.1-gnu-egl
srun <gpu-flag> --cpus-per-task=12 --ntasks=1 --time=00:40:00 \
     --mem=100G --pty /bin/bash
source $SCRATCH/testing_paraview_env/bin/activate
cd $SCRATCH/Visualization_Vignettes/Testing
python3 prepare_machine.py --check
python test_suite.py ../ --test_type ParaView --paraview_version 6.0.1 \
  --machine_name <machine-name> --machine ibex --image-tolerance 0.005 \
  --run-id <machine-name>-$(date +%Y-%m-%d) \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800

# VisIt on a GPU node
module load visit/3.4.1 ffmpeg
source $SCRATCH/testing_visit_env/bin/activate
python test_suite.py ../ --test_type VisIt --visit_version 3.4.1 \
  --machine_name ibex-gpu --machine ibex --nodes 1 --ranks 8 \
  --image-tolerance 0.005 --run-id ibex-visit-gpu-$(date +%Y-%m-%d) \
  --timeout 1800
```

---

## Things to expect on a cluster, and not be alarmed by

* **ex11 (ParaView) needs a display.** It exists to exercise the on-display
  path, so it must not be forced offscreen. Run it separately under
  `xvfb-run -a --server-args="-screen 0 1280x1280x24"` with `--no-offscreen`
  and the same `--run-id`. If `xvfb` is not on the compute nodes, skip it
  there and keep it as a local gate. VisIt's ex11 only warns without a
  display, and its frames are bit-identical either way.
* **ex06 needs 62 GB and about 190 seconds** at one rank in ParaView, and
  36 GB in VisIt. It is half the suite's wall clock on its own.
* **VisIt at 8 ranks matches its baselines.** Measured: 27 of 29 images are
  bit-identical at 8 ranks against 1-rank baselines, ex04 differs by 0.0134%,
  and ex06 is blessed at 8 ranks precisely so this case is the one that
  passes.
* **`--image-tolerance 0.005`** covers GPU GLX, Mesa llvmpipe and EGL on one
  baseline set. The widest legitimate cross-backend difference measured
  anywhere in the suite is 0.39%.
* **`any_tests_failed` can be `true` while the suite exits 0.** The five
  correctness gates feed the exit code; the performance gate does not.

## Recording, once it works

Use `--no-metrics` while you are getting a site working. When the run is
green and repeatable, run it once more without it, tagged with `--run-id`,
and commit `*/Testing/performance_metrics_<machine_name>.json`. That is the
long-term record, not a log of every attempt. `manage_metrics.py --remove-run
<id> -y` undoes one precisely.
