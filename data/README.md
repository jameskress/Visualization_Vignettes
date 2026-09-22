# Datasets

Everything the ParaView and VisIt vignettes read. Nothing here is produced by
a simulation at test time: the vignettes are pure readers.

Three categories, and the difference between them matters more than it looks.
**Shipped** files are in git and are the same everywhere. **Fetched** files are
downloaded once and are the same everywhere. **Generated** files are built by a
tool on each machine and are *not* portable, and none of them announces a
mismatch when it is wrong.

| Category | Copy between machines? | Rebuild with |
| :--- | :--- | :--- |
| Shipped | yes, it is in git | nothing |
| Fetched | yes | `./fetchData.sh` |
| Generated | **no** | `python3 ../Testing/prepare_machine.py` |

---

## Shipped with the repository

| Path | Size | Contents | Read by |
| :--- | ---: | :--- | :--- |
| `varying_data/varying*.vtk` | 19 MB | 20-step time series, 50³ rectilinear grid, point scalar `temp`. Legacy ASCII VTK. | ex07, ex10, ex11 |
| `varying.visit` | 4 KB | A `.visit` index over that series. Its paths are relative to the repository root, so vignettes that need absolute paths build their own. | ex11 |
| `noise.silo` | 11 MB | Silo database with the point scalar `hardyglobal`. | ex00-ex04 |
| `images/` | 872 KB | Images used by the documentation. | none |

### The legacy series carries no time

Nothing in `varying*.vtk` says which timestep it is. There is no `TIME` and no
`CYCLE` field, so **both tools invent a time from the file's position in the
list**, and they agreed on that invention until VisIt 3.4.2 changed it:

| Series | ParaView 6.1.0 | VisIt 3.4.1 | VisIt 3.4.2 |
| :--- | :--- | :--- | :--- |
| legacy `.vtk`, as shipped | `0, 1, 2 …` | `0, 1, 2 …` | **`0, 0, 0 …`** |

That is why `varying_series_xml/` exists (below). The legacy series is kept
deliberately, so the repository can show both behaviours: what a reader does
when the data tells it the time, and what it does when the data does not.
ex11's ParaView state also exists to exercise `LegacyVTKReader` specifically.

---

## Fetched on demand

```bash
./fetchData.sh
```

| Path | Size | Read by |
| :--- | ---: | :--- |
| `cyclone-chapala-2015-11-02_00-00-00-mb/` and `.vtm` | 5.6 GB | **ex06 only** |
| `currentRainfall.silo` | 145 MB | **ex06 only** |
| `KAUST_Visualization_Vignettes_Large_Data.zip` | 4.3 GB | the archive, gitignored |

The archive extracts beside itself; delete it afterwards if space matters.
Only ex06 reads any of this, and `prepare_machine.py --check` reports its
absence as a warning (exit 3) rather than an error, so the other twelve
vignettes run on a machine that never fetched it.

> **Two caveats.** `fetchData.sh` passes `curl -k`, which disables TLS
> certificate verification, and sets `UNZIP_DISABLE_ZIPBOMB_DETECTION=TRUE`.
> There is no checksum on the archive. On a network you do not control, fetch
> it by other means and verify it before extracting.

---

## Generated per machine

```bash
python3 ../Testing/prepare_machine.py          # build what is missing or stale
python3 ../Testing/prepare_machine.py --check  # verify only
```

`test_suite.py` runs `--check` as a preflight and refuses to start when any of
these is stale, because every way they fail looks like a regression in a
vignette rather than a setup problem.

### `topologies/` (35 MB), `pvbatch make_topology_datasets.py`

ex09's four mesh topologies in both suites, plus AMR in ParaView.

| File | Topology |
| :--- | :--- |
| `scalar_field.vti` | Uniform image data |
| `tetra_unstructured.vtu` | Unstructured grid of tetrahedra |
| `amr_hierarchy.vth` / `.vthb` | Overlapping AMR hierarchy, ParaView only. 5.x writes `.vth`, 6.x writes `.vthb`; the generator probes both and the manifest records which exists. VisIt's VTK reader does not consume either. |
| `surface_polydata.vtp` | Triangulated polygonal surface |
| `ragged_multiblock.vtm` + `ragged_blocks/` | Multiblock with **unequal** blocks |
| `ragged_multidomain.visit` | The same unequal blocks as a VisIt multi-domain database |
| `topologies_manifest.json` | Per dataset: scalar name, association, **measured** scalar range, and an isovalue strictly inside it |

**Why the manifest records a measured isovalue rather than a shared constant.**
Two of the five datasets do not share the Wavelet's range, and using one
constant produced empty contours that said nothing:

* the AMR Gaussian pulse tops out near 0.33, so a shared value of 150 (and the
  hard-coded 0.5 that replaced it) contoured nothing at all;
* `surface_polydata.vtp` *is* the isosurface at 150, so on it the wavelet
  scalar is exactly 150 everywhere. Contouring a constant field at its own
  constant value is empty by construction, in both tools. `scalar` there is
  the Y coordinate instead, which is what makes the contour the *isoline* ex09
  says it is testing. The manifest also flags
  `contour_is_lower_dimensional`, so ex09 knows to draw the input surface
  underneath it rather than rendering a hairline on empty space.

**The ragged datasets are ragged on purpose.** Their blocks have different
spans in every axis, because a decomposition whose extents divide evenly is
exactly the case that hides off-by-one errors in partitioned readers, writers
and filters.

The generator is a ParaView script and needs `pvbatch` on `PATH`. It writes
nothing outside its output directory; `--output-dir` puts the datasets
elsewhere, and the vignettes follow with `--data-dir` or `$VV_DATA_DIR`.

### `varying_series_xml/` (12 MB), `pvbatch make_time_series.py`

The same twenty timesteps as XML `.vtr`, **with real `TIME` and `CYCLE` in
each file's field data**, plus `series.pvd` for ParaView and `series.visit`
for VisIt. Read by ex05 and ex12, whose subject is time.

| | `timestep` | `cycle` | `time` |
| :--- | ---: | ---: | ---: |
| ParaView 6.1.0 | 0, 1, 2 | 0, 100, 200 | 0.0, 0.05, 0.1 |
| VisIt 3.4.1 | 0, 1, 2 | 0, 100, 200 | 0.0, 0.05, 0.1 |
| VisIt 3.4.2 | 0, 1, 2 | 0, 100, 200 | 0.0, 0.05, 0.1 |

The time is deliberately **not** the file index and the cycle steps by 100, so
those are three visibly different numbers rather than the loop counter written
out three times. It is also 41% smaller than the legacy series, because XML
VTK is binary and compressed where the legacy format is ASCII.

Ruled out first, by measurement on the same twenty files: `!TIME` directives in
a `.visit` index are ignored by VisIt 3.4.1 and 3.4.2 alike, `TIME` and
`TimeValue` in legacy field data are ignored by ParaView's `LegacyVTKReader`,
and a `.pvd` collection over legacy `.vtk` yields no timesteps at all. See the
header of `make_time_series.py`.

### Elsewhere in the tree

`ex11_state.pvsm`, `ex11_visit.session` and `ex11_series.visit` live beside
their vignettes rather than here, but they are generated by the same command
and follow the same rule: a `.pvsm` and a `.session` are locked to the version
that wrote them, and `ex11_series.visit` holds absolute paths.

---

## Offline machines

See `Testing/OFFLINE_SETUP.md`. The short version: copy the shipped and
fetched files, **never** copy the generated directories, and run
`prepare_machine.py` on the target.
