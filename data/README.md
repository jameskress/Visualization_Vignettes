# Datasets

Static datasets read by the ParaView and VisIt vignettes. Nothing here is
produced by a simulation at test time -- the vignettes are pure readers.

## Shipped with the repository

| Path | Contents |
| :--- | :--- |
| `varying_data/varying*.vtk` | 20-step time series, 50³ rectilinear grid, point scalar `temp`. Used by ex07, ex10, ex12 and by ex11's state generators. |
| `varying.visit` | A `.visit` index over the series. Its paths are relative to the repository root, so vignettes build their own index with absolute paths instead. |
| `noise.silo` | Silo database with `hardyglobal`. Used by the classic VisIt vignettes and by ex03. |
| `images/` | Images used by the documentation. |

## Fetched on demand

```bash
./fetchData.sh
```

Downloads the large datasets used by `ex06` in both suites.

> **Two caveats worth knowing.** `fetchData.sh` currently passes `curl -k`,
> which disables TLS certificate verification, and sets
> `UNZIP_DISABLE_ZIPBOMB_DETECTION=TRUE`. There is no checksum on the
> archive. If you are on a network you do not control, fetch the archive by
> other means and verify it before extracting.

## Generated once

```bash
pvbatch make_topology_datasets.py
```

Writes `topologies/`, which `ex09` reads in both suites:

| File | Topology |
| :--- | :--- |
| `scalar_field.vti` | Uniform image data |
| `tetra_unstructured.vtu` | Unstructured grid of tetrahedra |
| `amr_hierarchy.vth` | Overlapping AMR hierarchy (ParaView only) |
| `surface_polydata.vtp` | Triangulated polygonal surface |
| `ragged_multiblock.vtm` | Multiblock with **unequal** blocks |
| `ragged_blocks/` + `ragged_multidomain.visit` | The same unequal blocks as a VisIt multi-domain database |
| `topologies_manifest.json` | Which scalar each dataset carries, and at what value to contour it |

Every dataset carries a point scalar named `scalar`, so one contour value is
meaningful across all of them. Where a source refuses to rename its array --
the AMR Gaussian pulse is the case that actually happens -- the fallback name
is recorded in the manifest, and the vignettes read the name from there
rather than assuming it.

**The ragged datasets are ragged on purpose.** Their blocks have different
spans in every axis, because a decomposition whose extents divide evenly is
exactly the case that hides off-by-one errors in partitioned readers,
writers and filters.

The generator is a ParaView script, so it needs `pvbatch` on your `PATH`. It
writes nothing outside its output directory, and `--output-dir` puts the
datasets somewhere else -- point the vignettes at it with `--data-dir` or
`$VV_DATA_DIR`.
