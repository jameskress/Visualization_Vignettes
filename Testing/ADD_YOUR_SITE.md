# Add your site to the results dashboard

The [results dashboard](https://jameskress.github.io/Visualization_Vignettes/dashboard/)
shows every vignette on every machine that has contributed results. Today
those are a workstation, Ibex and Shaheen. Another workstation, cluster or
GPU type is welcome: running the suite there and opening a pull request with
the results puts it on the dashboard beside them, and later runs show how
your machine moves across tool versions and system updates.

This page is the path from a fresh clone to a merged pull request. The
details behind each step are in [README.md](README.md) (the suite) and
[RUNBOOK.md](RUNBOOK.md) (per machine).

## What you contribute

| What | Where | Required |
| :--- | :--- | :--- |
| One history file per vignette | `<suite>/<vignette>/Testing/performance_metrics_<name>.json` | yes |
| Your own image baselines, only where your renderer draws different pixels | `<suite>/<vignette>/Testing/Baseline/<name>/` | only if needed |

`<name>` is your **configuration name**: one machine with one way of
rendering, for example `mycluster-cpu` or `mycluster-egl-a100`. It names
your files and your row on the dashboard, so choose it once and keep it:

* letters, digits, `_` and `-` only. A dot is a legal character, but a
  name with one is taken for a host name and refused;
* not a host name. Without `--machine_name` the suite falls back to the
  host name, so always pass it;
* the tool version does not go in it. Both ParaView and VisIt records,
  of every version, share the one file per vignette.

A dashboard row is grouped by site from the start of its name (`ibex`,
`shaheen`); any other name is listed under *Other*.

**What a record holds.** Each record carries timings, memory, CPU and I/O
figures, the pass or fail of every gate, the tool version and a hash of the
build, and the machine's description: kernel, OS, CPU model, memory, GPU and
driver, and the short host name of the node it ran on. The dashboard shows
none of the host names, but the history files in the repository are public,
so they are readable there. Executable and module paths are not recorded;
the build is named by a hash instead.

## 1. Set up the machine

Follow [RUNBOOK.md section 1](RUNBOOK.md#1-the-four-things-every-machine-needs):
the repository, a Python venv, the data and the generated fixtures.
`python3 Testing/prepare_machine.py --check` must exit 0 (or 3, which only
means ex06's 5.7 GB of data is absent and ex06 will report SKIPPED).

Use the builds the suite pins, ParaView 6.2.1 and VisIt 3.5.0. Runs of
other versions are recorded and shown too, but the dashboard marks a
configuration whose latest run is not on the pinned builds as stale.

**Energy, optional.** The suite records what energy it can read and skips
the rest without an error: GPU energy wherever `nvidia-smi` runs, node energy
on Cray nodes a job owns, and CPU package energy from RAPL
(`/sys/class/powercap/intel-rapl:*/energy_uj`, or the `amd_energy` hwmon
socket counters on AMD nodes) when the run has the machine
to itself (outside Slurm, or a job that owns its one node). Linux makes RAPL root-only by
default, because its fine-grained readings can leak information between
users (the PLATYPUS side channel). On a single-user workstation you may make
the package and DRAM counters readable, for example with a systemd-tmpfiles
rule that runs at every boot:

```bash
echo 'z /sys/class/powercap/intel-rapl:*/energy_uj 0444 - - -' | \
  sudo tee /etc/tmpfiles.d/rapl-read.conf
sudo systemd-tmpfiles --create /etc/tmpfiles.d/rapl-read.conf
```

Do not do this on a shared machine. Nothing else in the suite needs it.

## 2. Run without recording until it is clean

```bash
cd ~/Visualization_Vignettes/Testing
export PARAVIEW_PATH="<path-to-your-paraview-6.2.1>/bin"
python test_suite.py ~/Visualization_Vignettes/ --test_type ParaView \
  --paraview_version 6.2.1 --machine_name mycluster-cpu --no-metrics
export VISIT_PATH="<path-to-your-visit-3.5.0>/bin/"
python test_suite.py ~/Visualization_Vignettes/ --test_type VisIt \
  --visit_version 3.5.0 --machine_name mycluster-cpu --no-metrics
```

`--no-metrics` runs and compares exactly as usual and records nothing. On a
cluster, start from the batch scripts in this directory, which already pass
the right launcher, ranks and display settings
([README.md, Clusters](README.md#clusters-the-batch-scripts)); copy one and
change the account, partition and modules.

[RUNBOOK.md section 10](RUNBOOK.md#10-what-to-expect-the-first-time) lists
what a first run on a new machine usually shows: image tolerance on a
software renderer (`--image-tolerance 0.0075`; ex05's annotation text
differs under Mesa whatever the tolerance), and partition-boundary
differences above one rank.

## 3. Your own image baselines, only if the pictures differ

An image gate that fails because your renderer draws a correct picture a
few levels differently (Mesa against a GPU, or Surface LIC noise) gets its
own baseline set; numeric, CSV and text baselines stay shared:

```bash
python test_suite.py ~/Visualization_Vignettes/ --test_type ParaView \
  --paraview_version 6.2.1 --test_number 6 --machine_name mycluster-cpu \
  --machine-baselines --bless --no-metrics
```

Look at the images in the vignette's `output/` before blessing, and at the
`Testing/Baseline/mycluster-cpu/` diff before committing: a blessed
baseline says what correct looks like. If your configuration draws exactly
what an existing one draws, judge against that one with `--baseline-machine
<its name>` instead of adding a copy. A wrong picture is a bug to report,
not a baseline to bless.

## 4. Record one run

Once both suites pass, record one tagged run of each, with three repeats so
the dashboard has a median and a spread:

```bash
python test_suite.py ~/Visualization_Vignettes/ --test_type ParaView \
  --paraview_version 6.2.1 --machine_name mycluster-cpu \
  --run-id mycluster-cpu-2026-11-22 --repeat 3
```

and the same for VisIt. On a workstation, `./record_local_run.sh <run-id>
<name>` records both suites this way. A run that went wrong comes out again
with `python3 manage_metrics.py --remove-run <run-id> -y`
([README.md, Cleaning up records](README.md#cleaning-up-records-that-are-already-committed)).

## 5. Check and open the pull request

```bash
cd ~/Visualization_Vignettes
python3 Testing/check_submission.py --base origin/master
python3 Testing/dashboard.py --out /tmp/vv-dashboard
```

The first command runs the checks the pull request will run (below) and
prints one line per problem. The second builds the dashboard with your
records; open `/tmp/vv-dashboard/index.html` to see your row.

Commit the history files and any `Testing/Baseline/<name>/` directories,
and nothing else from the run (logs, `output/`, summary reports), then open a
pull request against `master`. In its description, give the machine
(CPU, GPU, interconnect), how ParaView and VisIt were built or loaded, the
renderer (GPU EGL, OSMesa, llvmpipe), and anything that failed and why.

### What the pull request checks

The *Results dashboard* workflow runs `Testing/check_submission.py` and
then builds the dashboard with your records; the built site is attached to
the run as an artifact to look at.

* Every history file parses, sits in a vignette's `Testing/` directory,
  and every record in it names that vignette.
* The configuration name, and every per-site baseline directory, is a
  public name: allowed characters, not a host name.
* Each record the pull request adds was written by a current
  `test_suite.py` (metrics schema 5 or newer), carries a `run_id`, a
  numeric `execution_time` and a `run_succeeded`, was not filed under the
  host name it ran on, and is not dated in the future.

What it does not check is whether the numbers are right: that is what the
gates did when you ran them, and what review of the pull request is for.

## Afterwards

Record again after each change that matters: a new ParaView or VisIt
version ([RUNBOOK.md section 12](RUNBOOK.md#12-testing-a-new-paraview-or-visit-build)),
and just before and after a system maintenance, so the dashboard can tell
a system change from a tool change. A configuration with no run for six
months (183 days) is marked stale; one whose hardware is gone can be retired in
`Testing/retired_configurations.json`, which keeps its history and its page.
