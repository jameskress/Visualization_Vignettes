# Running the suites on an offline GPU machine

Some machines have no network and cannot see the filesystems of the machine
you prepare on, so a folder is carried over to them. This directory makes that
folder, and this file is the sequence to run once you are on the target.
Nothing below touches the network.

## 1. On a connected machine: build the handoff folder

```bash
cd /scratch/$USER/<clone>/Testing/gpu_handoff
bash stage_handoff.sh /scratch/$USER/vv_gpu_handoff        # ~6 GB, five minutes
```

It assembles, under that path:

| item | what | why |
|---|---|---|
| `vignettes.bundle` | git bundle of every branch on the connected clone | real history on the target; `git clone` it, no GitHub needed |
| `Visualization_Vignettes/` | a clone of that bundle, on master, with `data/` filled | ready to run; the bundle is the fallback and the way to update later |
| `data_large/` | ex06's 5.7 GB (cyclone multiblock, rainfall silo) | fetched here because the target cannot |
| `wheelhouse_<arch>_py3.10`, `_py3.11`, `_py3.12` | the five Python dependencies as wheels, per interpreter, for `x86_64` and `aarch64` | `uname -m` on the target picks the architecture: x86 wheels do not run on ARM64 |
| `pv_numpy_<arch>_py3.10`, `_py3.12` | numpy unpacked for ParaView's own Python, both architectures | a site ParaView module may carry its own Python without numpy |

Copy the whole folder. The paths below assume it lands at
`$SCRATCH/vv_gpu_handoff` on the target.

## What to check on the target first

- `uname -m`: `aarch64` means only the `aarch64` wheelhouses apply.
- `module avail python paraview visit`: which Python versions exist (use one
  that has a wheelhouse), the ParaView module's exact name, and whether there
  is a VisIt module at all.
- `module show <ParaView module>`: whether it prepends its own Python to
  `PYTHONPATH` (the suite scripts' pvbatch wrapper handles that) and whether
  it sets `VTK_DEFAULT_OPENGL_WINDOW`. A module can default to OSMesa on a GPU
  node, and OSMesa may not even be installed there.
- Then the backend probe, before anything else: does EGL find the GPU?

```bash
module load <ParaView module>
export VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow
cd $SCRATCH/vv_gpu_handoff/Visualization_Vignettes/ParaView_Vignettes/ex08_pvBackendCheck
srun --gres=gpu:1 -n 1 -t 00:05:00 pvbatch --force-offscreen-rendering ex08_pvBackendCheck.py --machine shaheen
```

"classified as: hardware" means run everything below with `VARIANT=egl`. Only
if EGL cannot create a context, fall back to `VARIANT=mesa`, and only if the
OSMesa library is actually present.

## 2. On the target: first time

Every value in angle brackets must be replaced before the line is pasted.

```bash
KIT=$SCRATCH/vv_gpu_handoff
cd $KIT
git -C Visualization_Vignettes log --oneline -1        # must print a commit; if empty, the .git folder did not survive the copy
git -C Visualization_Vignettes bundle verify $KIT/vignettes.bundle

# Python. A site Python module may put its own site-packages on PYTHONPATH;
# then pip finds numpy there, says "already satisfied", and installs nothing
# into the venv. The suite scripts unset PYTHONPATH, so the job would fail.
module load python/<3.10|3.11|3.12>
unset PYTHONPATH
python3 -m venv $SCRATCH/sw/testing_paraview_env
$SCRATCH/sw/testing_paraview_env/bin/python -m pip install --ignore-installed --no-index \
    --find-links=$KIT/wheelhouse_$(uname -m)_py3.<minor> pandas numpy pillow matplotlib psutil
env -u PYTHONPATH $SCRATCH/sw/testing_paraview_env/bin/python -c "import pandas, numpy, dateutil, PIL, matplotlib, psutil; print('ok')"

# ParaView's own Python: does it have numpy?
module load <ParaView module>
pvpython -c "import numpy" || { mkdir -p $SCRATCH/sw/pv-site; cp -r $KIT/pv_numpy_$(uname -m)_py3.<minor>/* $SCRATCH/sw/pv-site/; }

# Large data: into the clone (never copy data/topologies or varying_series_xml; prepare_machine regenerates them)
cp -r $KIT/data_large/* $KIT/Visualization_Vignettes/data/
```

Set the variables the suite scripts read, then let them build the fixtures:

```bash
export VV_SW=$SCRATCH                              # scripts look for $VV_SW/sw/testing_paraview_env and $VV_SW/sw/pv-site
export VV_PARAVIEW_MODULE=<ParaView module>        # MODULES.sh loads it directly, skipping site detection
export VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow   # if the ex08 probe said hardware
cd $KIT/Visualization_Vignettes && python3 Testing/prepare_machine.py && python3 Testing/prepare_machine.py --check
```

## 3. On the target: run

ex08 first, always. It proves the EGL backend found the GPU; without that every
timing after it is llvmpipe wearing a GPU label.

```bash
cd $KIT/Visualization_Vignettes/Testing
TESTS="8" sbatch --account=<account> --partition=<gpu partition> --gres=gpu:<n> \
       --export=ALL,VARIANT=egl,MACHINE_NAME=<machine name> shaheen_ppn_pv_suite.sbat
```

Then the suites, one at a time (never two in one clone), exploratory first,
then recorded:

```bash
sbatch --account=<account> --partition=<p> --gres=gpu:<n> --export=ALL,VARIANT=egl,MACHINE_NAME=<machine name> shaheen_ppn_pv_suite.sbat
sbatch --account=<account> --partition=<p>                 shaheen_ppn_visit_suite.sbat     # only if a VisIt module exists
# green? then the record
sbatch ... --export=ALL,VARIANT=egl,MACHINE_NAME=<machine name>,EXTRA="--run-id <machine name>-<date>" shaheen_ppn_pv_suite.sbat
```

The `--account`, `--partition`, `--gres` on the command line override the
`#SBATCH` lines in the scripts (written for Shaheen's `ppn`). Pick a
`MACHINE_NAME` that says which machine and which renderer, so the history
stays readable.

An image gate that fails by a few percent on a new GPU is normal (renderer
differences): bless per machine with `EXTRA="--no-metrics --machine-baselines --bless"`
on that test, look at the image, then record.

## 4. On the target: collect what comes back

```bash
bash $KIT/Visualization_Vignettes/Testing/gpu_handoff/collect_results.sh $SCRATCH/vv_gpu_results_$(date +%F)
```

That tars the metric files, the per-machine baselines, the summary reports
and the logs. Carry the tarball back to the connected machine; on the
workstation, untar over the repo on a branch and open a PR. Nothing else
needs to come back.
