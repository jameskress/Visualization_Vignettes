# Gray-Scott miniapp

A 3D reaction-diffusion simulation that feeds the in situ and in transit
visualization backends used across the Visualization Vignettes: VTK PVTI
files, Catalyst 2 (ParaView), Ascent, ADIOS2 (BP5 files and SST staging) and
Kombyne-lite. It is small enough to read in an afternoon and large enough to
run on thousands of cores, which makes it a fair test bed for comparing how
those backends get, move and render the same data.

It solves the [Gray-Scott model](https://doi.org/10.1126/science.261.5118.189)
for two chemicals, U (consumed) and V (produced):

```text
du/dt = Du * lap(u) - u * v^2 + F * (1 - u) + noise * r      r in [-1, 1), from (seed, step, x, y, z)
dv/dt = Dv * lap(v) + u * v^2 - (F + k) * v
```

with a 7-point Laplacian on a unit-spaced grid (the stencil sum is divided
by 6) and a forward Euler step of size `dt`.

Contents: [how it works](#how-it-works) ·
[prerequisites](#prerequisites) · [build](#build) · [run](#run) ·
[parameters](#parameters) · [outputs](#outputs) ·
[troubleshooting](#troubleshooting) · [more documentation](#more-documentation)

---

## How it works

The global grid is `L x L x L` points, periodic in all three directions.
MPI splits it into a 3D grid of blocks (`MPI_Dims_create`,
`MPI_Cart_create`); each rank owns one block and stores it with one extra
layer of halo points on every face, filled from its neighbours each step.

```text
  Global domain L^3, periodic, split over P = px * py * pz ranks (here 2 x 2 x 1)

        +-----------+-----------+          One rank's block, one face shown
       /  rank 2   /  rank 3   /|
      +-----------+-----------+ |          h h h h h h h h      h = halo point,
     /  rank 0   /  rank 1   /| +          h o o o o o o h          copy of the
    +-----------+-----------+ |/           h o o o o o o h          neighbour's
    |           |           | +            h o o o o o o h          edge
    |  local    |  local    |/             h o o o o o o h      o = owned point
    |  block    |  block    +              h h h h h h h h
    +-----------+-----------+
      wraps around in x, y and z           size_x + 2 points per row

  Each step, on every rank:

    exchange halos      MPI_Sendrecv with each neighbour, faces xy then xz then yz
          |             (MPI derived datatypes, no packing buffers)
          v
    update interior     7-point Laplacian + reaction terms, forward Euler
          |
          v
    every plotgap steps
          |
          v
    writer ------> none | pvti | catalyst_io | catalyst_insitu | ascent | adios | kombyne
                     |       |          |             |            |       |        |
                   (skip) VTK files  ParaView     ParaView      Ascent  ADIOS2  Kombyne-lite
                                     writes files pipeline     actions  BP5/SST
                                                  in situ
```

The goal for every backend is the same: hand the solver's arrays over
without copying, tag ghost cells, and give the same result across backends
and across rank counts. Results already match across rank counts, noise
included: the noise depends only on the seed, the step and the global
position. The backends do not meet the rest yet: PVTI copies and converts
to float, and Catalyst tags no ghosts. Phase 3 (#20 to #25) closes these
gaps. The
[build and run guide](docs/build-and-run-guide.md) covers each backend in
detail.

---

## Prerequisites

Measured on the KVL workstation; other Linux machines need the same pieces.

| | Required | Workstation |
| :--- | :--- | :--- |
| C++17 compiler | yes | GCC 9.5 |
| MPI | yes | Open MPI 4.1.2 (`mpicxx`, `mpirun`) |
| CMake | 3.22 or newer | 3.22.1 system; 3.31 under `~/packages` for building ParaView 6.2 |
| VTK | yes (the VTK logger is used throughout) | from the ParaView 6.2 source build, `~/packages/paraview-src/build_6.2.0/install` |
| Catalyst 2 | for `catalyst_*` output | same ParaView build (must match the VTK above) |
| Ascent | for `ascent` output | optional |
| ADIOS2 | for `adios` output and the in transit reader | optional |
| Kombyne-lite | for `kombyne` output | optional, free version 1.5 |
| GPU | not yet | two RTX A5000; GPU support is planned (`ENABLE_GPU`, off) |

VTK and Catalyst must come from the same ParaView build that Catalyst loads
at run time, or two copies of VTK end up in one process.

---

## Build

The miniapp ships CMake presets. They keep every optional backend off and
put each build under `build/<preset>`. The one machine-local path, `VTK_DIR`,
goes in `CMakeUserPresets.json`, which git ignores.

```bash
cd Miniapps/gray-scott
cp -n CMakeUserPresets.json.example CMakeUserPresets.json   # -n keeps an existing file; edit VTK_DIR if your ParaView lives elsewhere
cmake --list-presets
cmake --preset my-host-cpu
cmake --build --preset my-host-cpu -j
```

The binary is `build/my-host-cpu/gray-scott`.

| Preset | What it is |
| :--- | :--- |
| `host-cpu` | Release, MPI and VTK only |
| `host-cpu-debug` | Debug |
| `host-cpu-timers` | Release with `ENABLE_TIMERS` (per-step timers) |
| `my-host-cpu` | your copy of `host-cpu` with local paths, from the example file |

To turn a backend on, add it to your user preset with its path, for example:

```json
"cacheVariables": {
  "VTK_DIR": "$env{HOME}/packages/paraview-src/build_6.2.0/install/lib/cmake/paraview-6.2/vtk",
  "ENABLE_CATALYST": "ON",
  "catalyst_DIR": "$env{HOME}/packages/paraview-src/build_6.2.0/install/lib/cmake/catalyst-2.0"
}
```

The other switches are `ENABLE_ASCENT` (`Ascent_DIR`), `ENABLE_ADIOS2`
(`ADIOS2_DIR`), `ENABLE_KOMBYNELITE` (`kombynelite_DIR`) and
`BUILD_ANALYSIS_READER` (the ADIOS2 in transit reader). Ascent and Kombyne
cannot be enabled together. Building each backend SDK is covered in the
[build and run guide](docs/build-and-run-guide.md#how-to-build-locally).

---

## Run

Every run takes one settings file:

```bash
mpirun -np 1 build/my-host-cpu/gray-scott --settings-file=configs/miniapp-settings/settings-none.json
mpirun -np 2 build/my-host-cpu/gray-scott --settings-file=configs/miniapp-settings/settings-none.json
```

`settings-none.json` is a 64^3 grid for 100 steps with no output, a few
seconds on one core: the quickest check that a build works. Other settings
files under `configs/miniapp-settings/` turn on each backend. Add
`--logging-level=TRACE` for more detail (levels: `OFF`, `ERROR`,
`WARNING`, `INFO`, `TRACE`).

The step count, grid and output are all in the settings file; the
[parameters](#parameters) table explains each one.

---

## Parameters

From `simulation/settings.cpp`. Every key is required except those marked
optional; a settings file that leaves out a required key stops the run with
an error. The last column is the value in the code's constructor, for
reference only, except for the optional keys, where it is the value used
when the key is missing. The shipped files set every key
(`settings-none.json` uses L 64, 100 steps, Du 0.2, Dv 0.1, F 0.01, k 0.05,
dt 2.0, noise 1e-7).

All quantities are dimensionless. The solver works on a grid of spacing 1.
The backends publish the grid with spacing 0.1, so in ParaView,
VisIt or any output file the domain is 0.1 * L wide: divide output
distances by 0.1, and multiply output gradients by 0.1, to get solver units.

| Key | Meaning | Constructor value |
| :--- | :--- | :--- |
| `L` | grid points per side; the global grid is L^3 | 128 |
| `steps` | number of time steps | 20000 |
| `plotgap` | write output every this many steps | 200 |
| `F` | feed rate: U flows in, `F * (1 - u)` | 0.04 |
| `k` | kill rate: V is removed at `(F + k) * v` | 0.06075 |
| `Du` | diffusion coefficient of U | 0.05 |
| `Dv` | diffusion coefficient of V | 0.1 |
| `dt` | forward Euler time step | 0.2 |
| `noise` | amplitude of uniform noise in [-1, 1) added to U each step | 0.0 |
| `seed` | optional: seed for the noise; the value at each point and step depends only on the seed, the step and the global position, so reruns and any rank count give identical fields | 20261107 |
| `output_type` | `none`, `pvti`, `catalyst_io`, `catalyst_insitu`, `ascent`, `adios`, `kombyne` | `file` (set it explicitly) |
| `output_file_name` | output file or prefix for file-writing backends | `foo.bp` |
| `catalyst_script_path` | Catalyst Python script for `catalyst_*` | empty |
| `catalyst_lib_path` | Catalyst implementation library directory | empty |
| `adios_config` | ADIOS2 XML configuration | `adios2.xml` |
| `adios_span`, `adios_memory_selection` | ADIOS2 write paths (span or memory selection) | false |
| `mesh_type` | mesh description for backends that use it | `image` |
| `kombynelite_script_path` | Kombyne-lite script | empty |
| `checkpoint`, `checkpoint_freq`, `checkpoint_output` | ADIOS2 checkpoint after every N completed steps (a restart resumes from exactly that state); needs an `ENABLE_ADIOS2=ON` build (see below) | false, 2000, `ckpt.bp` |
| `restart`, `restart_input` | restart from a checkpoint; same requirement | false, `ckpt.bp` |
| `burn_in_steps` | optional: steps to run before output starts | 0 |
| `overwrite_last_step` | optional: keep only the latest output step. Every backend honours it except `catalyst_insitu`, whose script names its own files and keeps every step unless the script overwrites them | false |

Checkpointing and restart use ADIOS2 and are compiled only when
`ENABLE_ADIOS2=ON` (the presets turn it off). In any other build the
`checkpoint` and `restart` keys are read and ignored: no checkpoint is
written and a restart starts from step 0. Turn on ADIOS2 in
`CMakeUserPresets.json` and point `adios_config` at an ADIOS2 XML file (the
ones under `configs/adios2_configs/` work).

Stability: forward Euler on this stencil needs roughly `dt * max(Du, Dv) <= 1`
for the diffusion part; patterns form for F and k in the classic Pearson
ranges (the shipped values sit inside them).

---

## Outputs

| `output_type` | Needs | Writes |
| :--- | :--- | :--- |
| `none` | nothing | nothing; timing and correctness checks only |
| `pvti` | VTK | parallel VTK image files, one per output step |
| `catalyst_io` | Catalyst 2 | files written by a ParaView pipeline |
| `catalyst_insitu` | Catalyst 2 | whatever the Catalyst script renders or extracts |
| `ascent` | Ascent | whatever the Ascent actions file asks for |
| `adios` | ADIOS2 | BP5 files, or SST staging to the in transit reader |
| `kombyne` | Kombyne-lite | whatever the Kombyne script asks for |

How to run each one, with example settings, scripts and expected results, is
in the [build and run guide](docs/build-and-run-guide.md). That guide also
covers Docker, checkpoint and restart, and the in transit reader.

---

## Troubleshooting

**MPI on one machine**

* `There are not enough slots available`: Open MPI counts physical cores per
  slot. Add `--oversubscribe` to run more ranks than it thinks you have.
* Runs that are slower with more ranks on one node: Open MPI binds each rank
  to a core by default; check with `--report-bindings`, and on shared
  machines try `--bind-to none`.
* Errors that mention MPICH, or a crash at `MPI_Init`: the miniapp, VTK and
  ParaView were built against different MPI libraries. Rebuild them all with
  the same `mpicxx` and run with the matching `mpirun`
  (`which mpicxx mpirun` should point at the same installation).
* `Passed unrecognized argument`: the settings file must be passed as
  `--settings-file=<path>`, not as a bare path.

**Headless rendering** (Catalyst, Ascent, Kombyne on machines without a display)

* ParaView 6 chooses how to open a render window from
  `VTK_DEFAULT_OPENGL_WINDOW`: `vtkEGLRenderWindow` for GPU rendering without
  X, `vtkOSOpenGLRenderWindow` for OSMesa software rendering,
  `vtkXOpenGLRenderWindow` with a display. If none is set and there is no
  display, rendering fails or silently falls back to a slow software path.
* On a remote machine without a GPU, OSMesa is the reliable choice; on a GPU
  node, EGL. The backend check vignette
  (`ParaView_Vignettes/ex08_pvBackendCheck`) reports which one a ParaView
  build actually uses.
* Catalyst finds ParaView through `CATALYST_IMPLEMENTATION_PATHS` (the
  directory holding `libcatalyst-paraview.so`) and
  `CATALYST_IMPLEMENTATION_NAME=paraview`.

**Build**

* `Could not find a package configuration file provided by "VTK"`: `VTK_DIR`
  in your user preset does not point at a directory containing
  `vtk-config.cmake`.
* Presets not listed: CMake older than 3.22, or you are not in
  `Miniapps/gray-scott`.

---

## More documentation

* [Build and run guide](docs/build-and-run-guide.md): Docker, building each
  backend SDK, running each output type, checkpoint and restart, the in
  transit reader.
* [AGENTS.md](https://github.com/jameskress/Visualization_Vignettes/blob/master/AGENTS.md) (in the repository root): the working rules and target invariants for
  this miniapp.
* `sites/kw61316`, `sites/ibex`, `sites/shaheen`: machine-specific notes.
* The plan of work: phase issues #11, #18, #28, #38 and #46 on GitHub.
