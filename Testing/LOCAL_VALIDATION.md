# Local validation of the vignette regression suite

Bringing the `regressionTestingUpdates` branch (ex00–ex12, both suites, plus the
reworked `Testing/` harness) up on a workstation, against **ParaView 6.1.0** and
**VisIt 3.4.2**, before the same suite is taken to Shaheen.

Machine of record: `KW61316.kaust.edu.sa`, Ubuntu 22.04, 64 cores, 251 GB RAM,
2 × NVIDIA RTX A5000 (driver 580.173.02).

---

## 1. Current status

**ParaView 6.1.0, VisIt 3.4.2 and VisIt 3.4.1: 13 of 13 each, exit 0**, every
correctness gate, process exit code, image, numeric, CSV and the legacy text
comparison. Thirty-nine vignette runs, zero failed comparisons of any kind.

ex12 was the exception for a while, and the reason is worth reading before
anything else here: VisIt 3.4.2 reported every state of the shipped time
series as t=0 where 3.4.1 reported 0..19. Chasing that turned up something
larger. **The shipped series carries no time at all**, so neither tool had
ever been reading one; both synthesized a time from the file's position in the
list and agreed by coincidence until 3.4.2 changed its guess. The series is
now generated as XML with real times and cycles in it, and ParaView 6.1.0,
VisIt 3.4.1 and VisIt 3.4.2 all read the same values. See §4b.13.

These three runs are the ones recorded in the committed history. Everything
else behind §4 and §4b was run with `--no-metrics` and left no trace; see
§3 for the rule.

### ParaView 6.1.0, `KW61316.kaust.edu.sa`, run `pv610-local-2026-09-21`

| Vignette | Wall (s) | Peak (MB) | CPU (%) | Notes |
| :--- | ---: | ---: | ---: | :--- |
| ex00_pvQuery | 2.87 | 430 | 86 | numeric gate was silently dead, now live |
| ex01_pvScreenshot | 3.63 | 546 | 108 |  |
| ex02_pvAnimation | 56.31 | 1,591 | 145 |  |
| ex03_pvIsosurfaceAnimation | 19.20 | 1,649 | 348 |  |
| ex04_pvStreamlineAnimation | 67.84 | 1,741 | 603 |  |
| ex05_pvMultiTimeStepFile | 4.92 | 782 | 418 | XML time series + frame annotation, §4b.13 |
| ex06_pvLargeData | 192.22 | 61,992 | 2007 | 5% image tolerance, §5 |
| ex07_pvScaling | 4.52 | 557 | 231 |  |
| ex08_pvBackendCheck | 3.47 | 598 | 97 | metrics are machine-specific by design |
| ex09_pvMeshTopologies | 4.22 | 750 | 189 | isovalues fixed; polydata frame fixed, §4b.12 |
| ex10_pvColormapFidelity | 3.89 | 627 | 138 | legend format + binning fixed |
| ex11_pvStateVerification | 3.94 | 684 | 164 | needs xvfb, `--no-offscreen` |
| ex12_pvExtractRegression | 3.89 | 629 | 250 | extract loop fixed; real time + cycle, §4b.13 |
| **TOTAL** | **370.9** | | | ex06 is 52% of the wall clock and the only one that needs more than 2.4 GB |

`ex06_pvLargeData` is intermittent at the pixel level and declares its own 5%
image tolerance to absorb that; see §5. ex11 runs separately, under `xvfb-run`
with `--no-offscreen`, tagged with the same run id.

### VisIt 3.4.2, `KW61316.kaust.edu.sa`, run `visit342-local-2026-09-21`

| Vignette | Wall (s) | Peak (MB) | CPU (%) | Notes |
| :--- | ---: | ---: | ---: | :--- |
| ex00_visitQuery | 1.85 | 383 | 284 |  |
| ex01_visitScreenshot | 2.09 | 576 | 287 |  |
| ex02_visitAnimation | 45.74 | 1,013 | 350 |  |
| ex03_visitIsosurfaceAnimation | 18.77 | 1,054 | 287 |  |
| ex04_visitStreamlineAnimation | 82.37 | 2,363 | 244 |  |
| ex05_visitMultiTimeStepFile | 17.12 | 887 | 205 | XML time series + frame annotation, §4b.13 |
| ex06_visitLargeData | 207.15 | 36,050 | 107 | baseline is 8-rank, §4b.8 |
| ex07_visitScaling | 5.23 | 454 | 136 | `MinMax` on an isosurface, §4b.6 |
| ex08_visitBackendCheck | 1.97 | 424 | 274 | rank count derived from pids, §4b.4 |
| ex09_visitMeshTopologies | 4.28 | 548 | 168 | `viridis` loaded explicitly; polydata frame fixed, §4b.12 |
| ex10_visitColormapFidelity | 4.88 | 467 | 134 | `GetNumPlots()`, §4b.5 |
| ex11_visitStateVerification | 2.32 | 456 | 256 | identical with and without a display |
| ex12_visitExtractRegression | 3.62 | 462 | 170 | volume integrals pre-pass; real time + cycle, §4b.13 |
| **TOTAL** | **397.4** | | | ex06 is 52% of the wall clock and the only one that needs more than 2.4 GB |

Twelve in one command and ex11 on its own under `xvfb-run`, so one run id files
one record per vignette (§3). ex11's frames come out bit-identical with and
without a display, so it does not need a baseline of its own.

Every VisIt baseline in the repository was replaced during this pass, see §5b
for which ones were merely stale, which one was never wrong in the first place,
and which rank count each is blessed at.

### VisIt 3.4.1, `KW61316.kaust.edu.sa`, run `visit341-local-2026-09-21`

3.4.1 is what `MODULES.sh` loads on Shaheen and Ibex until spring (§5b), so it
gets a full run of its own, against the same baselines: **13 of 13, exit 0**,
no image, numeric, CSV or text comparison failed.

| Vignette | Wall (s) | Peak (MB) | CPU (%) |
| :--- | ---: | ---: | ---: |
| ex00_visitQuery | 1.79 | 367 | 40 |  |
| ex01_visitScreenshot | 2.00 | 568 | 74 |  |
| ex02_visitAnimation | 45.25 | 2,642 | 349 |  |
| ex03_visitIsosurfaceAnimation | 18.15 | 1,628 | 277 |  |
| ex04_visitStreamlineAnimation | 80.99 | 4,360 | 237 |  |
| ex05_visitMultiTimeStepFile | 17.17 | 1,144 | 174 |  |
| ex06_visitLargeData | 208.73 | 36,338 | 106 |  |
| ex07_visitScaling | 5.60 | 435 | 53 |  |
| ex08_visitBackendCheck | 1.95 | 412 | 51 |  |
| ex09_visitMeshTopologies | 4.28 | 537 | 63 |  |
| ex10_visitColormapFidelity | 4.83 | 461 | 43 |  |
| ex11_visitStateVerification | 2.37 | 458 | 64 |  |
| ex12_visitExtractRegression | 3.55 | 462 | 46 |  |
| **TOTAL** | **396.7** | | |

Within 0.2% of 3.4.2 on wall clock, and **it uses roughly twice the memory on
the animation vignettes**. That is the one number to carry into a Shaheen
allocation request. Its own history file is why: comparing a 3.4.1 record
against a 3.4.2 one would report that as a regression every time.

### Reading these numbers

**Peak memory is each vignette's own**, sampled across its whole process tree
rather than taken from `RUSAGE_CHILDREN`, which is a high-water mark that never
falls and had been reporting ex06's 62 GB as the peak of every vignette that ran
after it (§4.9).

**CPU percent is also whole-tree**, which matters far more for VisIt than for
ParaView: the VisIt client forks a viewer, an mdserver and a compute engine, and
the engine is where all the work happens. Before this was fixed the same ex06
run reported 13%; it is 107% (§4b.10). `metrics_schema` is **4**, and the
performance gate refuses to compare across a schema boundary.

**`any_tests_failed` in the summary report can be `true` while the suite exits
0**, and that is not a contradiction. The five correctness gates feed the exit
code; the *performance* gate does not. It flags any metric that moved more than
10% against the previous run, and on a shared workstation `cpu_usage_percent`
crosses that on the short vignettes routinely. Read the exit code for pass/fail
and the performance section as a prompt to look. It will mean much more on a
Slurm allocation than it does here.

---

## 2. One-time setup

### Python environments

```bash
python3 -m venv ~/testing_paraview_env
~/testing_paraview_env/bin/pip install pandas numpy pillow matplotlib psutil scipy

python3 -m venv ~/testing_visit_env
~/testing_visit_env/bin/pip install pytz six pyparsing psutil pandas numpy pillow matplotlib scipy
```

`psutil` is now load-bearing, not optional: it is what samples each vignette's
own peak memory (§4.9).

### Data

```bash
cd data
./fetchData.sh          # 4.3 GB, needed by ex06 only
```

### Generated fixtures, one command

Five of the suite's inputs are generated by a tool rather than shipped, and
none of them is portable: two are locked to a ParaView version, one to a VisIt
version, one holds absolute paths to this machine's data directory, and one is
a converted copy of the time series that only stays current while its source
does. This used to be four
commands documented in four places with nothing checking them. It is now one
idempotent command that rebuilds only what is missing or stale:

```bash
export PARAVIEW_PATH=/home/kressjm/packages/ParaView-6.1.0-MPI-Linux-Python3.12-x86_64/bin
export VISIT_PATH=/home/kressjm/packages/visit3_4_2.linux-x86_64/bin

python3 Testing/prepare_machine.py
```

```
ParaView   : 6.1.0  (/home/.../ParaView-6.1.0-.../bin/pvbatch)
OK   data/topologies generated by ParaView 6.1.0
OK   ex11_state.pvsm written by ParaView 6.1.0
OK   XML time series present (20 timestep(s))

VisIt      : 3.4.2  (/home/.../visit3_4_2.linux-x86_64/bin/visit)
OK   ex11_visit.session and ex11_series.visit present

OK   ex06 datasets present
OK   this machine is ready
```

* `--check` reports and changes nothing, exiting non-zero when anything is stale.
  Usable as a preflight in a job script.
* `--force` regenerates regardless.
* A tool that is not installed is skipped with a note, not an error, so this is
  safe on a machine that has only ParaView or only VisIt.
* It will not start the 4.3 GB `fetchData.sh` download on its own. It tells you
  when ex06's data is absent and leaves that decision to you.

`ex10` needs nothing prepared; its colour maps ship beside it.

### And the vignettes now check, rather than trusting

`prepare_machine.py` only helps if you remember to run it, so the guard is also
at the point of use. `data/topologies/topologies_manifest.json` records the
ParaView that wrote it, a `.pvsm` already records its own version, and ex09 and
ex11 compare both against the ParaView they are running under:

```
VignetteError: data/topologies (topologies_manifest.json) was generated by
ParaView 6.1.0, but this is ParaView 6.0.1. These fixtures are not portable
across a major.minor boundary and the mismatch does not announce itself -- it
shows up as wrong point and cell counts. Regenerate on this machine:
    pvbatch data/make_topology_datasets.py
```

That is the message you get now. What you got before was ex09 quietly reading
216 points where 842 were written, and a numeric-gate failure that looked like a
regression in the vignette. A fixture with no recorded version is warned about
rather than failed, so an older checkout still runs.

---

## 3. Running the suite

### ParaView, everything except ex11

```bash
export PARAVIEW_PATH=/home/kressjm/packages/ParaView-6.1.0-MPI-Linux-Python3.12-x86_64/bin
source ~/testing_paraview_env/bin/activate
cd Testing

python test_suite.py ../ \
  --test_type ParaView \
  --paraview_version 6.1.0 \
  --machine_name KW61316.kaust.edu.sa \
  --run-id pv610-local-$(date +%Y-%m-%d) \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 \
  --timeout 1800
```

### ParaView, ex11, which must NOT be offscreen

`ex11` exists to verify the on-display path a GUI user takes, so it needs a real
X display and must not be forced offscreen. `--no-offscreen` applies to the
whole invocation, which is why ex11 runs in its own command:

```bash
xvfb-run -a --server-args="-screen 0 1280x1280x24" \
  python test_suite.py ../ \
    --test_type ParaView --paraview_version 6.1.0 \
    --machine_name KW61316.kaust.edu.sa --run-id <same id as above> \
    --test_number 11 --no-offscreen --timeout 1800
```

Pass the **same `--run-id`** to both so `manage_metrics.py --remove-run` can
undo the pair as one unit.

### VisIt

```bash
export VISIT_PATH=/home/kressjm/packages/visit3_4_2.linux-x86_64/bin
source ~/testing_visit_env/bin/activate
cd Testing

python test_suite.py ../ --test_type VisIt --visit_version 3.4.2 \
  --machine_name KW61316.kaust.edu.sa \
  --run-id visit342-local-$(date +%Y-%m-%d) \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 \
  --timeout 1800
```

Twelve here and ex11 on its own, the same split ParaView uses, so that one run id
writes exactly one record per vignette. VisIt's ex11 is not the trap ParaView's
is: ParaView's ex11 *fails* when forced offscreen, VisIt's merely warns and
renders anyway. It is worth wrapping all the same, because the display path is
what that vignette exists to cover, and the warning in its log is easy to scroll
past. Running all thirteen here **and** the command below would file ex11 twice
under one run id, which is what `--test_number` above avoids:

```bash
xvfb-run -a --server-args="-screen 0 1024x1024x24" \
  python test_suite.py ../ --test_type VisIt --visit_version 3.4.2 \
    --machine_name KW61316.kaust.edu.sa --run-id <same id> --test_number 11
```

The confirmation is written by the vignette, not the harness, so look for it in
`VisIt_Vignettes/ex11_visitStateVerification/Testing/output.log` rather than on
the terminal:

```
[ex11_visitStateVerification] DISPLAY=:99 -- rendering through the display path
```

Measured: all three frames are **bit-identical** with and without a display, so
one baseline covers both and the `.sbat` scripts (which already wrap ex11 in
`xvfb-run`) need nothing special.

Two things about a VisIt log that are normal and worth knowing before you read
one:

* **`visit -cli` exits 250 whether it worked or not.** The harness ignores the
  exit code and reads the vignette's own results JSON instead; the line you
  want is `Vignette passed (results JSON status=ok)`. See §4b.1.
* **`-noconfig` is always passed**, so the run is independent of whose
  `~/.visit` it ran under. That also means VisIt starts with 18 colour tables
  rather than 157, and the vignettes load the ones they need out of the install
  themselves. See §4b.2.

#### Rehearsing a parallel run locally

`--machine local` never touches a scheduler, but it is no longer serial-only:

```bash
python test_suite.py ../ --test_type VisIt --visit_version 3.4.2 \
  --machine_name KW61316-scratch --ranks 8 --no-metrics
```

Above one rank this starts the engine through VisIt's own bundled `mpirun`
(`-np 8`), which is the cheapest way to find a parallel problem before spending
queue time on it, and it is how the rank question in §5b was answered without
spending any.

Bless from it only for a vignette whose baseline is *meant* to be parallel.
ex06 is the one: its baseline is blessed at eight ranks to match its `.sbat`
scripts. Everything else is blessed at one rank and is bit-identical at eight.

### VisIt 3.4.1, the cluster version

Shaheen and Ibex load `visit/3.4.1` until the spring module update (§5b), so a
local run of it is kept beside the reference one. Same baselines, **same
history file**: it is the same machine in the same rendering configuration,
and the version is recorded inside each record. Putting it in a file of its
own would hide the 3.4.1 against 3.4.2 comparison, which is one of the more
useful things this suite produces.

```bash
VISIT_PATH=/home/kressjm/packages/visit3_4_1.linux-x86_64/bin \
  python test_suite.py ../ --test_type VisIt --visit_version 3.4.1 \
    --machine_name KW61316.kaust.edu.sa \
    --run-id visit341-local-$(date +%Y-%m-%d) --timeout 1800
```

`--visit_version` is what separates the two in the history, not the machine
name. The gate reads it and says so:

```
Comparing memory_usage_mb: previous=1013.35 (v3.4.2), current=2642.12 (v3.4.1)
    Tool version differs between these two runs: v3.4.2 (earlier) ->
    v3.4.1 (latest), memory_usage_mb moved +160.7%. Reported rather than
    failed ...
```

### Seeing it rather than reading it

Each run rewrites six plots per vignette from the committed history, plus one
per suite. The trend plots put **each configuration in its own panel against
its own run number**, which is the third attempt at that axis and the first
one that works: a date axis and then a union-of-all-timestamps axis both drew
each configuration as a narrow band joined by a line straight across the
figure, under sixty-seven rotated timestamps mostly belonging to other
machines.

The single most useful thing the rewrite added is that **the schema boundary
is drawn**. ex00_pvQuery's memory reads 118 MB in 2024 and 428 MB in 2026, and
the old plot drew a line straight up between them. Nothing regressed: the 2024
figure was the harness's own resident set and the 2026 figure is the peak of
the vignette's whole process tree (§4.9). A plot that renders a change in what
a number MEANS as a change in the number is worse than no plot. Those records
now sit behind a grey band, and they are excluded from the latest-run bar
chart entirely.

Autoscaling each panel was the other half. With a shared y axis, one 428 MB
point flattened eleven panels of 2024 data into a straight line; autoscaled,
you can see ibex-cpu wandering between 133.6 and 135.5 MB across eight runs,
and shaheen3-cpu dropping from 137 MB to 98 when ParaView went 5.13.1 to
6.0.1. Both were invisible before. Cross-configuration comparison moved to the
companion `<metric>_latest.png` bar chart, which does it better than eleven
sparklines ever did.

### What goes into the committed history, and what does not

`performance_metrics_<machine>.json` is tracked in git and is the long-term
record. It is not a log of everything that was run. The rule:

* **`--no-metrics` on every debugging, blessing, experimenting and
  rank-checking run.** It compares exactly as usual and appends nothing. Most
  of the runs behind §4 and §4b were `--no-metrics`; none of them are in the
  history.
* **One recorded run per configuration, at the end**, once the code is in the
  state you intend to commit. Tag it with `--run-id` so it can be undone as a
  unit.
* **`--machine_name` names the configuration, never the tool version.** One
  file per machine and rendering configuration, with the tool version recorded
  inside each record, which is the convention the 2024 entries and the cluster
  files already use (`ibex-cpu`, `ibex-egl-a100`, `shaheen3-ppn-gpu-L40`). The
  local reference is `KW61316.kaust.edu.sa`, continuing the line that starts
  with ParaView 5.13.1 in October 2024, and the local 3.4.1 run goes in it too.
  `shaheen3-cpu` has held 3.4.1 and 3.4.2 records together since 2024, and the
  ParaView files have held 5.13.1 and 6.x the same way; a name like
  `KW61316-visit341` would break that and, worse, would hide the comparison.
* **The performance gate distinguishes a regression from a version change.**
  Two runs at the same tool version, one metric moved more than 10%: a
  regression, and the run fails. Two runs at different versions: the
  difference is printed with both version numbers and recorded under
  `version_comparisons` in the summary report, and the run does not fail.
  Seeing that 3.4.1 costs 2.6x the memory of 3.4.2 on ex02 is a result, not a
  false alarm, and the latest record is often deliberately the *older* build.
* **`metrics_schema` marks where a measurement's meaning changed.** It is 4
  now; the 2024 records predate the field. That one the gate refuses outright,
  because those rows measured a different quantity and comparing them says
  nothing about either version (§4.9, §4b.10). This is the only case where
  numbers are withheld rather than labelled.

Undoing a recorded run is one command, and it is precise even when newer runs
landed on top:

```bash
python manage_metrics.py --list-runs
python manage_metrics.py --remove-run <run-id> -y
```

### Experimenting without polluting the committed history

```bash
python test_suite.py ../ ... --no-metrics
```

Runs and compares exactly as usual; appends nothing to
`performance_metrics_<machine>.json`. Use this for every debugging run.

### Blessing

```bash
# 1. run, and LOOK at output/
python test_suite.py ../ --test_type ParaView --test_number 7 --machine_name ... --no-metrics
# 2. only once satisfied
python test_suite.py ../ ... --test_number 7 --bless --no-metrics
# 3. re-run without --bless to confirm it now passes
```

`--generate-metrics --bless` blesses from outputs already on disk without
re-running, which is useful after a long suite run you have already inspected.

**Clear `output/` before a blessing run.** Nothing in the harness does: it only
cleans `Testing/`, and ex12 counts files it produced.

---

## 4. What was changed, and why

Everything below was a real failure on this machine, not a theoretical one.

### 4.1 `.vth` has no writer in ParaView 6.1, `data/make_topology_datasets.py`

`SaveData("amr_hierarchy.vth")` finds no writer in 6.x (the extension is
`.vthb` now), returns a null proxy, and `CreateWriter` then raises
`AttributeError` on it. The exception was unguarded, so dataset generation died
**before writing the manifest** and every ex09 run failed on a missing file.

Fixed by probing both extensions and recording whichever produced a file, so one
script is correct on 5.13.1 (Shaheen/Ibex) and 6.1 (here).

### 4.2 pvbatch 6.1 segfaults on `sys.exit()`, every rendering vignette

Reduced to its essentials:

```python
cone = Cone(); v = GetActiveViewOrCreate("RenderView")
Show(cone, v); SaveScreenshot(path, v)
sys.exit(0)        # -> "error: exception occurred: Segmentation fault", exit 1
```

The same script exits 0 when it falls off the end, and exits 0 under `xvfb-run`
with a real display. The crash is in interpreter teardown, after the vignette has
finished and written everything, whenever a render window exists and no X display
does, which is every offscreen batch run and every compute node.

Deleting the view, `ResetSession()` and `servermanager.Finalize()` before exiting
were each measured; none of them prevent it.

Because the whole point of the reworked harness is that the exit code is a gate,
this turned every clean pass into a failure. Fixed with `vc.exit_vignette(code)`
(`os._exit` after an explicit flush), used by all 13 ParaView vignettes. VisIt
still shuts down through `finish_visit_session`, which must close the compute
engine first.

### 4.3 The numeric gate was dead for ex00, `Testing/test_suite.py`

`vignette_script_name()` derived the results-JSON name from the *script filename*.
Every vignette names that file after its `VIGNETTE` constant, which is the
*directory* name. The two differ in exactly one place, `ex00_pvQuery/` contains
`ex00_pvConeStat.py`, so the harness looked for
`ex00_pvConeStat_results.json`, found neither a produced file nor a baseline,
concluded "this vignette emits no structured results", and skipped the gate.
Blessing recorded nothing for the same reason.

Now resolved from a results JSON that actually exists, then the directory name,
then the filename.

### 4.4 Animation vignettes could never pass, `Testing/verify.py`

Blessing records at most `--max-baseline-images` (default 5). Image comparison
reported every *produced* image without a baseline as `NO BASELINE`, which is a
failing status. So a ten-frame animation had five permanently failing frames the
moment it was blessed, and no number of re-blesses could fix it, while the
code's own comment said the report was "informational only".

Split into a separate non-failing `NOT BASELINED` status. A genuinely missing
baseline for an image the comparison *does* cover is still `NO BASELINE`, and
still fails.

### 4.5 ex09: two isovalues that could never produce geometry

Both version-independent, both caught by the new assertions:

- **AMR.** `amr_contour_value()` returned `0.5` down both of its branches. The
  Gaussian pulse actually tops out near 0.33, so the contour was empty on every
  run.
- **Polydata.** `surface_polydata.vtp` *is* the isosurface of the wavelet at 150,
  so its scalar is exactly 150 everywhere. Contouring a constant field at its own
  constant value produces nothing, in ParaView and VisIt alike.

The generator now measures each dataset's range and records an isovalue strictly
inside it, and gives the surface a scalar that varies *along* it (the Y
coordinate) so the contour becomes the isoline the vignette says it is testing.
Both ex09 vignettes read the per-dataset value from the manifest.

### 4.6 Preset renames, `Viridis (matplotlib)` → `Viridis`

ParaView 6.0 dropped the ` (matplotlib)` suffix and 6.1 *raises* on an unknown
preset instead of warning, which aborted ex09. Worse in the other direction:
5.13 returns `False` and carries on, and every call site here discarded that
return, so on the cluster a rename would have rendered in the wrong colours
with every assertion passing.

`vc.apply_color_preset(lut, candidates, ctx)` takes every spelling the preset has
had, checks both the exception and the return value, and raises if none work. Now
used at all seven ParaView call sites.

### 4.7 Legend numbers printed as format strings, ex06 and ex10

ParaView 6 formats scalar-bar numbers with `std::format` specs (`{:<#6.3g}`), not
printf ones, and it does not reject a printf string; it prints it verbatim.
ex06's QICE legend read `%-#6.3f` where 5.13 drew `0.000 / 0.001`. Nothing in the
suite asserts on legend text, so blessing a 6.1 baseline would have recorded that
as correct.

`vc.number_format(bar, "%-#6.3f", "LabelFormat")` reads the build's own default
for that property to decide which dialect to emit, no version test, no table to
maintain.

### 4.8 ex11: a keyword that matched no ParaView release

`LoadState(..., restrict_to_data_files=False)`. The keyword is
`restrict_to_data_**directory**` in both 5.13.3 and 6.1.0. ParaView forwards an
unknown keyword to `_LoadStateLegacy`, which tries to set it as a proxy property
and raises `AttributeError`, while the fallback caught only `TypeError`, so the
fallback path was unreachable and the vignette simply died.

### 4.9 Peak memory was another test's number, `Testing/metrics.py`

`resource.getrusage(RUSAGE_CHILDREN).ru_maxrss` is a high-water mark over every
child the process has ever reaped, and never decreases. `test_suite.py` runs all
thirteen vignettes from one process, so once ex06 touched 62 GB, ex07–ex12 each
recorded **61965.6 MB** as their peak, ex06's number, written into their
committed history and compared against by the performance gate. Six of thirteen
memory figures per suite run were not measurements of anything.

`run_tests.py` now samples the vignette's own process tree while it runs and
records the peak; `metrics.py` prefers that and omits the metric entirely rather
than substituting a figure from a different test. Verified: ex03 1650 MB,
ex09 757 MB, where both previously read 61966 MB. `METRICS_SCHEMA` bumped to 3,
so the regression detector will not compare across the boundary.

### 4.10 ex12: `SaveExtracts` ran the whole animation, every iteration

`SaveExtracts()` without `FrameWindow` extracts *all* timesteps. Called inside the
per-step loop, a `--steps 3` run wrote all 20 timesteps three times over: the
extract phase timed 20 frames instead of one, and `data_extract_files` reported
20 against `steps_extracted` of 3, a count that would not have moved if per-step
extraction had stopped working altogether. It also left the pipeline parked at
timestep 19, so the measurements taken afterwards were of the wrong step.

Pinned with `FrameWindow=[index, index]`. `contour_cells` and `scalar_max` both
changed as a result; those are now correct.

### 4.11 ex12: file counts included the previous run's output

`os.listdir(output_dir)` counted everything on disk. Nothing clears `output/`
between runs, so the baseline was reproducible exactly once, on a clean checkout.
Now differenced against a listing taken before extraction starts.

### 4.12 ex10: the categorical map only ever showed 4 of its 5 colours

The binning expression scaled by `CATEGORY_COUNT - 1`, which is precisely what
its own comment said it was avoiding: four equal-width bins plus a fifth holding
only the exact maximum.

### 4.13 GPU selection pinned for single-rank renders, `Testing/run_tests.py`

With two GPUs visible the driver does not place work consistently. For a
single-rank job, which was only ever going to use one GPU, the device is now
pinned so the choice is deterministic. An explicit `CUDA_VISIBLE_DEVICES`
(which is what Slurm `--gres=gpu` sets) always wins, and nothing is pinned for a
multi-rank run.

### 4.14 VisIt reads the developer's config, `Testing/run_tests.py`

The VisIt CLI was launched without `-noconfig`, so `~/.visit/config`, saved
annotation, save-window, window-size and colour-table state, fed into every
baseline. The account running this suite has nine custom colour tables in
`~/.visit`, so this was not hypothetical. `-noconfig` added.

### 4.15 `ex11_make_state.py` reached `paraview` without importing it

It relied on the name leaking out of `from paraview.simple import *`. Now
imported explicitly, and it bootstraps `vignette_common` like every other script.

### 4.16 The preset helper had a hole that 6.0.1 fell straight through

The rename landed in **6.1**, not 6.0, so all three ParaViews disagree:

| Build | Preset name | Where |
| :--- | :--- | :--- |
| 5.13.1 | `Viridis (matplotlib)` |, |
| 6.0.1 | `Viridis (matplotlib)` | **Ibex** |
| 6.1.0 | `Viridis` | **Shaheen**, local |

And all three fail *differently* for a name they do not have: 6.1 raises, 5.13
returns `False`, and **6.0.1 does neither**: it returns something truthy and
silently leaves the transfer function alone. So the first version of
`apply_color_preset` accepted `"Viridis"` on 6.0.1, never tried the fallback, and
ex09's tetra contour rendered pale yellow instead of teal: 26.5% of the frame,
with every assertion passing.

The transfer function is now the witness: a preset that changed nothing is
investigated rather than trusted. "Nothing changed" has two very different
causes: the preset was already active (the normal case; ex09 colours four
topologies through one lookup table), or the name did not resolve and this
ParaView ignored it. Re-applying from a deliberately different sentinel state
separates them, and that extra step runs **only** in the ambiguous case, so the
normal path leaves the lookup table untouched.

That last detail cost two iterations and is worth recording:

* reading only `RGBPoints` missed categorical presets entirely, whose colours
  live in `IndexedColors`, ex10's `VV Categorical` looked like a preset that had
  not applied. The signature now covers `RGBPoints`, `Points`, `IndexedColors`
  and `NanColor`.
* forcing the sentinel state *unconditionally* perturbed the categorical lookup
  table enough to change its rendered image. Hence "only when ambiguous".

Verified on both 6.0.1 and 6.1.0: idempotent across three consecutive
applications, rejects a bogus name, and ex09/ex10 both come back bit-identical.

### 4.17 `MergeBlocks` refuses AMR on 6.0.1

`Input ... is of type vtkOverlappingAMR, but a vtkDataObjectTree is required` ,
6.1 accepts it, 6.0.1 does not, and VTK reports it through its error channel
rather than raising, so the failure arrived later and in disguise as
`Scalar 'scalar' absent from amr_hierarchy.vthb. Available point arrays: []`.

ex09 now merges, checks whether anything came out, and contours the composite
directly when it did not. ParaView's Contour takes composite input, so the
fallback is not a compromise.

---

## 4b. What was changed for VisIt, and why

§4.1–4.17 are ParaView. The VisIt vignettes had been written and reviewed but
never executed end to end. Everything below is a real failure on 3.4.2, in the
order it was hit.

### 4b.1 VisIt's launcher always exits 250, `Testing/run_tests.py`

`visit -cli` is a shell script that execs the real binary and returns its own
status. It returns **250 on success**, 250 on a Python traceback, and 250 on a
crashed compute engine. Measured on 3.4.2: a vignette that ran cleanly, one that
raised on line 3, and one whose engine aborted with SIGABRT all exited 250.

So for VisIt the exit code carries no information, and gating on it means either
every run fails or none ever does. The verdict now comes from what the vignette
itself wrote:

```
returncode                250          (recorded, never used as the verdict)
exit_code_is_authoritative false
verdict_source            "results JSON status=ok"
succeeded                 true
```

The results JSON has to be **fresh for this run**: its mtime is compared
against the launch time, otherwise a vignette that dies before writing anything
inherits the previous run's verdict, which is the worst possible failure mode
for a regression suite. A timeout is a failure regardless.

This was exercised by accident and held: the experiment in §4b.8 crashed VisIt's
engine with SIGABRT, `SaveWindow()` raised, no results JSON was written, and the
harness called it a failure on exactly the right grounds.

### 4b.2 `-noconfig` also hides 129 of VisIt's own colour tables

`-noconfig` (§4.14) is not optional for a regression suite, without it a
baseline is partly a function of whose `~/.visit` blessed it. But it is blunter
than it looks:

| | colour tables available |
| :--- | ---: |
| normal startup | 157 |
| `-noconfig` | **18** |

Only 11 of the 139 that disappear are this user's own. The other **129 are
VisIt's**, shipped as `.ct` files under
`$VISITARCHHOME/resources/colortables/` and loaded at startup by the same code
path `-noconfig` switches off. `viridis`, `plasma`, `Blues`, `magma`, `inferno`
, all of them.

And VisIt does not refuse an unknown colour-table name at the point of use. It
accepts it, fails the plot asynchronously with
`There is no color table named viridis`, and every subsequent query against that
plot returns `None`. ex09 died three steps later on `int(None)`, with nothing in
the traceback pointing at a colour table. ex06 did not die at all: it rendered a
washed-out grey frame that differed from its baseline in 99.3% of pixels while
every assertion passed.

`vc.ensure_color_table()` reads the `.ct` straight out of the install and adds it
by hand when it is not already present:

```python
pc_atts.colorTableName = vc.ensure_color_table(
    ctx, "viridis",
    ColorTableNames, AddColorTable, ColorControlPointList, ColorControlPoint,
)
```

It logs what it loaded and how many control points came back, so a future
failure says so. This keeps `-noconfig` (the suite depends on nobody's home
directory) without giving up VisIt's own tables, which are identical on Shaheen
and Ibex because they ship with the install.

Vignettes covered: ex09 (`viridis`), ex06 (`plasma`, `Blues`). ex10 builds its
own tables from control points and needed nothing.

### 4b.3 `getattr(visit_object, name, default)` does not fall back, `vc.visit_attr`

VisIt's attribute objects raise **`ValueError`** for an unknown field name, not
`AttributeError`. `getattr` only catches the latter, so the three-argument form
propagates instead of returning the default, and the usual defensive idiom is a
hard error. `dir()` on them raises too, so you cannot even look first.

`vc.visit_attr(obj, name, default)` is `getattr` with a default that actually
works. Two vignettes were relying on the broken idiom (§4b.4).

### 4b.4 ex08: `ProcessAttributes` has no rank count

The fields it actually carries on 3.4.2 are `pids`, `ppids`, `hosts`,
`isParallel`, `memory`, `times`. There is no `numProcs` and no `numNodes`; the
vignette asked for both and died on
`Could not find method with name 'numProcs'` before asserting anything (§4b.3 is
why the default did not save it). The counts now come from the data VisIt does
give: one pid per engine process, one distinct host per node.

### 4b.5 ex10: `PlotList` has no `numPlots`

Same shape of bug: `GetNumPlots()` is the accessor, `plots.numPlots` is not a
field, and the vignette died before rendering anything.

### 4b.6 ex07: `MinMax` on an isosurfaced plot returns the isovalue twice

`query_value("MinMax", use_actual_data=1)` on a plot that already carries the
Isosurface operator returns `(3.0, 3.0)`: every point on an isosurface *is* the
isovalue. So the "scalar range is non-degenerate" assertion could never pass, and
the recorded `scalar_min`/`scalar_max` were the isovalue twice rather than
anything about the data. `use_actual_data=0` asks the original database, which is
what the metric always meant.

### 4b.7 ex12: `Volume` on an isosurfaced plot is 0.0

The volume-weighted mean is `Weighted Variable Sum / Volume`, both over the
original mesh. Neither survives the contour pipeline:

* `use_actual_data=0` selects which *data* a query reads, but the query is still
  validated against the plot's **output topology**. An isosurfaced plot is a
  surface, so VisIt answers `Volume query requires 3D surface plot data` and
  returns 0.0 with either value of the flag. The vignette divided by it and
  asserted on the resulting NaN.
* Adding a second, hidden plot does not help either, VisIt does not execute a
  hidden plot's pipeline, so both integrals come back 0.0. Measured, after
  trying it.

The integrals are now collected in a pre-pass on their own operator-free plot,
which is then deleted. Nothing about the rendered frames changes.

Worth recording as a cross-check: with this fixed, VisIt ex12 reports
`scalar_mean = 8.770885`, which **matches ParaView's ex12 exactly**. Two
independent pipelines agreeing to six decimal places is the strongest single
piece of evidence in this whole exercise that both are measuring what they claim.

### 4b.8 ex06: the baseline was right, the rank count was different

This one was diagnosed wrong first, and the wrong diagnosis is worth keeping
because it was plausible for two hours.

`ex06_visitLargeData` came back **86% different** from its October 2025
baseline, even after §4b.2 restored `plasma` and `Blues`. The difference sat
entirely in the translucent cloud: terrain, legends and annotations differed by
1–7 grey levels, which is JPEG encoder noise.

Running the same script **with** the developer's config (no `-noconfig`) turned
up something alarming:

```
mpiexec -n 8 .../visit3_4_1.linux-x86_64/.../engine_par -hw-accel -n-gpus-per-node 2 ...
VisIt: Error - Scalable Render Request Failed
```

A host profile in `~/.visit` was starting an **8-rank parallel engine** from a
**VisIt 3.4.1 install**, with scalable rendering, none of which had been asked
for, and on this machine that combination now aborts with SIGABRT and saves no
image. The conclusion drawn was that the baseline had been made by a different
VisIt and was not reproducible. It was re-blessed at one rank.

**That was wrong.** Measured afterwards, on VisIt 3.4.1, at eight ranks, against
the original baseline restored out of git:

| Comparison | mean \|diff\| | pixels over 16 levels |
| :--- | ---: | ---: |
| fresh 8-rank render vs the 2025 baseline | **2.4** | **0.6%** |
| 1-rank render vs the 2025 baseline | 13.8 | 22.9% |
| 1-rank render vs 8-rank render | 13.8 | 23.1% |

The 2025 baseline was a perfectly good **8-rank** render, and it still
reproduces. The version was a red herring: 3.4.1 and 3.4.2 render this suite
identically (§5b). What changed was the rank count, because this scene is six
overlapping Pseudocolor plots, two of them translucent, and translucent geometry
is composited in an order that depends on how the data was partitioned.

So ex06's baseline is now blessed at **eight ranks**, which is what its `.sbat`
scripts request, and it is **bit-identical run to run** there, zero pixels
differ, no tolerance needed, unlike ParaView's ex06 (§5). A run at any other
rank count disables the image gate and says so:

```
[ex06_visitLargeData] WARNING: image gate disabled: the baseline was blessed at
8 rank(s) and this run is at 1. this cyclone scene is composited in a
partition-dependent order, so the two renders differ by roughly 23% of pixels
while both are correct. Bless at 8 rank(s), or compare the numbers rather than
the picture.
```

`ctx.disable_image_gate_off_baseline_ranks()` reads the rank count out of the
baseline's own results JSON, so there is no constant to keep in step. Every
other gate stays live: assertions, metrics and extracts all still run.

**`-noconfig` keeps its justification regardless**, a config that silently
substitutes a different VisIt install and a different engine topology is exactly
what a regression suite must not be subject to. It just was not the cause here.

### 4b.9 Every passing VisIt run printed "Vignette FAILED" first

Cosmetic, but it made a green log unreadable:

```
Vignette FAILED (exit 250) after 1.67s -- see .../error.log
Vignette passed (results JSON status=ok).
```

`_execute()` announced the exit-code verdict unconditionally. The VisIt path,
which derives the verdict itself, now asks it not to.

### 4b.10 CPU time measured the wrong processes for VisIt, `Testing/metrics.py`

The sibling of §4.9, found by disbelieving a number. The first clean VisIt suite
run reported **ex06 at 13% CPU over 207 seconds**, while its compute engine sat
at 33 GB resident on a 64-core machine.

`cpu_usage_percent` came from `RUSAGE_CHILDREN`, which accounts only for
processes this harness reaped. For ParaView that is nearly the whole story ,
`mpirun` is the direct child, `pvbatch` is its child, and the usage chains up as
each is reaped. For VisIt it is not: `visit -cli` starts a viewer, an mdserver
and an `engine_ser`/`engine_par`, and the engine is where every second of render
and query time goes.

`run_tests.py` already walked the process tree every 0.25 s for memory (§4.9),
so it now records each process's CPU time on the same walk, keeping the maximum
per pid, process CPU time is cumulative, so the highest value seen for a pid is
its final total, and summing those recovers the tree's CPU even for processes
that exited between samples. `metrics.py` prefers that figure and records which
one it used in `cpu_measurement_scope`.

| | ex00_visitQuery |
| :--- | ---: |
| `RUSAGE_CHILDREN` | 28% |
| whole tree, sampled | **317%** |

An eleven-fold correction on the *smallest* vignette in the suite. `metrics_schema`
is bumped to **4**, so the performance gate will not compare a schema-4 run
against the schema-3 records above it.

### 4b.11 VisIt 3.4.2 loses the times of a `.visit` series, a defect in the tool

> Read §4b.13 next. This entry is correct but it is not the whole story: the
> series had no time in it for either tool to lose, and that is what was
> actually fixed.

The only finding in this document that is not a bug in this repository. It was
found by running the same eight vignettes under **3.4.1**, which is what
`MODULES.sh` loads on Shaheen and Ibex, and noticing that one CSV column
disagreed.

Reduced to fifteen lines, over the same twenty `varying*.vtk` files, same
`.visit` index, same `-noconfig`:

```python
md = GetMetaData(index_path)
```

| | `md.times` | `md.cycles` |
| :--- | :--- | :--- |
| VisIt 3.4.1 | `(0.0, 1.0, 2.0, … 19.0)` | `(0, 1, 2, … 19)` |
| VisIt 3.4.2 | `(0.0, 0.0, 0.0, …  0.0)` | `(0, 0, 0, …  0)` |

`Query("Time")` returns the same zeros on 3.4.2, so ex12 recorded them without
complaint and the blessed CSV carried a `time` column of zeros. Nothing warned.
An analysis script reading that database under 3.4.2 would have no way to tell
one timestep from another.

ex12 now takes the whole time array from the database's own metadata up front
and asserts on it:

```
[FAIL] database reports a distinct time per state
   1 distinct time value(s) across 20 states. A time series whose states all
   carry the same time is a reader defect, not data: VisIt 3.4.2 returns t=0
   and cycle=0 for every state of a .visit index over legacy VTK, where 3.4.1
   returns 0..19 over the same files.
```

with `database_distinct_times` and `database_time_span` recorded as metrics so
the history shows when it changes back.

**The baseline now holds 3.4.1's values**, because those are the correct ones
and they are what both clusters produce. So ex12 passes on 3.4.1 and fails on
3.4.2, twice over, once on the assertion, once on the `time` column, and both
messages name the cause. That is the suite working, not the suite broken.

The old code fell back to the state index when the time query failed, which
would have filled the column with `0, 1, 2 …` and hidden this completely. The
fallback is gone for exactly that reason.

### How each tool decides what time a timestep is, measured

`Query("Time")` was the wrong place to look. The question is what the *reader*
reports, and the answer differs by tool, by version, and by file format. All of
this is `GetMetaData(db).times` in VisIt and `reader.TimestepValues` in
ParaView, over the same twenty `varying*.vtk` files:

| Series | ParaView 6.1.0 | VisIt 3.4.1 | VisIt 3.4.2 |
| :--- | :--- | :--- | :--- |
| legacy `.vtk`, as shipped | `0, 1, 2 …` (file index) | `0, 1, 2 …` (file index) | **`0, 0, 0 …`** |
| legacy `.vtk` + `!TIME` lines in the `.visit` index | n/a | `0, 1, 2 …` (ignored) | `0, 0, 0 …` (ignored) |
| legacy `.vtk` + `TIME`/`CYCLE` in FieldData | `0, 1, 2 …` (ignored) | **real** | **real** |
| legacy `.vtk` + `TimeValue` in FieldData | `0, 1, 2 …` (ignored) |, |, |
| `.pvd` collection over legacy `.vtk` | **empty** (PVDReader needs XML) | n/a | n/a |
| XML `.vtr` + `.pvd` (ParaView) / `.visit` (VisIt) | **real** | **real** | **real** |

Three separate facts fall out of that:

1. **The shipped series carries no time at all.** Neither tool has ever been
   reading a time from it; both were synthesizing one from the file index, and
   agreeing by coincidence.
2. **VisIt 3.4.2 changed what it synthesizes**, from the state index to zero.
   That is the regression in §4b.11. It is only visible because the data has no
   time of its own to fall back on.
3. **`!TIME` directives in a `.visit` index are ignored** by both 3.4.1 and
   3.4.2, which is worth reporting upstream separately: that is the documented
   mechanism for giving a `.visit` series real times.

The last row is the interesting one. Converting the series to XML `.vtr` with a
`.pvd` for ParaView and a `.visit` for VisIt gives **both tools the same real
times and cycles**, on every version tested, and the files are 42% smaller
(988 KB to 576 KB per timestep). Measured:

```
ParaView 6.1.0 .pvd        TimestepValues = [0.0, 0.05, 0.1, 0.15, 0.2]
VisIt 3.4.1    .visit/.vtr times = (0.0, 0.05, 0.1, 0.15, 0.2)  cycles = (0, 100, 200, 300, 400)
VisIt 3.4.2    .visit/.vtr times = (0.0, 0.05, 0.1, 0.15, 0.2)  cycles = (0, 100, 200, 300, 400)
```

That is what a vignette about time-varying data should be reading.

### 4b.12 ex09's polydata frame was a hairline on an empty background

`polydata` is a triangulated surface, so contouring it produces a **curve**:
227 points and 218 line segments. Rendered on its own that is about 1% ink in
VisIt and 0.06% in ParaView. As a regression gate it would have passed almost
anything; as a demonstration of how each tool reads a surface it showed
nothing at all.

The pipeline was right, the picture was not, so the fix is entirely at the
rendering level. `data/make_topology_datasets.py` now records the fact it
already knows:

```json
"contour_is_lower_dimensional": true
```

and both ex09s read it. Where it is set, the **input surface is drawn
underneath**, coloured by the same scalar, and the isoline is drawn on top in
flat white at line width 4 or 5. Colouring the isoline by the scalar would be
pointless: it lies exactly on the surface, at exactly that value, so it would
be painted the colour of what is directly behind it. `vc.ensure_flat_color_table()`
builds the one-colour table VisIt needs to say "white", since a VisIt
Pseudocolor plot takes its colour from a table and has no solid-colour mode.

Queries, metrics and assertions are untouched, so what the vignette *measures*
is exactly what it measured before. Only the frame changed, and only for this
one topology: tetra, ragged and amr come back bit-identical in both suites.

**One thing this cost, worth recording.** The first attempt moved
`GetColorTransferFunction` and `RescaleTransferFunction` above the `Show()`
calls, to keep the colour setup in one place. All four ParaView frames then
came back **26.5% different**, including the three that were not supposed to
change. `Show()` auto-rescales a representation's lookup table to its own data
range the first time it colours by an array, so presetting and rescaling first
has the rescale silently undone. That is the same 26.5% as §4.16, and it is
the same failure: a frame drawn with a lookup table nobody had configured.
The lookup table is now fetched and rescaled after every `Show`/`ColorBy`, with
a comment saying why.

The image gate caught it immediately, which is the first time in this exercise
it caught a regression that was mine rather than the tool's.

### 4b.13 The time series had no time in it, `data/make_time_series.py`

§4b.11 said VisIt 3.4.2 had lost the times of a `.visit` series, and asserted
on it. That was right as far as it went and it was not the real problem.

**The shipped series never carried a time.** `data/varying_data/varying*.vtk`
contains geometry, a scalar, and nothing that says which timestep it is.
Neither tool has ever been reading a time from it; both synthesized one from
the file's position in the list, and for years they agreed by coincidence.
VisIt 3.4.2 changed what it synthesizes, from the state index to zero, and the
coincidence ended.

That is not a thing a vignette can fix, because there was nothing to read. A
time series with no time in it cannot demonstrate how two codes handle time.
It can only demonstrate how they guess.

`data/make_time_series.py` converts the series once, per machine, into XML
`.vtr` with a `.pvd` index for ParaView and a `.visit` index for VisIt, and
with `TIME` and `CYCLE` in each file's field data. Every build tested then
reads the same real values:

| | `timestep` | `cycle` | `time` |
| :--- | ---: | ---: | ---: |
| ParaView 6.1.0 | 0, 1, 2 | 0, 100, 200 | 0.0, 0.05, 0.1 |
| VisIt 3.4.1 | 0, 1, 2 | 0, 100, 200 | 0.0, 0.05, 0.1 |
| VisIt 3.4.2 | 0, 1, 2 | 0, 100, 200 | 0.0, 0.05, 0.1 |

The time is deliberately **not** the file index and the cycle step is 100, so
those three columns are three visibly different numbers. A CSV that reported
`0,0,0 / 1,1,1 / 2,2,2` would look correct and would be the loop counter
written out three times.

ex12 now reports all three in both suites, and the two CSVs agree column for
column. ParaView takes its time from the `.pvd`'s timestep attributes and its
cycle out of the dataset's field data; VisIt takes both from the database
metadata. Two different readers, two different mechanisms, the same answer,
which is the check worth having.

**ex05 and ex12 read the XML series. ex07, ex10 and ex11 keep the legacy
one**, deliberately: ex11's ParaView state exists to exercise
`LegacyVTKReader` through a saved `.pvsm`, and having both series in the
repository means the suite can show what a reader does when the data tells it
the time and what it does when the data does not.

The files are also 41% smaller, 18.8 MB against 11.1 MB for twenty timesteps,
because XML VTK is binary and compressed where the legacy format is ASCII.

The series is generated, not committed. `Testing/prepare_machine.py` builds it
and `--check` reports it stale when the source series has more files than the
manifest records.

#### And the frames now say which timestep they are

ex05's subject is a multi-timestep database, and its twenty frames used to
differ only in the data. Both suites now put the same line in the top-left
corner, reading the same values:

```
Cycle: 300    Time: 0.15
```

Each tool does it its own way, which is worth knowing if you are borrowing
from these scripts:

* **VisIt** gets a `Text2D` annotation object with the literal text
  `Cycle: $cycle    Time: $time`. VisIt expands those macros at render time
  from whatever the reader reported, so the annotation is also the most
  direct way to *see* what the reader made of a series: over the legacy files
  it reads `Time: 0` on all twenty frames under 3.4.2.
  `databaseInfoFlag` would print the same thing and is deliberately left off,
  because it also prints the database path and that would put this machine's
  directory layout into every blessed baseline.
* **ParaView** gets a `PythonAnnotation`. `AnnotateTimeFilter` formats the
  time and nothing else, and the cycle is not a pipeline concept there at all
  -- it is an array in the dataset's field data, which is why
  `ArrayAssociation` has to be set to `Field Data`. `time_value` comes from
  the filter itself.
* The ParaView expression formats with `%g` rather than a fixed number of
  decimals, to match how VisIt trims its own `$time`: `0`, `0.05`, `0.15` in
  both, not `0.00` against `0`.

Both annotations are 3% of the frame height, so they read the same size
despite the two suites using different aspect ratios. ex05's five baselines
were re-blessed in both suites and verified on ParaView 6.1.0, VisIt 3.4.2 and
VisIt 3.4.1.

#### What was ruled out first, and why

| Attempt | Result |
| :--- | :--- |
| `!TIME` directives in the `.visit` index | **Ignored** by 3.4.1 and 3.4.2 alike, in all four placements tried. That is the documented mechanism, so this is worth reporting upstream on its own. |
| `TIME`/`CYCLE` in the legacy file's FieldData | Works in both VisIt versions. **Ignored** by ParaView's `LegacyVTKReader`, which always uses the file index. |
| `TimeValue` in the legacy file's FieldData | Ignored by ParaView as well. |
| `.pvd` collection over legacy `.vtk` files | **No timesteps at all.** `PVDReader` wants XML. |
| XML `.vtr` + `.pvd` + `.visit` | Both tools, all three builds, identical real times and cycles. |

The assertion from §4b.11 stays in place. It now passes everywhere, and it
will fire again if a future reader starts collapsing a series to a single
time.

---

## 5. Known issue: ex06 image stability

`ex06_pvLargeData` differs **4.13% of pixels between two consecutive runs** on
this machine, with the same ParaView, same data and the GPU pinned, against a
baseline blessed from its own output minutes earlier. The difference is confined
to the Surface LIC on the terrain; the volume-rendered clouds are stable.

Measured, so it is not guesswork:

| Launch | Run-to-run difference |
| :--- | :--- |
| `pvbatch script.py` (no launcher, no forced offscreen) | 0.008%, stable |
| `mpirun -np 1 pvbatch --force-offscreen-rendering` (what the harness does) | 4.135% |
| Surface LIC in isolation, offscreen | 0.000%, bit-identical |

So it is not the LIC noise texture and not the GPU choice; it is something about
the forced-offscreen GLX path under the launcher. `EnhanceContrast = "LIC and
Color"` computes a histogram stretch over the rendered LIC, which amplifies any
difference into a visible one.

**Resolved with a per-vignette tolerance.** ex06 now declares its own:

```python
ctx.set_image_tolerance(0.05, "Surface LIC with contrast enhancement is not "
                              "reproducible run to run under forced-offscreen GLX")
```

The harness reads that back out of the results JSON and uses it for this
vignette only. It is declared in the vignette rather than by raising
`--image-tolerance` globally, because the two numbers are an order of magnitude
apart: the widest *legitimate* cross-backend difference anywhere in this suite is
0.39%, and a 5% global tolerance would make every other vignette blind to a real
regression in order to accommodate one LIC.

5% still leaves ex06 a real test, the volume rendering, geometry, legends and
colour maps are all compared at that threshold, and the observed noise is 4.1%.
If it starts flapping again, the next step is pinning
`EnhanceContrast = "Off"` on the LIC representation, which would likely make it
deterministic at the cost of changing the picture.

### Does ex06 run on Shaheen?

Yes. `ex06_shaheen_runScript.sbat` requests `--partition=workq`, 1 node,
8 ranks, 200 GB, and `MODULES.sh` loads the `-mesa` variant there, so it runs
under software rendering. It is also the most expensive vignette by a wide
margin: 192 s of the suite's 371 s, and 62 GB peak.

---

## 5a. Answered: do we need per-machine baselines?

**No.** One shared baseline set covers all four targets, with the image tolerance
raised from 0.1% to 0.5%. This was measured rather than assumed.

### ParaView minor version does not change pixels

ParaView 6.0.1 (Ibex) and 6.1.0 (Shaheen, local), same GPU, same data,
6.1.0-blessed baselines:

| Vignette | Verdict |
| :--- | :--- |
| ex01_pvScreenshot | **SAME**, 0.0000% |
| ex03_pvIsosurfaceAnimation (5 frames) | **SAME**, 0.0000% |
| ex10_pvColormapFidelity (4 configs) | **SAME**, 0.0000% |
| ex12_pvExtractRegression (3 frames) | **SAME**, 0.0000% |
| ex09 tetra / polydata / ragged | **SAME**, 0.0000% |
| ex09 amr | differs, a *file* incompatibility, not rendering (below) |

Bit-identical. But only after two 6.0.1-specific defects were fixed, see §4.16
and §4.17. Before those, the same comparison showed 26.5% on ex09 tetra and a
hard failure on AMR, which would have looked exactly like "we need per-machine
baselines" and was nothing of the sort.

### Backend changes pixels a little

ParaView 6.1.0 rendering through Mesa llvmpipe
(`VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow`, which is what
`run_tests.py` already sets when a `-mesa` module is loaded), against the same
GPU-blessed baselines:

| Image | Difference |
| :--- | ---: |
| ex09 tetra | 0.391% |
| ex09 ragged | 0.369% |
| ex09 amr | 0.135% |
| ex10 categorical | 0.110% |
| ex01, ex03, ex12, ex10 (other three), ex09 polydata | under 0.1%, pass as-is |

Worst case **0.39%**, and it is anti-aliasing on contour edges. So:

```bash
--image-tolerance 0.005      # 0.5%
```

covers GPU GLX, Mesa llvmpipe and (by the same argument) EGL, on one baseline
set, while still failing on a real geometry or colour-map change, those move
whole regions, not edges.

### What must NOT be shared between machines

**Generated fixtures.** Regenerate them on each machine; do not copy them.

* `data/topologies/amr_hierarchy.vthb`, 6.1.0 writes an AMR that 6.0.1 opens
  but only partially reads: 216 points and 125 cells against the 842 and 605
  that 6.1.0 sees. That is the entire remaining ex09 difference on Ibex, and it
  produces no error of its own.
* `ex11_state.pvsm`, a ParaView state file is version-locked by design.
* `ex11_visit.session`, likewise, per VisIt version.

`python3 Testing/prepare_machine.py` handles all three, and ex09 and ex11 refuse
to run against a fixture from a different ParaView rather than silently
believing it. See §2.

---

## 5b. VisIt baselines: what they are, and what they are not

The VisIt baselines in the repository dated from October 2025 and were all
replaced. Two independent reasons, and the distinction matters:

* **ex01–ex05, ex07–ex12** were blessed before the vignettes were rewritten and
  no longer matched even in size, 2048×1784 against the 2048×2048 the scripts
  now request. Nothing subtle; they were simply stale.
* **ex06** matched in size and was not stale at all. It was an **8-rank**
  render, and the suite was comparing it against a 1-rank one. See §4b.8; it
  reproduces today to within JPEG noise.

ex01–ex05 and ex07–ex12 were re-blessed on 3.4.2 under `-noconfig` at one rank,
from a run whose images were inspected first. ex06 is blessed at **eight
ranks**, matching its `.sbat` scripts, and is bit-identical run to run there.

### What is known to be portable

The same argument as §5a applies to VisIt's colour tables and only to those:
`viridis`, `plasma` and `Blues` come out of `$VISITARCHHOME/resources/colortables/`
and ship with the install, so they are identical on Shaheen and Ibex. That is
the one cross-machine question §4b.2 closes.

### Measured: VisIt 3.4.1 renders the same pixels as 3.4.2

This matters because `MODULES.sh` loads **`visit/3.4.1`** on both Shaheen and
Ibex, and the version is hard-coded a second time inside the Shaheen job
submitter in `~/.visit/customlauncher`. Local validation was on 3.4.2, so the
baselines had to be shown to transfer.

Eight vignettes, seventeen images, 3.4.2-blessed baselines, run under 3.4.1:

| Images | Verdict |
| :--- | :--- |
| ex01, ex07, ex08, ex09 (all four topologies), ex10 (all four configs), ex12 (three frames) | **SAME**, 0.0000% |
| ex11 (three frames) | ACCEPTABLE, 0.0149% |

Fourteen of seventeen bit-identical. ex11's 0.0149% is not a rendering
difference: its `.session` fixture was written by 3.4.2 and is version-locked by
design, which is why `prepare_machine.py` regenerates it per machine (§2).
Regenerate it under 3.4.1 and that difference goes too.

**So the image baselines transfer.** One set covers 3.4.1 and 3.4.2.

### Which VisIt is the reference, and until when

Decided: **this workstation stays on 3.4.2, the clusters stay on 3.4.1 until
the spring module update.** Both are 13 of 13 against the same baselines, and
the measurement above is what makes running two versions at once reasonable
rather than reckless.

Two things follow from that.

* **Both versions share one history file**, `KW61316.kaust.edu.sa`, because
  they are one machine in one rendering configuration. The version lives in
  each record, where it always has: `shaheen3-cpu` has carried 3.4.1 and
  3.4.2 records together since 2024, and the ParaView histories have carried
  5.13.1 and 6.x the same way. Comparing across versions is a large part of
  what this suite is for, so the gate reports the difference and names both
  versions rather than hiding it. It does not fail the run on it (§3, the
  performance gate).
* The version is hard-coded in **two** places that must agree, and changing
  one without the other fails as a connection that opens and then dies on a
  protocol mismatch, naming no version: `VisIt_Vignettes/MODULES.sh`, and the
  Shaheen job submitter inside `~/.visit/customlauncher`, whose
  `TFileLoadModules` writes `module load visit/3.4.1` into the engine's job
  file. When the clusters move in spring, change both, then run
  `python3 Testing/prepare_machine.py --force` there to rebuild
  `ex11_visit.session` under the new version.

What does *not* transfer is ex12's `time` column, and that turned out to be a
defect in VisIt 3.4.2 rather than a property of the baseline, see §4b.11. The
baseline holds 3.4.1's values.

### Measured: rank count changes translucent scenes and nothing else

The `.sbat` scripts request **8 ranks** on Shaheen; local runs default to one.
`--ranks 8 --machine local` now starts a real parallel engine through VisIt's
bundled mpirun (§3), so this was answered on the workstation, without queue
time.

Every VisIt vignette, 1-rank baselines, run at eight ranks:

| Images | Verdict |
| :--- | :--- |
| ex01, ex02 (5 frames), ex03 (5), ex05 (5), ex09 (4 topologies), ex10 (4 configs), ex12 (3 frames) | **SAME**, 0.0000% |
| ex04 (5 frames), the streamline animation | **ACCEPTABLE**, worst 0.0134% |
| ex06, the cyclone scene | 86% of pixels differ |

Opaque geometry is rank-invariant to the bit: twenty-seven images across seven
vignettes came back with zero differing pixels.

**ex04 is the interesting near-miss.** It is the one vignette whose *algorithm*
is partition-sensitive rather than just its compositing: integral curves are
seeded and advected per domain, so a curve that crosses a partition boundary is
integrated in pieces. The result still lands at 0.0134% worst case, seven times
inside the 0.1% default gate and forty times inside the 0.5% cross-backend
tolerance. Worth knowing it is not zero; not worth a tolerance of its own.

**ex06 is the one real exception**, and there the difference is compositing
order rather than error: overlapping translucent plots, both renders correct,
each bit-identical to itself (§4b.8).

So: **one baseline set covers every rank count, except ex06**, which is blessed
at eight ranks to match its `.sbat` scripts and disables its own image gate when
run at anything else. Nothing else needs a per-rank baseline, and Shaheen's
first VisIt suite should not go red for a rank-count reason.

One incidental fix came out of this. `compute_engine_launched` was recorded as a
**metric** in ex07, ex10 and ex12, and `metrics` is a correctness gate, so a
run at eight ranks failed all three on `expected false, got true` while every
image was bit-identical. How the engine was launched is a property of the run,
not of the result; it is a note now. `ex08_visitBackendCheck` keeps it as a
metric, because the backend is what that vignette is about.

---

## 6. Taking it to Shaheen and Ibex

The suite is version-tolerant now, so the same commands work everywhere. What
changes per site is the module, the launcher and the machine name.

### ParaView on Shaheen and Ibex

```bash
# --- Shaheen, CPU (workq) ---------------------------------------------------
source ParaView_Vignettes/MODULES.sh          # loads the -mesa variant
srun --cpus-per-task=32 --ntasks=2 -p workq --time=00:40:00 --mem=200G -A k01 --pty /bin/bash
source $SCRATCH/testing_paraview_env/bin/activate
cd $SCRATCH/Visualization_Vignettes/Testing

python test_suite.py ../ --test_type ParaView --paraview_version 6.1.0 \
  --machine_name shaheen3-cpu --machine shaheen --launcher srun \
  --image-tolerance 0.005 --non_gpu_machine \
  --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800

# --- Shaheen, GPU (ppn, EGL/L40) -------------------------------------------
source ParaView_Vignettes/MODULES.sh egl
srun --cpus-per-task=32 --ntasks=1 -p ppn -G 1 --time=00:40:00 --mem=200G -A k01 --pty /bin/bash
python test_suite.py ../ --test_type ParaView --paraview_version 6.1.0 \
  --machine_name shaheen3-ppn-gpu-L40 --machine shaheen \
  --image-tolerance 0.005 --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800
```

Before the first run on each machine:

```bash
python3 prepare_machine.py           # generates whatever is missing or stale
python3 prepare_machine.py --check   # or just verify, exits non-zero if not ready
```

Worth putting `--check` at the top of a job script. It is a two-second probe and
it turns "the fixtures were from the wrong ParaView" from a confusing numeric
failure two hours into a queue into a refusal to start.

`--machine_name` must stay stable per site: it names the metrics file, and the
performance gate needs two runs under the same name before it can fire.

Three things to expect and not be alarmed by:

* **ex11 will not run in a batch allocation without a display.** It needs
  `xvfb-run` and `--no-offscreen`, as locally. If `xvfb` is not available on the
  compute nodes, skip it there and keep it as a local/CI gate.
* **ex06 needs 62 GB and 192 s**, single-rank. At 8 ranks on `workq` it will be
  different on both counts; that is the point of running it there.
* **`--ranks > 1` has never been exercised for ParaView.** The harness supports
  it now but every baseline in the repo was blessed at one rank. Expect
  partition-boundary differences in `contour_points` and integrated quantities
  the first time; that is real information, not a bug.

### VisIt on Shaheen and Ibex

```bash
# --- Shaheen, CPU (workq) ---------------------------------------------------
source VisIt_Vignettes/MODULES.sh             # loads visit/3.4.1
source $SCRATCH/testing_visit_env/bin/activate
cd $SCRATCH/Visualization_Vignettes/Testing

python test_suite.py ../ --test_type VisIt --visit_version 3.4.1 \
  --machine_name shaheen3-visit-cpu --machine shaheen --launcher srun \
  --nodes 1 --ranks 8 --image-tolerance 0.005 --non_gpu_machine \
  --timeout 1800

# --- Shaheen, GPU (ppn) -----------------------------------------------------
python test_suite.py ../ --test_type VisIt --visit_version 3.4.1 \
  --machine_name shaheen3-visit-ppn --machine shaheen \
  --nodes 1 --ranks 8 --image-tolerance 0.005 --timeout 1800
```

Unlike ParaView, **no vignette is excluded**: VisIt's ex11 restores a session
and needs no display.

Two VisIt-specific things to settle before the first of these runs, both of
which are cheap to answer locally and expensive to discover in a queue:

1. **`MODULES.sh` loads `visit/3.4.1` on both clusters.** The version is
   hard-coded in two places that must agree, there, and in the Shaheen job
   submitter inside `~/.visit/customlauncher`, which writes
   `module load visit/3.4.1` into the engine's job file. A client and an engine
   from different builds fail as a connection that opens and then dies on a
   protocol mismatch, naming no version. Change one and you must change the
   other. The baselines themselves transfer: 3.4.1 and 3.4.2 render the same
   pixels (§5b). Regenerate `ex11_visit.session` under 3.4.1 on each cluster,
   which `prepare_machine.py` does.
2. **The `.sbat` scripts ask for 8 ranks**, so pass `--ranks 8` to
   `test_suite.py` as well, the commands above do. Opaque vignettes are
   bit-identical at any rank count and ex06 is blessed at eight, so the
   baselines are already the right shape (§5b). What has not been checked at
   eight ranks is ex02–ex05, the animations.

---

## 7. Next steps

Both suites run clean locally, on all three builds, and every question that
could be answered on a workstation has been. The clusters are next.

1. **Shaheen CPU** (`workq`), both suites, collect numbers. Pass `--ranks 8`
   for VisIt, to match the `.sbat` scripts and ex06's baseline.
2. **Shaheen GPU** (`ppn`, EGL/L40 for ParaView).
3. **Ibex**, ParaView 6.0.1 and VisIt 3.4.1 are both expected to work
   unchanged, given §5a and §5b respectively. Neither has been run.
4. **Spring: move the clusters to 3.4.2.** Decided rather than open, and
   recorded in §5b: this workstation stays on **3.4.2**, Shaheen and Ibex
   stay on **3.4.1** until the spring module update, and the two are
   validated against the same baselines in the meantime. When the clusters
   move, change `visit/3.4.1` in `VisIt_Vignettes/MODULES.sh` **and** in the
   Shaheen job submitter inside `~/.visit/customlauncher`, which hard-codes
   it separately. The suite itself needs nothing.

Deferred deliberately, with reasons, rather than forgotten:

* **ParaView at `--ranks > 1` has never been exercised.** The harness supports
  it; no baseline has ever been blessed above one rank.
* **Miniapps and in-situ** are out of scope for this pass by request.
