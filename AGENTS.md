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
python test_suite.py ../ --test_type ParaView --paraview_version 6.2.0 \
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
* **The shared baselines are the workstation's.** Every image, numeric and
  CSV baseline under `Testing/Baseline/` was blessed on
  `KW61316.kaust.edu.sa` (ParaView 6.2.0 since Nov 2026, 6.1.0 before; GPU GLX), and the CI's Mesa runner
  passes against them. That host blesses the shared set; `--bless` from any
  other host is refused unless `--bless-shared` says it is deliberate.
* **Image baselines can be per machine; nothing else is.** Every renderer
  draws its own Surface LIC noise and Mesa shades a few levels off a GPU, so
  `--machine-baselines` judges images against
  `Testing/Baseline/<machine_name>/` (falling back to the shared file per
  image) and `--bless --machine-baselines` records them there. Once the
  directory exists it is used automatically. Bless only the images that
  genuinely differ by renderer (ex06 on `shaheen3-cpu`, 21 Oct 2026), after
  looking at them; a per-machine bless touches nothing else, and numeric, CSV
  and text baselines stay shared.
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
* **`exit_vignette(0)` returns; it does not exit.** A clean run must fall
  off the end of its script so MPI satellites are released, so the call is
  only meaningful as the last statement. Anything that must stop early, such
  as `ctx.skip()`, calls `sys.exit(0)` itself, which is safe before any
  render window exists. When `skip()` used `exit_vignette(0)`, ex06 ran on
  without its data, rendered an empty scene and overwrote its own skipped
  verdict with "ok", failing the CI image gate (run #99, 21 Oct 2026).
* **`Show()` auto-rescales a lookup table** the first time it colours by an
  array. Set the preset and rescale *after* every `Show`/`ColorBy`, or the
  rescale is silently undone. This cost a 26.5% whole-frame regression twice.
* Preset names moved in 6.1 (`Viridis (matplotlib)` -> `Viridis`) and the
  three versions in use fail differently for a name they lack. Use
  `vc.apply_color_preset()`.
* ParaView 6.2 renamed or changed three things the vignettes touch, each
  handled so 6.0, 6.1 and 6.2 all pass the same baselines: the contour
  normals of a rectilinear input are called `Gradients` (ex03), the
  `PythonAnnotation` `CYCLE` variable is an int rather than an array (ex05),
  and Contour on overlapping AMR no longer skips blanked coarse cells (ex09).
  `Testing/LOCAL_VALIDATION.md` §4.18 has the details.

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

## How work is organized

Shared with the other KVL repositories so every agent works the same way.

* **Issue first.** Every piece of work that ships as one PR has a GitHub
  issue with five sections: Problem (in James's words), Done when (what James
  will see when it works), Out of scope, Risk (what it touches that is real or
  shared, what needs James's OK), Docs (which pages change). A phase or larger
  effort gets a short parent issue with a task list of its children and a
  `phase::<n>` label.
* **Work starts on James's go.** No file changes without an issue and his go
  on it; reading to understand needs neither.
* **Status labels live on issues only**: `status::refining` (being written),
  `status::ready` (James said go), `status::in-progress`, `status::merged`
  (PR in, issue open until the result is checked), `status::deferred`
  (agreed for later). The owner closes the issue after checking the merged
  result.
* **One PR per issue, from a worktree.** Branch `<issue>-<short-name>` made
  with `git worktree add <dir> -b <branch> origin/master`; never edit the main
  checkout. The PR says "Related to #N", never "Closes", "Fixes" or
  "Resolves" (those close the issue at merge, before it is checked).
* **James merges.** `master` is protected. Say "ready to merge" only after
  the last push and a green pipeline, and push nothing after that.
* **Docs ship with the change** in the same PR.
* **Stay in scope.** Anything else becomes a comment or a new issue, never a
  quiet fix. Ask instead of half baking a choice.
* **Subagents** get a precise question and return facts with sources (file,
  line, time); the owning session makes the changes.
* **Shared machines.** CI runs on the self-hosted runner `z2n-fe`, which has
  no CPU cap yet; tell the KVL Coordinator session before adding CI load.
* **No secrets** in git, docs, commit messages or chat; print key names or
  masked values only.

---

## The Gray-Scott miniapp (`Miniapps/gray-scott`)

A 3D reaction-diffusion simulation (U and V, 7-point Laplacian, periodic in
all three directions, MPI Cartesian decomposition with one halo layer)
feeding in situ and in transit backends: VTK PVTI files, Catalyst 2
(ParaView), Ascent, ADIOS2 (BP5, SST) and Kombyne-lite. The work on it is
planned in phases, each a parent issue: #11 (bootstrap), #18 (stencil
audit, sanitizers, regression tests), #28 (in situ ghosts, zero-copy,
performance logging), #38 (GPU and hybrid modes), #46 (Ascent features,
ADIOS2 in transit).

**Rules that hold now**

* **Bare metal first.** Develop and test natively on the workstation with
  the CMake presets in `Miniapps/gray-scott/CMakePresets.json`; machine-local
  paths go in a gitignored `CMakeUserPresets.json`. The top-level
  `Dockerfile` is a downstream distribution artifact: do not build inside it
  or change it as part of miniapp work.
* **VTK is required.** The VTK logger is used throughout. VTK and Catalyst
  must come from the same ParaView build that Catalyst loads at run time, or
  two VTKs end up in one process; the workstation uses a ParaView 6.2 source
  build (#19).
* **Backend equivalence is the headline rule.** Every backend (PVTI,
  Catalyst, Ascent, ADIOS2, Kombyne) does roughly the same thing with the
  same data, so results across them can be claimed equivalent. A change to
  one backend's mesh, ghosts or fields is a change to all of them, or a
  recorded, measured exception.
* **Measure everything.** Every code path that runs per step gets a named
  timer, and every run writes its metadata (git commit, machine, compiler,
  MPI, ranks and decomposition, grid, backend and version, settings) next to
  its numbers, so results can go straight into papers. Logging stays cheap,
  and off by default where it costs. The structured log is #26.

**Target invariants** (goals; each says where the code is today and which
phase makes it true; update the line when that changes)

* **Zero-copy.** Arrays handed to Conduit or VTK reuse the simulation's own
  pointer (`assert(wrapped_ptr == raw_sim_ptr)`), and nothing allocates in
  the timestep loop. *Today:* Ascent, Catalyst, Kombyne and PVTI copy every
  step through `u_noghost()`; ADIOS2 already passes the simulation array to
  a deferred `Put()`. *Made true in phase 3* (#20 to #25).
* **Ghost cell tagging.** Halo cells are flagged (Conduit Blueprint ghost
  field, `vtkGhostType` for ParaView) so pipelines drop duplicate boundaries
  and seams disappear; each cell is owned by exactly one rank. *Today:*
  untagged, and the Catalyst adaptor shifts each rank's mesh until the pieces
  touch instead. *Made true in phase 3* (#20, #21, #24).
* **Numerical equivalence.** 1 rank matches N ranks within 1e-12 relative
  (the fields themselves should match bitwise; only reductions differ by
  order). *Today:* true with `noise = 0`; with noise on, each rank seeds its
  own generator from `std::random_device`, so no two runs match. *Made true
  with noise in phase 2* (#14, enforced by #15); extended to CPU vs GPU in
  phase 4 (#33).
* **Four hybrid modes.** Simulation on GPU or CPU, visualization on GPU or
  CPU, with data moved only when a backend on the other side asks.
  *Today:* no GPU code. *Phase 4* (#31, #34). ParaView-Catalyst stays CPU
  only.

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
| `Miniapps/gray-scott/` | the Gray-Scott miniapp; see its section above and its README |

The in situ vignettes (`In_Situ_Vignettes/`) are out of scope unless asked.
