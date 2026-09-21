# Datasets

Static datasets read by the ParaView and VisIt vignettes. Nothing here is
produced by a simulation at test time -- the vignettes are pure readers.

## Shipped with the repository

| Path | Contents |
| :--- | :--- |
| `varying_data/varying*.vtk` | 20-step time series, 50³ rectilinear grid, point scalar `temp`. **Carries no time and no cycle**: nothing in these files says which timestep they are, so a reader has to invent one from the file's position in the list. Used by ex07, ex10 and ex11's state generators, where that does not matter. |
| `varying_series_xml/` | The same twenty timesteps as XML `.vtr`, **with real `TIME` and `CYCLE` in each file**, plus a `series.pvd` for ParaView and a `series.visit` for VisIt. Generated, not committed: `python3 Testing/prepare_machine.py`, or `pvbatch data/make_time_series.py`. Read by ex05 and ex12, whose subject is time. See `data/make_time_series.py` for the measurements that made it necessary. |
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
| `amr_hierarchy.vth` / `.vthb` | Overlapping AMR hierarchy (ParaView only). ParaView 5.x writes `.vth`, 6.x writes `.vthb`; the generator probes both and the manifest records which one exists. |
| `surface_polydata.vtp` | Triangulated polygonal surface |
| `ragged_multiblock.vtm` | Multiblock with **unequal** blocks |
| `ragged_blocks/` + `ragged_multidomain.visit` | The same unequal blocks as a VisIt multi-domain database |
| `topologies_manifest.json` | Which scalar each dataset carries, and at what value to contour it |

Every dataset carries a point scalar named `scalar`. The manifest records each
dataset's **measured** scalar range and an isovalue strictly inside it, and the
vignettes read both from there rather than assuming a shared constant -- two of
the five do not share the Wavelet's range:

* the AMR Gaussian pulse tops out near 0.33, so the shared value of 150 (and the
  hard-coded 0.5 that replaced it) produced an empty contour;
* `surface_polydata.vtp` *is* the isosurface at 150, so on it the wavelet scalar
  is exactly 150 everywhere. Contouring a constant field at its own constant
  value is empty by construction, in ParaView and VisIt alike, so `scalar` there
  is the Y coordinate instead -- which is what makes the contour the *isoline*
  that `ex09` says it is testing.

Where a source refuses to rename its array, the fallback name is recorded in the
manifest too, and the vignettes read the name from there rather than assuming
it.

**The ragged datasets are ragged on purpose.** Their blocks have different
spans in every axis, because a decomposition whose extents divide evenly is
exactly the case that hides off-by-one errors in partitioned readers,
writers and filters.

The generator is a ParaView script, so it needs `pvbatch` on your `PATH`. It
writes nothing outside its output directory, and `--output-dir` puts the
datasets somewhere else -- point the vignettes at it with `--data-dir` or
`$VV_DATA_DIR`.
