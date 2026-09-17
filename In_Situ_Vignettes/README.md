# In Situ Vignettes

Executable vignettes that exercise the *coupling* between a simulation and an
in situ backend — the adapter layer, the ghost/topology contract, the
trigger logic, and the failure behaviour — rather than the rendering that
sits downstream of it.

The ParaView and VisIt vignettes answer *"how do I make this picture?"*.
These answer *"is the data I handed the backend actually the data I meant,
and what happens when something goes wrong?"* Every vignette here is a test
first and an example second: it exits non-zero when its contract is violated.

---

## Why these exist

An audit of `Miniapps/gray-scott` found that the coupling layer, not the
rendering, is where the defects live:

| Symptom found in the miniapp | Vignette that would have caught it |
| --- | --- |
| Adapters call `Node::set()` (deep copy) where `set_external()` was intended, and materialise the field 2–3× per output step | `is00_zeroCopyAdapter` |
| Subdomain origins nudged with an integer-division fudge, correct only when `L % nranks == 0`; ghost layer dropped entirely | `is01_ghostCorrectness` |
| Output gating duplicated between `main.cpp` and `writerKombyne.cpp`, able to disagree | `is02_thresholdTrigger` |
| `catch (...) {}` around the actions-file load: a missing YAML means *no visualization at all*, silently | `is03_inTransitFailover` |
| `if (!sim.size_x) return;` before a collective call — a rank with an empty subdomain deadlocks the job | all of them (`Checks::check_all` is collective by construction) |

---

## Layout

```
In_Situ_Vignettes/
├── README.md                     # this file
├── CMakeLists.txt                # standalone build tree; registers CTest cases
├── cmake/                        # shared backend-discovery modules
├── common/
│   └── insitu_harness.h          # GhostedBlock, rss_kb(), collective Checks
└── isNN_<name>/
    ├── CMakeLists.txt            # add_insitu_vignette(...) — one call
    ├── isNN_<name>.cpp           # the vignette
    ├── isNN_validate.py          # independent verdict on the emitted log
    ├── isNN_actions.yaml         # Ascent actions   (when a backend is driven)
    ├── isNN_catalyst.py          # Catalyst script  (when a backend is driven)
    ├── run_local.sh              # developer workstation entry point
    ├── isNN_ibex_runScript.sbat  # cluster entry points, matching the
    ├── isNN_shaheen_runScript.sbat  #   convention in the PV/VisIt vignettes
    └── Testing/
        └── Baseline/             # only for vignettes that render
```

Two rules keep this tree usable:

1. **A vignette never links the miniapp.** Simulation-shaped data comes from
   `common/insitu_harness.h`. A vignette that needs `gray-scott` to compile
   cannot be used to debug `gray-scott`.
2. **A vignette owns its verdict.** It exits non-zero on failure. Nothing
   downstream has to diff an image or scrape a log to find out whether it
   worked — though `isNN_validate.py` does re-check the log independently,
   so a vignette that starts exiting 0 while printing `FAIL` is still caught.

---

## The initial five

### `is00_zeroCopyAdapter` — implemented

Proves that handing the simulation's buffer to Conduit is free. Four
collective checks: pointer identity under `set_external`, aliasing
(a write through the sim buffer is visible through the node), RSS flatness
across N publish cycles measured against the deep-copy path, and
`blueprint::mesh::verify`.

Needs Conduit and MPI only — no renderer, no display, no GPU. This is the
vignette that still runs when the graphics stack is broken.

```bash
cmake -S In_Situ_Vignettes -B build-insitu -DConduit_DIR=<...>/lib/cmake/conduit
cmake --build build-insitu -j
ctest --test-dir build-insitu --output-on-failure
```

### `is01_ghostCorrectness` — next

Decompose a known analytic field across 1, 2, 4 and 8 ranks with a global
extent deliberately **not** divisible by the rank count, publish it with the
ghost layer and a `vtkGhostType` mask, run a contour through the backend, and
assert that the surface has no seams and no duplicated cells at subdomain
boundaries. Compares the multi-rank result against the single-rank result
rather than against a stored image, so it is resolution- and
version-independent.

This is the vignette that fails today: `writerCatalyst.cpp:173` and
`writerAscent.cpp:58` both shift the origin by `(dx / nx) * spacing` — integer
division — and `ghost_cell_mask()` in `gray-scott.cpp:120` marks one layer too
many as ghost.

### `is02_thresholdTrigger` — next

Data-driven output: publish every step, but only *render* when a field
statistic crosses a threshold. Asserts that the trigger fires on exactly the
expected step set, that the decision is identical on every rank (a
rank-local trigger decision splits a collective call and hangs), and that the
non-firing steps cost approximately nothing.

Replaces the fixed `plotgap` gating that currently lives in two places at
once — `main.cpp:325` and again in `writerKombyne.cpp:65`.

### `is03_inTransitFailover` — next

Launch producer and consumer as an MPMD pair over ADIOS2/SST. Then break it
on purpose: kill the consumer mid-stream, start the consumer before the
producer, point at a missing actions file, and give the consumer more ranks
than the global extent has planes. Assert the producer survives, that a
`QueueFullPolicy` of `Discard` really discards, and — the point of the
vignette — that every one of those failures produces a diagnostic instead of
a silent no-op.

The last case is a live bug: `ReadRepartition` in `adios_reader.cpp:178`
computes `slab_size = global_dims[0] / size`, which is 0 when ranks outnumber
planes, and then adds an overlap plane on top of it, producing an
out-of-range selection.

### `is04_liveSteering` — next

Bidirectional coupling: the backend writes a parameter back to the running
simulation (a reaction-rate change, a pause, a request for a different
extract) and the simulation picks it up at a step boundary. Asserts that
every rank observes the same steering value at the same step, and that a
steering channel that goes away leaves the simulation running rather than
blocked.

---

## Adding a vignette

```cmake
# In_Situ_Vignettes/is0N_myVignette/CMakeLists.txt
add_insitu_vignette(is0N_myVignette
  SOURCES is0N_myVignette.cpp
  LIBS    conduit::conduit conduit::conduit_blueprint ascent::ascent_mpi
  RANKS   1 2 4          # one CTest case per rank count
  ARGS    --size=32
)
```

then add `add_subdirectory(is0N_myVignette)` to `In_Situ_Vignettes/CMakeLists.txt`.

Use `insitu::Checks` for every assertion. It reduces across the communicator,
so a failure on one rank is a failure on all of them and no rank takes a
different branch into a collective call.
