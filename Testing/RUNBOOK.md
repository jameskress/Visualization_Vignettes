# Running the vignette suite: every machine, both tools

One document for the workstation, Ibex, Shaheen `workq` and Shaheen `ppn`,
for ParaView and VisIt, online and air-gapped.

If you read nothing else, read section 1. Every failure worth having is in
the setup, not the vignettes.

- [1. The four things every machine needs](#1-the-four-things-every-machine-needs)
- [2. The Python environment](#2-the-python-environment)
- [3. Data and generated fixtures](#3-data-and-generated-fixtures)
- [4. Local workstation](#4-local-workstation)
- [5. Ibex](#5-ibex)
- [6. Shaheen III, CPU (`workq`)](#6-shaheen-iii-cpu-workq)
- [7. Shaheen III, GPU (`ppn`)](#7-shaheen-iii-gpu-ppn)
- [8. Air-gapped machines](#8-air-gapped-machines)
- [9. Recording a run](#9-recording-a-run)
- [10. What to expect the first time](#10-what-to-expect-the-first-time)
- [11. Troubleshooting](#11-troubleshooting)

---

## 1. The four things every machine needs

In this order. Each one fails loudly if you skip it, which is the point.

| | What | Check |
| :--- | :--- | :--- |
| 1 | The repository, on the right branch | `git log --oneline -1` |
| 2 | A Python **3.9 or newer** venv with five packages | `python -c "import pandas, numpy, PIL, matplotlib, psutil"` |
| 3 | The data | `ls data/noise.silo data/varying_data` |
| 4 | The generated fixtures | `python3 Testing/prepare_machine.py --check` |

Step 4 is the gate. `test_suite.py` runs it as a preflight and refuses to
start if it fails, because every way a stale fixture goes wrong looks like a
regression in a vignette rather than a setup problem.

Exit codes from `--check`:

| Code | Meaning | Do |
| ---: | :--- | :--- |
| 0 | ready | run |
| 3 | only ex06's 5.7 GB data is absent | run; ex06 reports SKIPPED |
| 1 | a fixture is missing or stale | `python3 Testing/prepare_machine.py` (add `--force` after a module change) |

---

## 2. The Python environment

**The one thing people get wrong.** The wheels must match the `python3` that
creates the venv. That is a plain Python, **not** ParaView's and **not**
VisIt's. `test_suite.py` imports pandas, numpy, PIL, matplotlib and psutil;
the vignettes run inside `pvbatch` or the VisIt CLI and import only the
standard library, deliberately, so that one `vignette_common.py` works under
three interpreters.

For reference, the bundled interpreters are ParaView 6.1.0 → Python 3.12 and
VisIt 3.4.2 → Python 3.9. Neither is the one you build the venv with.

**Check before you build anything:**

```bash
python3 --version
```

Shaheen's login nodes answer `3.6.15`. That is too old: pip resolves to
pandas 1.1.5 and matplotlib 3.3.4 from 2020 and nothing tells you. Load a
newer module first:

```bash
module avail python
module load python/<newer>
python3 --version          # confirm 3.9+
```

Then, one venv per tool so the two suites cannot disturb each other:

```bash
python3 -m venv $SCRATCH/testing_paraview_env
source $SCRATCH/testing_paraview_env/bin/activate
pip install pandas numpy pillow matplotlib psutil
python -c "import pandas, numpy, PIL, matplotlib, psutil; print('deps ok')"
deactivate

python3 -m venv $SCRATCH/testing_visit_env
source $SCRATCH/testing_visit_env/bin/activate
pip install pandas numpy pillow matplotlib psutil
deactivate
```

A venv is not relocatable: it hard-codes its own path and interpreter into
`bin/activate` and every console script. Build it on the machine that will
use it. For machines with no network, see section 8.

Without `pillow` the image gate does not run at all. Without `psutil` the
memory and CPU metrics are omitted rather than recorded wrongly. Both are
silent losses of a gate, which is why they are not optional.

---

## 3. Data and generated fixtures

**Shipped with the repository** (about 30 MB, already there after a clone):
`data/noise.silo`, `data/varying_data/`, `data/varying.visit`.

**Fetched once**, 4.3 GB download extracting to 5.7 GB, needed only by ex06:

```bash
cd data && bash fetchData.sh
```

Skip it if you do not want ex06. It will report SKIPPED and the other twelve
run normally, and `--check` returns 3 rather than 1.

**Generated per machine**, never committed, because each is version-locked or
path-locked and none announces a mismatch:

```bash
module load paraview        # and visit, if you want both prepared
python3 Testing/prepare_machine.py
```

That builds `data/topologies/`, `data/varying_series_xml/`,
`ex11_state.pvsm` (ParaView) and `ex11_visit.session` + `ex11_series.visit`
(VisIt). A tool that is not loaded is skipped with a note, not an error, so
running it with only one module loaded is fine; run it again after loading
the other.

The `No matching writer found for extension: vth` line during generation is
expected. ParaView 6.1 dropped that writer, the generator falls through to
`.vthb`, and the manifest records what it actually wrote.

---

## 4. Local workstation

```bash
export PARAVIEW_PATH=$HOME/packages/ParaView-6.1.0-MPI-Linux-Python3.12-x86_64/bin
source ~/testing_paraview_env/bin/activate
cd Testing
python test_suite.py ../ --test_type ParaView --paraview_version 6.1.0 \
  --machine_name $(hostname) \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800
```

ex11 separately, because it verifies the on-display path a GUI user takes and
fails when forced offscreen, and `--no-offscreen` applies to the whole
invocation:

```bash
XVFB_SCREEN=1280x1280x24 ../Scripts/run_with_display.sh \
  python test_suite.py ../ --test_type ParaView --paraview_version 6.1.0 \
    --machine_name $(hostname) --test_number 11 --no-offscreen --timeout 1800
```

VisIt, same split:

```bash
export VISIT_PATH=$HOME/packages/visit3_4_2.linux-x86_64/bin
source ~/testing_visit_env/bin/activate
python test_suite.py ../ --test_type VisIt --visit_version 3.4.2 \
  --machine_name $(hostname) \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800

XVFB_SCREEN=1024x1024x24 ../Scripts/run_with_display.sh \
  python test_suite.py ../ --test_type VisIt --visit_version 3.4.2 \
    --machine_name $(hostname) --test_number 11 --timeout 1800
```

No `--image-tolerance` locally: the baselines were blessed on this hardware,
so the default 0.001 is the right gate. Everywhere else, see section 10.

About 6 minutes per suite, of which ex06 is half.

**A record is only as quiet as the machine.** The 21 Oct 2026 workstation
record took three attempts. With a 24-day-old Omniverse `kit` process holding
three cores, every ParaView vignette came out 3 s slower; removed with
`manage_metrics.py --remove-run <id> -y` (exact; `git diff` shows what went).
With `kit` stopped but the Claude desktop app open, still 40 to 120% slower on
the quick vignettes: its GPU process shares the display GPU, and pausing it
alone cut GLX context creation from 1.36 s to 0.9 s. With that app and the VNC
viewer closed, from a plain terminal (load 1.5): every gate passes, ex06 is
faster than September (185 s against 192 s) and the quick vignettes carry about
one extra second each, which is what creating GLX contexts costs on this
41-day-old X session with four monitors. That is the record. VisIt renders
without X and never moved. So a clean workstation record is taken from a
plain terminal with the desktop quiet:

```bash
export PARAVIEW_PATH=$HOME/packages/ParaView-6.1.0-MPI-Linux-Python3.12-x86_64/bin
export VISIT_PATH=$HOME/packages/visit3_4_2.linux-x86_64/bin
Testing/record_local_run.sh KW61316-2026-10-21 KW61316.kaust.edu.sa
```

`record_local_run.sh` removes any earlier record with that id, runs both
suites (VisIt's ex11 under Xvfb), and prints the gate and performance
verdicts; commit the `performance_metrics_<machine>.json` files it changed.

---

## 5. Ibex

`glogin.ibex.kaust.edu.sa`. Clone into `/ibex/scratch/<username>/`.

Node sizes vary and a job with no `--constraint` has to fit the smallest:
CPU nodes run 40 cores (Skylake, Cascade Lake, the bulk of them) to 128
(Rome) and 192 (Turin). GPU nodes are tighter, because Ibex pins two cores
per node for the WekaIO filesystem, so a 32-core Skylake host with V100 or
GTX-1080Ti GPUs allocates 30.

`MODULES.sh` reads the site's current default ParaView and loads the matching
`-gnu-egl` or `-gnu-mesa` variant. Do not `module load paraview` yourself
first; it is not merely redundant, `MODULES.sh` unloads it again to read the
version number.

### Ibex, CPU

```bash
cd /ibex/scratch/$USER/Visualization_Vignettes
srun --cpus-per-task=12 --ntasks=1 --time=00:40:00 --mem=100G --pty /bin/bash

source ParaView_Vignettes/MODULES.sh              # mesa variant
source $SCRATCH/testing_paraview_env/bin/activate
cd Testing
python3 prepare_machine.py --check
python test_suite.py ../ --test_type ParaView --paraview_version <version> \
  --machine_name ibex-cpu --machine ibex --launcher mpirun \
  --image-tolerance 0.0075 --non_gpu_machine \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800
```

```bash
source VisIt_Vignettes/MODULES.sh                 # visit/3.4.2 on both Ibex and Shaheen
source $SCRATCH/testing_visit_env/bin/activate
python test_suite.py ../ --test_type VisIt --visit_version 3.4.2 \
  --machine_name ibex-cpu --machine ibex --launcher mpirun \
  --image-tolerance 0.0075 \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800
```

`--paraview_version <version>` must match what `MODULES.sh` actually loaded.
It prints it, and it is also in `$VV_PARAVIEW_MODULE`.

No `--non_gpu_machine` on the VisIt line. VisIt does not lean on the GPU the
way ParaView does, and its ex08 demands a hardware context only when given
`--hw-accel`, which the submission scripts add for a GPU queue and this does
not. Passing the flag would downgrade a real ex08 failure to a warning.

### Ibex, GPU

```bash
srun --gres=gpu:1 --cpus-per-task=12 --ntasks=1 --time=00:40:00 \
     --mem=100G --pty /bin/bash

source ParaView_Vignettes/MODULES.sh egl          # note the argument
source $SCRATCH/testing_paraview_env/bin/activate
cd Testing
python test_suite.py ../ --test_type ParaView --paraview_version <version> \
  --machine_name ibex-egl-<gpu> --machine ibex --launcher mpirun \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800
```

Name the machine after the GPU, continuing the convention already in the
history: `ibex-egl-a100`, `ibex-egl-v100`, `ibex-egl-p100`,
`ibex-egl-p6000`, `ibex-egl-rtx2080ti`, `ibex-egl-gtx1080ti`. Pin the GPU you
mean with a constraint, or you will not know which one you measured:

```bash
srun --gres=gpu:1 --constraint=a100 ...
```

No `--image-tolerance` here and no `--non_gpu_machine`: a GPU run should match
GPU-blessed baselines at the default 0.001, and ex08 asserting hardware is
exactly what you want to hear about.

### The whole suite as one batch job (25 Oct 2026)

`Testing/ibex_pv_suite.sbat` and `Testing/ibex_visit_suite.sbat`, submitted from
`Testing/`, with the same `TESTS`, `RANKS` and `EXTRA` knobs as the Shaheen ones
(default `--no-metrics`; `EXTRA="--run-id ibex-cpu-<date>"` for the one recorded
run). GPU: `sbatch --gres=gpu:1 --constraint=a100 --ntasks=4 --cpus-per-task=4
--export=ALL,VARIANT=egl,GPU=a100 ibex_pv_suite.sbat`. Never pass `--partition`
for a GPU job (Ibex refuses it) and stay within the per-GPU CPU limit (16 on
A100, 6 on V100). Account `pi-ghanis`.

They expect `$VV_IBEX_SW` (default `/ibex/scratch/$USER/hpcsaudi`) to hold
`venvs/vv` and `sw/pv-site`. Build both like this, and note the two traps:

```bash
module load python/3.11.0
python3 -m venv /ibex/scratch/$USER/hpcsaudi/venvs/vv
# The python module sets PYTHONPATH to its own site-packages, which already has
# pandas; pip then reports "already satisfied" and installs nothing into the venv.
env -u PYTHONPATH /ibex/scratch/$USER/hpcsaudi/venvs/vv/bin/python -m pip install pandas numpy pillow matplotlib psutil scipy
# numpy for ParaView's own python 3.12 (the module ships none), as on Shaheen:
pip download -d /tmp/wh --only-binary=:all: --python-version 3.12 --platform manylinux2014_x86_64 numpy
mkdir -p /ibex/scratch/$USER/hpcsaudi/sw/pv-site && cd $_ && python3 -m zipfile -e /tmp/wh/numpy-*.whl .
```

What the job scripts work around, so you do not rediscover it:

* **A batch shell has no `module` function.** `#!/bin/bash -l` is not enough on
  Ibex; the scripts `source /usr/share/Modules/init/bash`.
* **CPU nodes default to the `/sw/rl9c` module tree**, whose `paraview/6.0.1`
  entry requires `openmpi/4.1.4/gnu11.2.1-cuda11.8`, which exists only in the GPU
  tree `/sw/rl9g`. All of `/sw` is mounted everywhere, so the scripts `module
  use` the GPU tree first and everything resolves.
* **The site's ParaView 6.0.1 build segfaults in interpreter teardown after
  every script**, render window or not. The data generators and every
  single-rank vignette now end with `os._exit()`, and `run_tests.py` runs one
  rank without `mpirun` (mpirun reports an `os._exit` as "exiting improperly"
  and returns 1 over a passed vignette). Multi-rank runs still fall off the end
  of the script to release their satellites; on this build that path is untested.
* **Its AMR reader reads one level by default.** ex09 now sets
  `DefaultNumberOfLevels = 0` so every build reads all 605 cells.
* **ex09 never merges the AMR hierarchy any more.** Kitware's builds let
  MergeBlocks flatten a vtkOverlappingAMR (842 points after point merging,
  scalar max 0.333); Ibex's site build refuses it and the old "merge, else
  fall back" rule then contoured the composite directly (986 points, 0.4145),
  so the numeric baseline depended on the build. The AMR now goes to Contour
  unmerged on every build and the baseline is the unmerged numbers (re-blessed
  25 Oct 2026).
* `visit/3.4.2` is the only VisIt; `VisIt_Vignettes/MODULES.sh` loads it.

### Submission scripts instead of an interactive session

Every vignette carries `ex##_ibex_runScript.sbat`. The `RUN CONFIGURATION`
block near the top is the only part you normally edit.

```bash
sbatch ex01_pvScreenshot/ex01_ibex_runScript.sbat
```

---

## 6. Shaheen III, CPU (`workq`)

`shaheen.hpc.kaust.edu.sa`. Clone into `/scratch/<username>/`.

A `workq` node is a dual AMD EPYC 9654: **192 cores, 384 GB**, allocated
exclusively. `ntasks-per-node x cpus-per-task` must come to 192 or less or
`sbatch` refuses the job. There are no GPUs on `workq`, so the ParaView
module must be the `-mesa` variant; an `-egl` module there finds no device,
falls back to llvmpipe, and renders correctly at a hundredth of the speed
while claiming otherwise.

Setup, once:

```bash
cd /scratch/$USER
git clone https://github.com/jameskress/Visualization_Vignettes.git
cd Visualization_Vignettes
git checkout regressionTestingUpdates

cd data && bash fetchData.sh && cd ..      # only if you want ex06

module avail python && module load python/<newer>    # NOT the 3.6.15 default
export PIP_CACHE_DIR=$SCRATCH_IOPS/sw/cache/pip   # home is not for work; pip caches ~1 GB per install
python3 -m venv $SCRATCH_IOPS/sw/testing_paraview_env   # iops: the small NVMe, fast for python imports
source $SCRATCH/testing_paraview_env/bin/activate
pip install pandas numpy pillow matplotlib psutil
deactivate

module load paraview                       # 6.1.0-mesa is the default
python3 Testing/prepare_machine.py
python3 Testing/prepare_machine.py --check # expect 0, or 3 without ex06 data
```

Run:

```bash
module load python/3.10.13                 # the same python the venv was built with
source ParaView_Vignettes/MODULES.sh mesa
unset PYTHONPATH                           # see below
source $SCRATCH_IOPS/sw/testing_paraview_env/bin/activate   # AFTER the modules, so its python wins
srun --nodes=1 --ntasks=8 --cpus-per-task=24 -p workq --time=00:40:00 \
     --mem=200G -A <account> --pty /bin/bash
cd Testing
python test_suite.py ../ --test_type ParaView --paraview_version 6.1.0 \
  --machine_name shaheen3-cpu --machine shaheen --launcher srun \
  --image-tolerance 0.0075 --non_gpu_machine \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800
```

```bash
source VisIt_Vignettes/MODULES.sh          # visit/3.4.2: Shaheen III has no 3.4.1 any more,
                                           # and a bare `module load visit` does not resolve
source $SCRATCH_IOPS/sw/testing_visit_env/bin/activate
python3 Testing/prepare_machine.py --tool VisIt
python test_suite.py ../ --test_type VisIt --visit_version 3.4.2 \
  --machine_name shaheen3-cpu --machine shaheen --launcher srun \
  --nodes 1 --ranks 8 --image-tolerance 0.0075 \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800
```

As a batch job, which also runs ex11 under Xvfb afterwards (the compute nodes
have it): `Testing/shaheen_visit_suite.sbat`, submitted from `Testing/`, with
the same `TESTS`, `RANKS` (default 8, the rank count ex06 is blessed at) and
`EXTRA` knobs as the ParaView one. Inside the allocation the engine starts
as a job step (`-l srun -nn 1 -np 8`), which the harness arranges itself.

First VisIt run on Shaheen (21 Oct 2026): 11 of 13 clean. ex06's image
differs from the workstation baseline by renderer (Mesa volume rendering),
so it has its own baseline in `Testing/Baseline/shaheen3-cpu/` like the
ParaView one. ex08 recorded "engine launched" and "engine is parallel" as
metrics, which are launch facts and are now notes; its shared numeric
baseline was re-blessed on the workstation.

**Order and `PYTHONPATH` matter on Shaheen** (found 21 Oct 2026). The
`paraview/6.1.0-mesa` module prepends ParaView's own `lib/python3.12` and its
`site-packages` to `PYTHONPATH`. Any other python then imports ParaView's 3.12
standard library and dies with `AssertionError: SRE module mismatch` on the
first `import re`. `pvbatch` does not need that variable, so unset it after
`MODULES.sh`. The module also prepends ParaView's `bin`, which carries a
`python3`, so activate the venv after the modules or `python` is ParaView's.
And check the venv really holds the packages: a venv built on 2 Oct had none,
and only looked fine because the `python/3.10.13` module's own `site-packages`
was on `PYTHONPATH` at the time.

**Shaheen's ParaView has no numpy.** `paraview/6.1.0-mesa` ships without it, so
Python Annotation renders the literal text "(error)" and ex05's frames fail the
image gate at 2 to 4% (21 Oct 2026). Give ParaView's own python a user-site
copy, built for its interpreter (3.12), on the iops disk:

```bash
pip download -d /tmp/wh --only-binary=:all: --python-version 3.12 \
    --platform manylinux2014_x86_64 numpy
mkdir -p $SCRATCH_IOPS/sw/pv-site && cd $SCRATCH_IOPS/sw/pv-site && \
    python3 -m zipfile -e /tmp/wh/numpy-*.whl .
PYTHONPATH=$SCRATCH_IOPS/sw/pv-site:$PYTHONPATH pvpython -c "import numpy; print(numpy.__file__)"
```

That `PYTHONPATH` is for `pvbatch` only. Run the harness as `python -E
test_suite.py ...` so the venv python ignores the variable, and the children
inherit it. `Testing/shaheen_pv_suite.sbat` does all of this; submit it from
`Testing/` with `TESTS="5 6"` for a subset and `EXTRA="--run-id ..."` for the
one recorded run (default `--no-metrics`). Ask KSL to add numpy to the module;
until then the user site is the fix.

**pvbatch's stdout is lost on this build unless the vignette prints through
`sys.__stdout__`.** ParaView's capture helper only hands text to the real
stdout at interpreter finalisation, which `exit_vignette()` skips, so every
text gate failed on an empty `output.log` (21 Oct 2026). `VignetteContext`
now switches to the real streams for ParaView vignettes; anything else run
under `pvbatch` on Shaheen must do the same or redirect nothing and expect
no output.

**More than one rank: the vignette must end by falling off its script.**
pvbatch runs the script on rank 0 only; the satellites wait for rank 0's
normal shutdown. `os._exit()` and `sys.exit()` on rank 0 both leave them
waiting until the walltime (a 2-rank cone on Shaheen, 21 Oct 2026: rank 0
"done", rank 1 killed at the step's timeout; ex07 at 4, 8 and 16 ranks sat
for 30 minutes the same way). `exit_vignette()` now returns on a clean
verdict and keeps `os._exit()` for failures, and every `srun` launch carries
`--kill-on-bad-exit=1` so a failing rank 0 takes the satellites with it.
With that, ex07 at 16 ranks on 4 nodes ends in 5.5 s.

**The image gate ignores one-to-four-level pixel noise.** `verify.py`'s
`CHANNEL_NOISE_FLOOR` is 12 (summed RGB). Shaheen's llvmpipe differs from the
GPU baselines by that much on a few percent of shaded pixels, which failed
ex05 five frames out of five at a floor of 1; real changes are 60+ levels.

**Mesa's 3D texture limit is 2048.** ex06's volumes vanished (56% of the frame
different) because llvmpipe refuses a 2240-wide volume texture. ex06 now
resamples at 2048 on every machine, and its baseline was re-blessed on the
workstation on 21 Oct 2026. Its image gate cannot pass against the shared
baseline on another machine: the Surface LIC noise pattern is different on
every renderer. So Shaheen has its own image baseline for ex06 in
`Testing/Baseline/shaheen3-cpu/`, blessed after looking at the frame (clouds
and rain present, terrain and arrows in place):

```bash
TESTS="6" EXTRA="--no-metrics --bless --machine-baselines" sbatch shaheen_pv_suite.sbat
```

The machine directory is used automatically once it exists; every other
image is still judged against the shared baseline. The shared set belongs
to the workstation (`KW61316.kaust.edu.sa`), which is the only host that
blesses it; `--bless` from a cluster is refused unless `--bless-shared` is
given on purpose.

Both suites share `shaheen3-cpu`: it names a machine and a rendering
configuration, never a tool version. The tool version lives inside each
record, and that file has carried both since 2024.

ex11 needs a display. If the `Xvfb` binary is on the compute nodes, wrap it in
`Scripts/run_with_display.sh` as in section 4. The wrapper does not need
`xauth`, which is what `xvfb-run` fails on. If `Xvfb` is absent, leave ex11 to
the workstation and CI and say so in the run notes rather than recording a
failure.

Or submit per vignette, which is what the `.sbat` scripts are for. Set your
account in each first:

```bash
cd ParaView_Vignettes/ex01_pvScreenshot
vim ex01_shaheen_runScript.sbat          # #SBATCH --account=k##
sbatch ex01_shaheen_runScript.sbat       # from inside the vignette directory
```

Submit from inside the vignette directory. Slurm runs a copy of the script
from its spool, so the script finds `../MODULES.sh` through the submit
directory, not through its own path (fixed 21 Oct 2026; before that every
`.sbat` failed under `sbatch` with "pvbatch not found").

---

## 7. Shaheen III, GPU (`ppn`)

The `ppn` partition has the GPUs and **requires membership of the `video`
Unix group**. Check with `groups`; request it from help@hpc.kaust.edu.sa.
`ppn` nodes have fewer CPU cores than `workq`, 128 rather than 192, so size
jobs against that.

```bash
source ParaView_Vignettes/MODULES.sh egl     # paraview/6.1.0-egl
source $SCRATCH/testing_paraview_env/bin/activate
srun --nodes=1 --ntasks=4 --cpus-per-task=16 -p ppn --time=00:40:00 \
     --mem=200G -A <account> --pty /bin/bash
cd Testing
python3 prepare_machine.py --check
python test_suite.py ../ --test_type ParaView --paraview_version 6.1.0 \
  --machine_name shaheen3-ppn-gpu-L40 --machine shaheen --launcher srun \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800
```

```bash
source VisIt_Vignettes/MODULES.sh
source $SCRATCH/testing_visit_env/bin/activate
python test_suite.py ../ --test_type VisIt --visit_version 3.4.1 \
  --machine_name shaheen3-ppn --machine shaheen --launcher srun \
  --nodes 1 --ranks 8 --timeout 1800
```

Three machine names already exist in the history for Shaheen and they mean
different things. Keep using them: `shaheen3-cpu` for `workq`,
`shaheen3-mesa-ppn` for a `ppn` node deliberately running the Mesa module,
and `shaheen3-ppn-gpu-L40` for `ppn` with the GPU actually in use. The middle
one exists to separate "this node has a GPU" from "this run used it".

Run **ex08 first** on any GPU configuration. It exists to prove the backend
is what you asked for, and it takes seconds:

```bash
python test_suite.py ../ --test_type ParaView --paraview_version 6.1.0 \
  --machine_name shaheen3-ppn-gpu-L40 --test_number 8 --no-metrics
```

A pass means the rest of the run measured a GPU. A failure means everything
after it would have been llvmpipe wearing a GPU label, which is the one
result worse than no result.

---

## 8. Air-gapped machines

Nothing in the harness or the vignettes touches the network at run time. They
were checked for `urllib`, `requests`, `curl` and `wget`; there are none. All
the network steps happen on a connected machine and get copied.

**Do not copy a virtual environment.** It hard-codes its own absolute path in
`bin/activate` and in every console script's shebang, so one built at
`/home/you/env` does not work at `/scratch/you/env`, and one built against a
different interpreter does not work at all. It half-works, which is worse
than failing.

Copy wheels instead and build the venv on the target.

### Getting the repository across without GitHub

Login nodes lose outbound access often enough that this is worth knowing
before you need it, and it is also the answer when `git pull` on the cluster
hangs or returns a proxy error. A bundle is a single file holding real git
history, so the clone on the target stays a clone, with branches and the
ability to fetch again later.

On a connected machine:

```bash
cd Visualization_Vignettes
git bundle create /tmp/vignettes.bundle --all
scp /tmp/vignettes.bundle <target>:/scratch/$USER/
```

On the target, first time:

```bash
cd /scratch/$USER
git clone /scratch/$USER/vignettes.bundle Visualization_Vignettes
cd Visualization_Vignettes
git checkout regressionTestingUpdates
```

On the target, updating an existing clone:

```bash
cd /scratch/$USER/Visualization_Vignettes
git fetch /scratch/$USER/vignettes.bundle 'refs/heads/*:refs/remotes/bundle/*'
git log --oneline HEAD..bundle/regressionTestingUpdates   # look before you leap
git merge --ff-only bundle/regressionTestingUpdates
```

`git bundle verify /scratch/$USER/vignettes.bundle` on the target says whether
the file arrived intact and which commits it expects to already be present.
A bundle made with `--all` expects none, so it always applies.

**Before building one, make sure the commits you want are actually in it.**
`--all` bundles what the connected machine has, not what GitHub has. If you
committed on the workstation and never pushed, the bundle carries it and
GitHub does not; if you pushed from somewhere else, the bundle misses it.
`git log --oneline origin/<branch>..HEAD` on the connected machine tells you
which way round you are.


### On a connected machine

Match the Python version of the **target's** venv interpreter, not this one:

```bash
cd Visualization_Vignettes/Testing
./make_offline_bundle.sh --python-version 3.11 --platform manylinux2014_x86_64
```

It refuses to run under Python older than 3.9 without an explicit
`--python-version`, because that silently produces 2020-era pandas and
matplotlib. Roughly 15 wheels and 52 MB. Check the target first:

```bash
# on the target, after loading whatever python module you will use
python3 --version
```

### Data

`fetchData.sh` downloads 4.3 GB and extracts 5.7 GB. Run it on the connected
machine and copy the **extracted** files, not the archive:

```bash
cd Visualization_Vignettes/data && bash fetchData.sh
rsync -a --exclude 'KAUST_Visualization_Vignettes_Large_Data.zip' \
  data/ <target>:/scratch/$USER/Visualization_Vignettes/data/
```

| Path | Size | Needed by |
| :--- | ---: | :--- |
| `data/varying_data/` | 19 MB | ex05, ex07, ex10, ex11, ex12, both suites |
| `data/noise.silo` | 11 MB | ex00-ex04, both suites |
| `data/currentRainfall.silo` | 145 MB | **ex06 only** |
| `data/cyclone-…-mb/` + `.vtm` | 5.6 GB | **ex06 only** |

The first two are committed, so a clone already has them.

### On the offline machine

```bash
module load python/<version>
python3 -m venv $SCRATCH/testing_paraview_env
source $SCRATCH/testing_paraview_env/bin/activate
pip install --no-index --find-links=/path/to/offline_bundle/wheelhouse \
    pandas numpy pillow matplotlib psutil
python -c "import pandas, numpy, PIL, matplotlib, psutil; print('deps ok')"
```

`--no-index` is the flag that matters. Without it pip reaches for PyPI, fails
on a timeout, and the error is about the network rather than about a missing
wheel.

**Never copy the generated fixtures.** They are version-locked and
path-locked and none of them announces a mismatch: an AMR hierarchy written
by 6.1.0 opens under 6.0.1 and quietly reads 216 points where 842 were
written, and a VisIt `.session` from the wrong version restores with plots
silently missing. Build them on the target:

```bash
module load paraview
python3 Testing/prepare_machine.py
```

### Shaheen GPU, offline

Same as section 7, with the environment built as above. The order matters:

```bash
# 1. connected machine
./make_offline_bundle.sh --python-version <target's>
cd data && bash fetchData.sh
rsync the repo + offline_bundle + extracted data to /scratch on Shaheen

# 2. Shaheen login node
module load python/<version>
python3 -m venv $SCRATCH/testing_paraview_env
source $SCRATCH/testing_paraview_env/bin/activate
pip install --no-index --find-links=$SCRATCH/offline_bundle/wheelhouse \
    pandas numpy pillow matplotlib psutil
module load paraview/6.1.0-egl
python3 Testing/prepare_machine.py          # builds fixtures with THIS build
python3 Testing/prepare_machine.py --check  # must be 0 or 3

# 3. a ppn allocation
groups | grep video                         # or none of this works
srun --nodes=1 --ntasks=4 --cpus-per-task=16 -p ppn --time=00:40:00 \
     --mem=200G -A <account> --pty /bin/bash
cd Testing
python test_suite.py ../ --test_type ParaView --paraview_version 6.1.0 \
  --machine_name shaheen3-ppn-gpu-L40 --machine shaheen --launcher srun \
  --test_number 8 --no-metrics              # prove the backend first
python test_suite.py ../ --test_type ParaView --paraview_version 6.1.0 \
  --machine_name shaheen3-ppn-gpu-L40 --machine shaheen --launcher srun \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800
```

Generate the fixtures with the same module variant you will run under. They
are keyed on ParaView major.minor, so `-egl` and `-mesa` of the same version
are interchangeable, but 6.0.1 and 6.1.0 are not.

---

## 9. Recording a run

`performance_metrics_<machine>.json` is tracked in git and is the long-term
record. It is not a log of everything you ran.

- **`--no-metrics` on every debugging, blessing and experimenting run.** It
  compares exactly as usual and appends nothing.
- **One recorded run per configuration, at the end**, once the code is in the
  state you intend to commit. Tag it with `--run-id` so it can be undone as a
  unit: `--run-id shaheen3-cpu-$(date +%Y-%m-%d)`.
- **`--machine_name` names a machine and a rendering configuration, never a
  tool version.** Both tool versions belong in the same file; the version is
  recorded inside each record.

Undo a recorded run:

```bash
python3 Testing/manage_metrics.py --list-runs
python3 Testing/manage_metrics.py --remove-run <run-id> -y
```

---

## 10. What to expect the first time

**Image tolerance.** The baselines were blessed on a GPU. Mesa llvmpipe
differs from them by anti-aliasing along contour edges. An early five-vignette
sample put the worst case at 0.39% and 0.005 was the recommendation. Running
the whole suite under llvmpipe later found two the sample did not speak for,
both stable across two ParaView versions:

| Vignette | Difference | What it is |
| :--- | ---: | :--- |
| ex02 frame 1 | 0.5042% | Over 0.005 by four ten-thousandths of a percent |
| ex05, five frames | 1.80% to 3.55% | The cycle and time annotation, ie. font rasterization |

So pass `--image-tolerance 0.0075` on any software-rendered run, and leave the
default 0.001 on a GPU. **Expect ex05 to fail anyway on a software renderer.**
No honest tolerance covers a different font engine while still catching a real
change, which is why CI leaves ex05 out of its list entirely. On the cluster,
run it, look at the diff, and record it as a known text difference rather than
widening the gate to hide it. Section 5a of `LOCAL_VALIDATION.md` has the
measurements.

**Rank count.** Every ParaView baseline was blessed at one rank and ParaView
above one rank has never been exercised on a cluster. The submission scripts
run ex04, ex05 and ex07 at 4 ranks and ex06 at 8. Expect partition-boundary
differences in `contour_points` and integrated quantities. That is real
information, not a bug. VisIt is already measured: 27 of 30 images
bit-identical at 8 ranks, with ex04 differing by 0.0134% because
integral-curve advection is partition-sensitive, and ex06 blessed at 8 ranks
because translucent geometry composites in a partition-dependent order.

**So split the first cluster run by rank count, not by suite:**

| Phase | Vignettes | Ranks | Why |
| :--- | :--- | ---: | :--- |
| 1 | ex00-ex03, ex08-ex12 | 1 | Same as the baselines. A difference here is environment, nothing else. |
| 2 | ex04, ex05, ex07 | 4 | First multi-rank ParaView. |
| 3 | ex06 | 8 | Biggest and slowest, and skips outright without its data. |

Run phase 1 with `--no-metrics` until it is clean. If phase 1 is messy, the
problem is setup and phase 2 would only bury it.

**Version differences are reported, not failed.** Two runs at the same tool
version with a metric more than 10% apart is a regression and fails. Two runs
at different versions get printed with both version numbers and recorded
under `version_comparisons`, without failing, because the newest record is
often deliberately the older build.

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `FAIL n generated fixture(s) missing or stale` | fixtures not built, or built by a different ParaView major.minor | `python3 Testing/prepare_machine.py`, add `--force` after a module change |
| `ParaView : unknown` | the version probe could not read the build | fixed as of `d9d6c8c`; `pvbatch --version` is tried first and unknown no longer counts as stale |
| `No matching writer found for extension: vth` | ParaView 6.1 dropped that writer | expected, the generator falls through to `.vthb` |
| Ancient pandas/matplotlib in the wheelhouse | built under the login node's Python 3.6 | `module load python/<newer>` first; the script now refuses below 3.9 |
| Every image fails by a fraction of a percent | software rendering against GPU-blessed baselines | `--image-tolerance 0.0075` |
| Only ex05 fails, by 1.8% to 3.5% | font rasterization differs from the GPU baseline | expected on a software renderer, see section 10 |
| ex08 fails on a GPU queue | the module variant is Mesa, or EGL found no device | check `$VV_PARAVIEW_MODULE` and that you are on `ppn` with the `video` group |
| ex11 fails | forced offscreen | run it alone under `Scripts/run_with_display.sh` with `--no-offscreen` |
| ex06 reports SKIPPED | its 5.7 GB is not on this machine | expected; `cd data && bash fetchData.sh` if you want it |
| ex06 fails its image gate by ~70% where its data is absent (CI) | `ctx.skip()` returned instead of exiting, so the vignette rendered an empty scene and overwrote the skipped verdict | fixed 21 Oct 2026: `skip()` ends the process with `sys.exit(0)` and a skipped status is sticky in `write_results()`; see AGENTS.md |
| `sbatch` refuses the job | `ntasks-per-node x cpus-per-task` exceeds the node | 192 on Shaheen `workq`, 128 on `ppn`, as low as 30 on an Ibex GPU node |
| Suite refuses to start | preflight failed | read what `--check` said; `--skip-preflight` exists but every way a stale fixture fails looks like a regression |
| A venv copied from another machine does not work | venvs are not relocatable | rebuild it from the wheelhouse on this machine |
