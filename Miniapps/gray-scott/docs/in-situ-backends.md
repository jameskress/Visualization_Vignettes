# In situ backends

How the Gray-Scott miniapp hands its data to each backend, and the rules they
all follow so that their results and timings can be compared. Phase 3 (#28)
fills this in backend by backend; #27 completes it.

Performance records for every backend are described in the
[README's Performance section](../README.md#performance).

## The shared mesh description

Every Conduit-based backend gets the same Mesh Blueprint tree, built by
`simulation/mesh_blueprint.h` (#20). Ascent and Catalyst (#21) publish it.
Kombyne-lite and PVTI take their own objects, so they use the same geometry
helpers and ownership instead (#23).

**Mesh.** One Blueprint domain per rank, with `state/domain_id` set to the
rank. A uniform coordset and topology cover the rank's whole ghosted array,
`size + 2` points per axis. Point `i` of the local array is global point
`offset + i - 1`.

**Coordinates.** The origin is `(offset - 1) * 0.1` and the spacing is
0.1. That is the spacing every shipped camera assumes; the solver itself
is dimensionless.

**Fields.**

* `u` and `v` are vertex fields attached with `set_external`, so the
  backend reads the solver's own arrays and nothing is copied. Building
  the tree does no per-point work: about 33 microseconds per step at 64^3.
  The ghost flags are computed once, at start-up.
* The tree is verified with `conduit::blueprint::mesh::verify` on the
  first write. Its shape never changes after that.

**Ownership.** A cell belongs to the rank that owns its low corner point.

* Cells whose low corner is in the low halo are ghosts; the neighbour
  below owns them.
* Cells whose low corner is the last owned point bridge to the
  neighbour above, and are owned here.

Every global cell, including the periodic wrap-around cells, is therefore
owned by exactly one rank. On 4 ranks at 64^3 that is 4 x 32 x 32 x 64 =
64^3 owned cells, with no gaps and no doubles at rank boundaries.

**Ghost fields.** Each backend gets the convention it reads, all computed
from the same ownership rule:

| Field | Association | Type | Values | Read by |
| :--- | :--- | :--- | :--- | :--- |
| `ascent_ghosts` | element | int32 | 0 owned, 1 ghost | Ascent strips cells outside [0, 0] before rendering (`ascent_main_runtime.cpp`) |
| `vtkGhostType` | element | uint8 | 0, or `DUPLICATECELL` = 1 | VTK and ParaView (`vtkDataSetAttributes.h`) |
| `vtkGhostType_points` | vertex | uint8 | 0, or `DUPLICATEPOINT` = 1 | offered to Catalyst (#21); a Blueprint tree cannot hold two fields named `vtkGhostType` |

**Halo freshness.** `iterate()` exchanges halos before it updates, so
afterwards the halo is one step behind the interior. Each output step
therefore calls `GrayScott::refresh_halos()` before the backend runs. The
call is the same for every backend and is timed under `halo`, and it does
not change the solution.

## Ascent

`simulation/writerAscent.cpp` publishes the shared tree with only the
`ascent_ghosts` field.

* The actions file named in `ascent_options.yaml` is read once, at
  start-up. It used to be read from disk on every step.
* With `overwrite_last_step`, relay extracts are replaced by a manual save
  that overwrites the previous one.

Timers (README, Performance):

| Timer | Measures |
| :--- | :--- |
| `wrap` | building the tree |
| `execute` | `ascent.publish` and `ascent.execute` |
| `io` | the manual relay save (zero otherwise) |

Ascent's own render and extract output happens inside `execute`. Its
per-filter timings (the `timings` option in `ascent_options.yaml`) give a
finer split; see the build and run guide.

The scripts are in `configs/ascent_scripts/`. Cameras assume the 0.1
spacing above, so the domain spans 0 to 6.4 for L = 64.

Checked on 1, 2 and 4 ranks (64^3, volume render of `v`):

* The mesh verifies on every rank.
* The data range in the rendered images is identical.
* No seams or gaps appear at rank boundaries.
* 0.4% of pixels differ by more than 8 of 255 between 1 and 4 ranks. This
  is volume-render sampling and compositing across domains. #24 adds an
  exact ghost-volume test.

## Catalyst (ParaView 6.2)

`simulation/writerCatalyst.cpp` puts the shared tree on the channel `grid`
with the `vtkGhostType` cell field (#21). ParaView's Conduit reader
recognises the name and makes it the cell ghost array.

* Each block sits at its true global position, over its full ghosted
  array.
* The old adaptor copied u and v without halos and shifted each block's
  origin until the pieces touched. Both are gone.
* Zero-copy, checked: the address of `u` that the adaptor logs on its
  first write equals the address of the `u` array in the vtkImageData that
  ParaView builds for that rank.

Timers:

| Timer | Measures |
| :--- | :--- |
| `wrap` | building the tree |
| `execute` | `catalyst_execute`: ParaView's conversion plus the pipeline or script, including any files it writes |
| `io` | not separated from `execute` |

Checked on 1, 2, 4 and 8 ranks at 64^3, step 100, with a test script that
integrates areas using ParaView's `IntegrateVariables` (which skips
`DUPLICATECELL` cells):

| Quantity | 1 rank | 2, 4 and 8 ranks |
| :--- | ---: | ---: |
| contour v = 0.2, area | 17.2025866257 | identical to 10 digits |
| slice at x = 3.25 (inside a cell layer), area | 40.96 | identical |
| slice at x = 3.2 (exactly on the 2-rank boundary plane), area | 40.96 | 81.92 |

The contour has no cracks and no doubled faces. The one case that doubles
is a cut lying exactly on a grid plane that two blocks share:

* Each rank cuts its own owned cell face on that plane, and ParaView's
  cutter output carries no ghost flags to drop one of the copies.
* Avoid exact grid planes at rank boundaries, or deduplicate afterwards.

The cell ghost count per rank equals the low-halo cells, for example 8353
of 139425 on a 33 x 65 x 65 cell block.

The shipped scripts in `configs/catalyst_scripts/` follow what the
renders on 1, 2, 4 and 8 ranks showed. Volumes are rendered straight from
the producer: a `GhostCells` filter under a volume cracks it at rank
boundaries. Surface filters (Clip, Contour) read `GhostCells(producer)`:
with ghosts on the low side only, the high face of each block is otherwise
drawn as an internal surface, and contour normals there are one-sided.
Colour maps are pinned so that every rank count gets the same colours.

Rendering needs no X display: the ParaView 6.2 source build renders
through EGL with `VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow` (pass it
to the ranks with `mpirun -x`).

## Kombyne-lite (free version 1.5)

Kombyne takes its own grid objects, not a Conduit tree. Its adaptor
(`simulation/writerKombyne.cpp`, #23) builds a rectilinear grid
(`kb_rgrid`) over the full ghosted block:

* The axis coordinates come from `gs_mesh::axis_points` (the same origin
  and 0.1 spacing).
* `U` and `V` are passed with `KB_MEM_BORROW`, so there is no copy.
* The ghost-cell mask comes from the shared ownership rule, in Kombyne's
  convention: 0 = ghost, non-zero = real (`kombyne_data_ugrid.h`).
* The coordinates and mask are built once and borrowed every step.
* The old adaptor copied u and v without halos and built per-point
  coordinates, which left a one-cell gap between ranks.

Timers: `wrap` (building the handles, about 50 microseconds at 64^3) and
`execute` (`kb_simulation_execute`, including its exports).

Checked by exporting with `kombyne-save-data.yaml` on 1, 2 and 4 ranks and
reading the files in ParaView:

* Contouring v = 0.2 over the cells with `__ghostCells` >= 1 gives the
  same area on every rank count.
* The owned volume is 262.144 (6.4^3) on every rank count.

Kombyne's VTK export writes the mask as `__ghostCells` in Kombyne's
convention, not as `vtkGhostType`, so ParaView does not treat it as a ghost
array. Contouring the exported files without the threshold double counts
the halo cells: area 17.61 on 2 ranks and 18.01 on 4, against 17.20.
Readers of Kombyne exports must apply the mask; #24's test does so.

## PVTI (VTK XML)

`simulation/writerPVTI.cpp` (#23) writes the same geometry:

* **Extents:** each piece is its full ghosted block, with extents in
  global point indices. The whole extent runs from -1 to L, the halo
  layers included. The old writer placed every block one point too high
  and flagged no ghosts.
* **Fields:** `u` and `v` are the solver's arrays, borrowed by VTK
  (`SetArray(..., save = 1)`) and written as doubles. The old writer copied
  them to float. Files are about twice as large as before; in exchange they
  hold exactly what every other backend sees.
* **Ghosts:** `vtkGhostType` is written as both a cell array
  (`DUPLICATECELL` on low-halo cells) and a point array (`DUPLICATEPOINT`
  on halo points). ParaView applies both when reading.

Timers: `wrap` (building the image inside the pipeline, about 90
microseconds at 64^3, down from about 11 ms) and `io` (the rest of
`Write()`).

Checked in ParaView 6.2 on 1, 2 and 4 ranks:

* The volume is 262.144 on every rank count.
* The contour v = 0.2 area is 17.2025866257 on every rank count, the same
  value as Catalyst.

## ADIOS2 (BP5 files and SST staging)

`simulation/writerADIOS.cpp` (#22) writes `U` and `V` as global L^3
arrays.

**What is stored.** Each rank's block holds its owned points only, so every
global point is stored exactly once and no halo is written. There is
nothing for a reader to deduplicate. The geometry matches the shared
description: point i sits at i * 0.1 (the `Fides_Origin` and
`Fides_Spacing` attributes).

**Attributes for readers.**

| Attribute | Value |
| :--- | :--- |
| `gs_point_ownership` | "each global point stored once" |
| `gs_halo_layers_written` | 0 |
| `gs_periodic` | {1, 1, 1} |
| `gs_ghost_policy` | "readers add their own overlap layer and flag it ghost" |

A reader that builds one mesh per block, such as the in transit analysis
reader, must read one extra layer of points past the high side of its
block itself, wrapping around because the domain is periodic. Otherwise
there is a one-cell gap between blocks. Those added points are ghost
points (`DUPLICATEPOINT`), but the cells they close are owned by the
block: only cells whose low corner belongs to another block are ghosts.
Flagging every cell that touches an added point would remove owned
boundary cells and open the gap again. The analysis reader does not do
this yet; the fix is planned for phase 5 (#42).

**The three write modes.**

| Mode (setting) | Copies made by the miniapp | `wrap` | `execute` | `io` |
| :--- | :--- | :--- | :--- | :--- |
| default | one: `u_noghost()` into a local vector (ADIOS2 may copy again into its own buffer; that depends on the engine) | the copy | `BeginStep` and the `Put` calls | `EndStep` |
| `adios_span` | one, straight into ADIOS2's buffer | the copy | `BeginStep` and the `Put` calls | `EndStep` |
| `adios_memory_selection` | none: ADIOS2 reads the interior of the ghosted arrays | 0 | `BeginStep` and the `Put` calls | `EndStep` |

In every mode, `io` also includes the close and reopen that
`overwrite_last_step` does before each write.

Span and memory selection are checked with BP5 only. With the SST engine
the writer ignores both settings, logs a warning and uses the default
mode: SST does not implement span `Put()`, and its FFS marshalling is
reported to ignore memory selections. Revisit when the in transit path is
tested in phase 5 (#42).

**Pointer lifetime.** `Put()` is deferred: ADIOS2 may read the memory at
`Put()` or at any point up to `EndStep()`, depending on the engine. Each
pointer handed to `Put()`, and the data it points to, must therefore stay
valid and unchanged until `EndStep()` returns:

* The solver's arrays in memory-selection mode. Nothing writes them
  during `write()`; the writer also checks after `EndStep()` that they
  have not moved, and aborts if they have.
* The local vectors in the default mode. They are const and live until
  the end of the block that contains `EndStep()`.
* ADIOS2's own span buffer in span mode, filled before `EndStep()`.

**Checked.** BP5 files on 1 and 4 ranks in all three modes: the stored
`U` at step 100 is identical at full precision across modes and rank
counts. That holds because the solver is bitwise identical across rank
counts (#15) and each point is stored once. The SST in transit path was
not run, because the reader build does not link on the workstation (see
#26).

## Zero-copy and allocations (#25)

**Pointer checks.** Each adaptor checks that the array it hands the backend
is the solver's own (`Writer::check_zero_copy`). Debug builds check every
write; release builds check the first. A copy aborts the run.

| Adaptor | What is compared |
| :--- | :--- |
| Ascent and Catalyst | the data pointer of `fields/u/values` |
| PVTI | the pointer inside VTK's `u` array |
| ADIOS2 memory selection | nothing to compare: `Put` takes the solver's own pointer directly, and the writer checks after `EndStep()` that the arrays have not moved |
| Kombyne | no getter exists; `KB_MEM_BORROW` is the API's zero-copy guarantee |

**Allocation counts.** Built with `-DGS_COUNT_ALLOCATIONS=ON`, on 2 ranks
at 64^3 for 30 steps with output every 10:

| Backend | solver step, steps 1 to 30 | wrap, per write (allocations / bytes) | whole backend call, per write |
| :--- | ---: | ---: | ---: |
| none | 0 | 0 / 0 | 0 |
| PVTI | 0 (1 inside Open MPI) | 77 / 9 KB | 1138 |
| Catalyst | 0 | 389 / 20 KB | 4701 |
| Kombyne-lite | 0 | 48 / 5 KB | 1775 |
| ADIOS2 default | 0 | 2 / 2 MB (the deliberate copy of u and v) | 338 |
| ADIOS2 span | 0 | 0 / 0 | 334 |
| ADIOS2 memory selection | 0 | 0 / 0 | 346 |

How to read it:

* **Solver step:** nothing in our code allocates. Open MPI allocates
  about 147 KB on the first exchange, and rarely grows a 4 KB buffer
  later; the PVTI run shows one such growth on one rank.
* **Wrap:** no backend allocates field-sized memory except the ADIOS2
  default mode, which is the copying mode by design. The remaining wrap
  allocations are metadata: Conduit tree nodes, VTK array objects and
  Kombyne handles, rebuilt each write.
* **Whole call:** the counts are the backends' own internal allocations.
  They are reported, not failed.

## Ghost volume test (#24)

`tests/ghost_volume/ghost_volume.py` checks the ghost handling of every
backend end to end. The README's Testing section shows how to run it.

At 64^3, step 100, cells with u <= 0.3 on every corner:

| Backend | Counted by | 1, 2, 4 and 8 ranks |
| :--- | :--- | :--- |
| ADIOS2 | `bpls`, counted on the periodic global array (the reference) | 356 cells, volume 0.356 |
| Catalyst | Threshold, then IntegrateVariables, in situ | 356 cells, volume 0.356000097 |
| PVTI | the same pipeline on the files, in pvpython | 356, 0.356000097 |
| Kombyne-lite | the same, after masking with `__ghostCells` | 356, 0.356000097 |
| Ascent | threshold pipeline and relay extract, owned cells counted with h5py | 2460 (any-corner rule) |

The volume differs between the reference and the other three. ParaView
integrates the threshold output, whose points are float32, so its volume
differs from 356 x 0.1^3 by 2.7e-7 relative. The comparison uses 1e-12
between backends integrated the same way and 1e-6 against the analytic
value.

Ascent's threshold keeps a cell if any corner is in range; this Ascent has
no all-corners option. Its count is therefore compared with the ADIOS2
reference under the same rule (2460 on both). Ascent's pipelines keep ghost
cells, and Ascent strips them only before rendering, so the extract still
carries `ascent_ghosts` and the test counts cells where it is 0. The
rendered images are checked separately (Rendering, below).

## Rendering

The images are the acceptance test: a seam, crack or internal face at a
rank boundary is a failure even when the counts above agree.
`tests/render/render_check.py` (CTest label `render`) renders each backend
on 1 and 4 ranks with the same camera and fixed colour ranges, and fails
if more than 0.1% of pixels differ by more than 24/255. The images stay in
the build tree under `tests/render/<backend>/` for review.

Workstation, 64^3, step 2000, 4 vs 1 ranks (pixels off by more than 24/255):

| Backend | Volume | Contour |
| :--- | :--- | :--- |
| Catalyst | 0.002% | 0.000% |
| Ascent | 0.000% | 0.000% |
| PVTI | 0.000% | 0.000% |
| Kombyne-lite | (no volume) | 0.012% |

The pre-#21 adaptor, which moved each rank's block back by one cell per
block index instead of marking ghosts, fails the same check: 2.1% of
volume pixels and 15% of contour pixels change between 1 and 4 ranks. Its
images looked continuous, but each rank boundary lost one cell layer and
the structures moved as ranks were added.

Rules each backend needs for clean images:

* **ParaView / Catalyst.** Render volumes straight from the producer. Put
  a `GhostCells` filter before surface filters (Contour, Clip, Slice). The
  adaptor marks one ghost layer, on the low side of each block, so without
  it the high face of each block is drawn as an internal surface and
  contour normals there are one-sided. Under a volume, the extra layer
  cracks the image. Pin colour maps (`AutomaticRescaleRangeMode =
  "Never"`): rescaling to each run's range makes the same data render
  differently per rank count.
* **Ascent.** Set `samples` on volume plots, about 9 per cell along the
  diagonal (1000 for L = 64). The default of 100 bands, and streaks at
  block faces differently for each rank count. Ascent strips ghost cells
  before rendering, so meshes show no internal faces.
* **Kombyne-lite.** Give pseudocolor a `minimum` and `maximum`; Kombyne
  otherwise uses the current data range, which differs between rank
  counts. Its iso surfaces keep a faint one-sided normal at block faces
  (0.012% of pixels above); there is no GhostCells equivalent.
* **Slices** exactly on a grid plane two ranks share are drawn by both.
  Place them between grid planes (the shipped scripts use 3.25, not 3.2).

Headless rendering: the ParaView 6.2 source build and the Kitware binaries
both render through EGL without an X display. Set
`VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow` (and pass it to the ranks,
`mpirun -x VTK_DEFAULT_OPENGL_WINDOW`), or give pvpython
`--opengl-window-backend EGL`. EGL and X images are pixel-identical.

