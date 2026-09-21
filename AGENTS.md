# AGENTS.md

Working notes for an AI coding assistant, or for a human who has not been
here before. `AGENTS.md` is the cross-tool convention; `CLAUDE.md` points
here so there is one file to keep current rather than two to keep in sync.

This file is the short version. The reasoning, the measurements and the
defect log live in `Testing/LOCAL_VALIDATION.md`, and the harness reference
lives in `Testing/README.md`. Read those before changing behaviour; read this
before changing anything.

---

## What this repository is

Two parallel suites of thirteen vignettes each, `ParaView_Vignettes/ex00..ex12`
and `VisIt_Vignettes/ex00..ex12`, run by one harness in `Testing/`. They serve
two purposes at once, and both matter:

1. **Regression testing** across ParaView and VisIt versions, machines
   (workstation, Shaheen, Ibex) and rendering backends (GPU GLX, Mesa, EGL).
2. **Demonstration.** Users read these to see how each tool does a thing, and
   to compare the two. A vignette that passes its gates while showing nothing
   useful has half failed. ex09's polydata frame was a hairline on black for
   exactly that reason, and it counted as a defect.

When those two purposes pull in different directions, say so rather than
quietly optimising for the gates.

---

## Before you run anything

```bash
export PARAVIEW_PATH=/path/to/paraview/bin      # or module load
export VISIT_PATH=/path/to/visit/bin
python3 Testing/prepare_machine.py              # build what is missing
```

Four of the suite's inputs are **generated per machine and not committed**,
and none of them announces a mismatch when it is wrong:

| Fixture | Locked to |
| :--- | :--- |
| `data/topologies/` | a ParaView major.minor |
| `ParaView_Vignettes/ex11_pvStateVerification/ex11_state.pvsm` | a ParaView major.minor |
| `VisIt_Vignettes/ex11_visitStateVerification/ex11_visit.session` + `ex11_series.visit` | a VisIt version, and absolute paths |
| `data/varying_series_xml/` | its source series in `data/varying_data/` |

`test_suite.py` now runs `prepare_machine.py --check` as a preflight and
refuses to start when any of them is stale. `--skip-preflight` exists; it is
an escape hatch, not a default.

---

## Running, blessing, recording

```bash
cd Testing

# normal run
python test_suite.py ../ --test_type ParaView --paraview_version 6.1.0 \
  --machine_name KW61316.kaust.edu.sa --timeout 1800

# anything experimental
python test_suite.py ../ ... --no-metrics

# record a baseline, having LOOKED at output/ first
python test_suite.py ../ ... --test_number 9 --bless --no-metrics
```

Rules that are not negotiable:

* **`--no-metrics` on every debugging, blessing, experimenting and
  rank-checking run.** `performance_metrics_<machine>.json` is tracked in git
  and is the long-term record, not a log of everything anyone ever ran. One
  recorded run per configuration, at the end, tagged with `--run-id`.
  `manage_metrics.py --remove-run <id> -y` undoes one precisely.
* **Never bless without looking at the images.** `--bless` is the only thing
  that creates a baseline; a missing baseline is a failure by design. A
  blessed wrong picture is invisible forever after.
* **`--machine_name` names a configuration, not a run.** One history per
  machine and rendering configuration, tool version recorded inside each
  record. That is the existing convention (`ibex-cpu`, `ibex-egl-a100`,
  `shaheen3-ppn-gpu-L40`).
* **`metrics_schema` gets bumped whenever a recorded field changes meaning.**
  It is 4. The performance gate and the plots both refuse to compare across
  that boundary, which is the only thing stopping a definition change from
  reading as a regression.

---

## Things that will cost you an afternoon

Each of these was found the expensive way. They are written up with the
measurements in `Testing/LOCAL_VALIDATION.md` §4 and §4b.

**VisIt**

* `visit -cli` **exits 250 whether it worked or not** -- clean run, Python
  traceback and crashed engine alike. The verdict comes from the vignette's
  own results JSON, and only when that file was written after the run started.
* **`-noconfig` hides 129 of VisIt's own colour tables**, not just the user's.
  `viridis`, `plasma`, `magma`, `Blues` all ship as `.ct` files that
  `-noconfig` stops loading. VisIt does not refuse an unknown table name: it
  accepts it, fails the plot asynchronously, and every later query on that
  plot returns `None`. Use `vc.ensure_color_table()`.
* **`getattr(visit_object, "name", default)` does not fall back.** VisIt's
  attribute objects raise `ValueError`, not `AttributeError`, and `dir()` on
  them raises too. Use `vc.visit_attr()`.
* A host profile in `~/.visit` can silently start a **different VisIt install**
  with a different engine topology. That is the other half of why `-noconfig`
  is not optional.

**ParaView**

* **pvbatch segfaults on `sys.exit()`** when a render window exists and there
  is no X display, which is every offscreen batch run. Use
  `vc.exit_vignette()`.
* **`Show()` auto-rescales a lookup table** the first time it colours by an
  array. Set the preset and rescale *after* every `Show`/`ColorBy`, or the
  rescale is silently undone. This cost a 26.5% whole-frame regression twice.
* Preset names moved in 6.1 (`Viridis (matplotlib)` -> `Viridis`) and the
  three versions in use fail differently for a name they lack. Use
  `vc.apply_color_preset()`.

**Both**

* The legacy `data/varying_data/*.vtk` series **carries no time and no cycle**.
  Both tools synthesize one from the file index. ex05 and ex12 read
  `data/varying_series_xml/` instead, which has real values; ex07, ex10 and
  ex11 keep the legacy series on purpose.
* **ex06's VisIt baseline is blessed at 8 ranks**, matching its `.sbat`.
  Translucent geometry composites in a partition-dependent order, so it
  disables its own image gate at any other rank count, loudly. Everything else
  is bit-identical at 1 and 8 ranks.

---

## Conventions

* `Testing/vignette_common.py` is imported by three different interpreters:
  pvbatch's, VisIt's CLI, and system python3. **It must never import
  `paraview` or `visit` at module level.** Tool callables are passed in as
  arguments instead.
* Every vignette writes a results JSON that the harness gates on. Add a
  measurement with `ctx.add_metric()`, an assertion with `ctx.assert_true()`,
  a CSV with `ctx.extract_path()`.
* Environment-dependent facts go in `ctx.notes`, not `ctx.add_metric()`.
  `metrics` is a correctness gate; recording how the engine was launched there
  makes every rank change look like a regression.
* Comments explain **why**, especially where the code looks wrong and is not.
  Most of this file exists because someone later will reasonably think "that
  defensive branch is pointless" and delete it.
* No em dashes in prose.

---

## Where things are

| | |
| :--- | :--- |
| `Testing/README.md` | harness reference: gates, arguments, cluster recipes |
| `Testing/LOCAL_VALIDATION.md` | what was changed and why, with measurements |
| `Testing/prepare_machine.py` | generated fixtures, `--check` as a preflight |
| `Testing/manage_metrics.py` | inspect and prune the committed history |
| `Testing/plot_metrics.py` | trend and comparison plots from that history |
| `data/make_topology_datasets.py` | ex09's four mesh topologies |
| `data/make_time_series.py` | the XML time series with real times |

Out of scope unless asked: `Miniapps/` and the in-situ work.
