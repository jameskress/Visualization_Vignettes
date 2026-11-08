# In situ backends

How the Gray-Scott miniapp hands its data to each backend, and the rules they
all follow so that their results and timings can be compared. Phase 3 (#28)
fills this in backend by backend; #27 completes it.

Performance records for every backend are described in the
[README's Performance section](../README.md#performance).

## The shared mesh description

Every Conduit-based backend gets the same Mesh Blueprint tree, built by
`simulation/mesh_blueprint.h` (#20). Ascent and Catalyst (#21) use it;
Kombyne-lite moves to it in #23.

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
