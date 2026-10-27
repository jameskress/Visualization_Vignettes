# Running the suites on the air-gapped Shaheen GPU system

The GPU system has its own login (a web portal), no network, and no view of
Shaheen's scratch. An admin copies a folder from Shaheen scratch to it. This
directory makes that folder, and this file is the sequence to run once you
are inside. Nothing below touches the network.

## 1. On Shaheen (connected): build the handoff folder

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
| `wheelhouse_<arch>_py3.10`, `_py3.11`, `_py3.12` | the five Python dependencies as wheels, per interpreter, for `x86_64` and `aarch64` | GPUP is Grace Hopper, ARM64: x86 wheels do not run there |
| `pv_numpy_<arch>_py3.10`, `_py3.12` | numpy unpacked for ParaView's own Python, both architectures | the HPE ParaView/6.1.1 carries Python 3.12; check whether it has numpy |

The admin copies the whole folder. Ask for it to land under scratch on the
target; the paths below assume `$SCRATCH` exists there.

## What is known about GPUP (26 Oct 2026, from HPE's install note)

Login `gh1`, Grace Hopper nodes (`craype-arm-grace`: **ARM64**, so only the
`aarch64` wheelhouses apply), four GPUs per node (`--gres=gpu:4`), Cray PrgEnv.
`module av ParaView` shows `ParaView/6.1.1` under `/sw/ex113gracehopper`; the
module carries its own Python 3.12 and prepends it to `PYTHONPATH` (the same
leak as Shaheen's module: the suite scripts' pvbatch wrapper handles it), and
it sets `VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow`. That last line
means **this build renders in software through OSMesa and does not use the
GPUs**. ex08 will report "software"; that is the correct result for this
build, not a failure of the suite, and it is the first thing to tell HPE. Use
`export VV_PARAVIEW_MODULE=ParaView/6.1.1` (capital P; the module name does
not say mesa or egl, so MODULES.sh keeps the hint the module already set).
No VisIt module was listed; check `module av visit` before planning that suite.

## 2. On the target: first time

```bash
cd $SCRATCH/vv_gpu_handoff
git -C Visualization_Vignettes log --oneline -1        # confirm which master you carry
git bundle verify vignettes.bundle                     # intact?

# Python: whichever module exists; match the wheelhouse to it
module avail python; module load python/<3.10|3.11|3.12>
python3 --version
python3 -m venv $SCRATCH/sw/testing_paraview_env
source $SCRATCH/sw/testing_paraview_env/bin/activate
pip install --no-index --find-links=wheelhouse_py3.<minor> pandas numpy pillow matplotlib psutil
deactivate

# ParaView: find the module, decide whether it has numpy
module avail paraview visit
module load <paraview module>                           # or export VV_PARAVIEW_MODULE=<name> for MODULES.sh
pvpython -c "import numpy" || echo "no numpy: use pv_numpy_py3.<minor> through the pvbatch wrapper"

# Large data: into the clone (never copy data/topologies or varying_series_xml; prepare_machine regenerates them)
cp -r data_large/* Visualization_Vignettes/data/
```

Set two variables for the suite scripts, then let them build the fixtures:

```bash
export VV_SW=$SCRATCH                      # suite scripts look for $VV_SW/sw/testing_paraview_env and $VV_SW/sw/pv-site
export VV_PARAVIEW_MODULE=<paraview module name>      # MODULES.sh loads it directly, skipping site detection
mkdir -p $SCRATCH/sw/pv-site && cp -r pv_numpy_py3.<minor>/* $SCRATCH/sw/pv-site/   # only if pvpython lacked numpy
cd Visualization_Vignettes && python3 Testing/prepare_machine.py && python3 Testing/prepare_machine.py --check
```

## 3. On the target: run

ex08 first, always. It proves the EGL backend found the GPU; without that every
timing after it is llvmpipe wearing a GPU label.

```bash
cd Testing
TESTS="8" sbatch --account=<acct> --partition=<gpu partition> --gres=gpu:4 \
       --export=ALL,VARIANT=mesa,GPU=GH200,MACHINE_NAME=gpup-gh200-mesa \
       shaheen_ppn_pv_suite.sbat      # VARIANT=mesa: the HPE build is OSMesa, so judge with the software tolerance
```

Then the suites, one at a time (never two in one clone), exploratory first,
then recorded:

```bash
sbatch --account=<acct> --partition=<p> --gres=gpu:4 --export=ALL,VARIANT=mesa,MACHINE_NAME=gpup-gh200-mesa shaheen_ppn_pv_suite.sbat
sbatch --account=<acct> --partition=<p>               shaheen_ppn_visit_suite.sbat
# green? then the record
sbatch ... --export=ALL,VARIANT=mesa,MACHINE_NAME=gpup-gh200-mesa,EXTRA="--run-id gpup-gh200-mesa-<date>" shaheen_ppn_pv_suite.sbat
sbatch ... --export=ALL,EXTRA="--run-id shaheen3-gpu-<date>" shaheen_ppn_visit_suite.sbat
```

The `--account`, `--partition`, `--gres` on the command line override the
`#SBATCH` lines in the scripts (written for Shaheen's `ppn`). Machine names: with
`VARIANT=mesa` the script records `shaheen3-mesa-ppn`; on GPUP set
`MACHINE_NAME=gpup-gh200-mesa` so the history says which system and that the
render was software. If HPE later provides an EGL build, rerun with
`VARIANT=egl`, `MACHINE_NAME=gpup-gh200`.

An image gate that fails by a few percent on a new GPU is normal (renderer
differences): bless per machine with `EXTRA="--no-metrics --machine-baselines --bless"`
on that test, look at the image, then record.

## 4. On the target: collect what comes back

```bash
bash Testing/gpu_handoff/collect_results.sh $SCRATCH/vv_gpu_results_$(date +%F)
```

That tars the metric files, the per-machine baselines, the summary reports
and the logs. Ask the admin to copy the tarball back to Shaheen scratch; on
the workstation, untar over the repo on a branch and open a PR. Nothing else
needs to come back.
