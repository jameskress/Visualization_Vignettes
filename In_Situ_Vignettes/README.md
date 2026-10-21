# In Situ Visualization Vignettes at KAUST

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

---

## In situ at KAUST: the options

*This section is the overview that used to be this directory's whole README; the
vignettes above are the tests behind it.*

Welcome to the KAUST In Situ Vignettes! This repository serves as a guide and resource for integrating and utilizing *in situ* visualization and analysis with your simulations. 

### Why Use In Situ Visualization?
As simulation sizes and data output grow, writing all data to disk is increasingly becoming a major bottleneck. *In situ* visualization tackles this by processing data while the simulation is running in memory. Key benefits include:
- **Faster simulations & more throughput:** Eliminates I/O wait times, allowing your simulation to run significantly faster.
- **Increased simulation resolution:** Run at higher temporal and spatial resolutions since you aren't bottlenecked by disk storage limits.
- **Keep only what you need:** Extract features, generate images, or save reduced datasets on the fly.
- **Reduced I/O helps the community:** Less strain on shared supercomputing file systems benefits all users on the cluster.
- **Optimized performance:** Reduced storage requirements keep overall system and simulation performance highly optimal.

---

### Featured: The Gray-Scott Miniapp
**[Explore the Miniapp Here](https://github.com/jameskress/Visualization_Vignettes/tree/master/Miniapps/gray-scott)**

We are actively expanding our *in situ* support across multiple frameworks. To demonstrate this, we have developed a detailed 3D reaction-diffusion miniapp (Gray-Scott). This single repository provides a working example of how to instrument a simulation to concurrently use **ParaView Catalyst**, **Ascent**, and **ADIOS2**. It serves as an excellent starting point for researchers looking to study true *in situ* integrations before adding them into their own codebases.

---

### In Situ Capabilities & Supported Options at KAUST

#### 1. Inshimtu
Developed by the KAUST Visualization Core Lab (KVL), Inshimtu is a lightweight *in situ* ‘shim’ designed for existing, unmodified simulations.
- Works directly with files currently written by the simulation.
- Leverages Catalyst and ParaView vis-pipelines.
- Provides a very low barrier to entry.
- Great for trying out *in situ* capabilities without the heavy commitment of a full bespoke code integration.
- **Read the Kitware Article:** [Cyclone Chapala Simulation with ParaView Catalyst through KAUST's Inshimtu Library](https://www.kitware.com/cyclone-chapala-simulation-with-paraview-catalyst-through-kaust-imshimtu-library/)
- **Repository:** [Inshimtu-basic on GitHub](https://github.com/kaust-vislab/Inshimtu-basic)

#### 2. ParaView Catalyst
Directly integrate ParaView's powerful visualization and analysis functionalities into your simulation code. Catalyst processes data in memory, meaning you can configure complex visualization pipelines without writing large data streams to disk.
- [ParaView Catalyst Documentation](https://catalyst-in-situ.readthedocs.io/en/latest/index.html)
- **Video Resource:** Check out KVL's comprehensive workshop on basic Catalyst usage: [Scientific Visualization 210: ParaView ~ In Situ Visualization using Catalyst](http://www.youtube.com/watch?v=oMudj6EUy3g).

#### 3. Ascent
Ascent is a many-core capable, flyweight *in situ* visualization and analysis infrastructure. It is highly optimized for modern HPC architectures and requires minimal overhead.
- [Ascent Documentation](https://ascent.readthedocs.io/en/latest/)

#### 4. ADIOS2
More than just an *in situ* tool, ADIOS2 is a full-scale data management framework. It is highly effective at aiding in better I/O performance, enabling *in situ* workflows, in-transit visualization, and data reduction.
- [ADIOS2 Documentation](https://adios2.readthedocs.io/en/latest/)

#### 5. VisIt Libsim
Similar to Catalyst but native to the VisIt ecosystem, Libsim allows you to tightly couple VisIt's analysis tools directly to your simulation code for live processing.
- [VisIt In Situ Tutorial](https://www.visitusers.org/index.php?title=VisIt-tutorial-in-situ)

#### 6. VTK-m
VTK-m is a scientific visualization toolkit designed specifically for emerging multi-core and many-core processor architectures. It serves as the heavy-lifting backbone for tools like Ascent, but can also be used independently alongside other libraries to enable highly optimized *in-transit* visualization.
- [VTK-m Documentation](https://m.vtk.org/)

---
*For more information or assistance with implementing these tools in your workflow, please reach out to the KAUST Visualization Core Lab.*
