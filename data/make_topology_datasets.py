#
# Visualization Vignettes
#
# make_topology_datasets.py
#
# One-time data preparation for the mesh-topology and state-file vignettes.
#
# Produces five static datasets under data/topologies/ that ex07 through ex12
# read from disk. This is a preparation step in the same spirit as
# fetchData.sh -- run it once per checkout, commit or stage the output, and
# the vignettes themselves stay pure readers with no generation logic and no
# dependency on anything outside their own directory.
#
#   scalar_field.vti          uniform rectilinear image data
#   tetra_unstructured.vtu    unstructured grid of tetrahedra
#   amr_hierarchy.vth[b]      overlapping AMR hierarchy
#   surface_polydata.vtp      triangulated polygonal surface
#   ragged_multiblock.vtm     multiblock with deliberately unequal blocks
#
# Every dataset carries a point-centred scalar named "scalar" so a single
# contour value is meaningful across all five. Where a source refuses to
# rename its array, the fallback name is recorded in topologies_manifest.json
# and the vignettes read the name from there rather than assuming it.
#
# The ragged multiblock is the important one. Its blocks are deliberately NOT
# equal sizes, because a decomposition whose extents divide evenly is the
# case that hides off-by-one errors in partitioned readers and writers.
#
# USAGE
#
#   pvbatch data/make_topology_datasets.py
#   pvbatch data/make_topology_datasets.py --output-dir /scratch/vv-data/topologies
#
# Author: James Kress, <james@jameskress.com>
#
import argparse
import datetime
import json
import os
import sys

from paraview.simple import *  # noqa: F401,F403


# The scalar every dataset should expose, and the isovalue the vignettes
# contour at. Chosen to sit inside the Wavelet source's natural RTData range
# (roughly 37 to 276) so the contour is non-empty on every topology.
TARGET_SCALAR = "scalar"
CONTOUR_VALUE = 150.0

# Only reached when the AMR array cannot be measured at all. Every normal
# run records a value taken from the data.
AMR_FALLBACK_CONTOUR_VALUE = 0.15

# Wavelet extent. 51^3 points is large enough that a contour has real
# geometry to compare and small enough that the whole set of datasets stays
# a few tens of megabytes.
WAVELET_EXTENT = [-25, 25, -25, 25, -25, 25]

# ParaView renamed the overlapping-AMR XML extension between 5.13 (".vth")
# and 6.x (".vthb"), and vtkSMWriterFactory matches purely on the extension:
# SaveData("...vth") on ParaView 6.1 finds no writer, returns a null proxy,
# and CreateWriter then raises AttributeError on it. A single hard-coded
# extension is therefore wrong on exactly one of the two releases, so both
# are tried and whichever one produced a file is what the manifest records.
AMR_EXTENSIONS = (".vth", ".vthb")


def _paraview_version_string():
    """The running ParaView's version, as major.minor.patch when available.

    paraview.__version__ carries the full "6.1.0"; GetParaViewVersion() gives
    only (6, 1). The full string is recorded and the comparison is made on
    major.minor, which is the granularity at which these formats actually
    change.
    """
    try:
        import paraview

        version = getattr(paraview, "__version__", None)
        if version:
            return str(version)
    except Exception:  # noqa: BLE001
        pass
    try:
        return ".".join(str(part) for part in GetParaViewVersion())
    except Exception:  # noqa: BLE001
        return "unknown"


def point_array_range(proxy, name):
    """(min, max) of a point array on an updated proxy, or None.

    Measuring beats assuming. Two of the five datasets had a hard-coded
    isovalue that does not lie inside their data, and neither failure was
    visible until ex09 asserted on the contour it produced.
    """
    array = proxy.PointData.GetArray(name)
    if array is None:
        return None
    low, high = array.GetRange(0)
    return (float(low), float(high))


def interior_value(value_range, fraction=0.5):
    """A value strictly inside `value_range`.

    Used to pick an isovalue that is guaranteed to produce geometry on a
    continuous field. Returns None for a degenerate range, which is the
    caller's signal that contouring this array is meaningless.
    """
    if value_range is None:
        return None
    low, high = value_range
    if not high > low:
        return None
    return round(low + (high - low) * fraction, 9)


def log(message):
    print("[make_topology_datasets] {0}".format(message))
    sys.stdout.flush()


def build_base_field():
    """Wavelet source with its RTData copied to a predictably named scalar."""
    wavelet = Wavelet(registrationName="vv_wavelet")
    wavelet.WholeExtent = WAVELET_EXTENT

    named = Calculator(Input=wavelet, registrationName="vv_named_scalar")
    named.AttributeType = "Point Data"
    named.ResultArrayName = TARGET_SCALAR
    named.Function = "RTData"
    UpdatePipeline(proxy=named)
    return named


def write_uniform(base, output_dir, manifest):
    """Uniform image data -- the simplest topology, and the shared reference."""
    path = os.path.join(output_dir, "scalar_field.vti")
    SaveData(path, proxy=base, PointDataArrays=[TARGET_SCALAR])
    log("wrote {0}".format(path))
    manifest["uniform"] = {
        "path": os.path.basename(path),
        "topology": "uniform image data",
        "scalar": TARGET_SCALAR,
        "association": "POINTS",
        "scalar_range": point_array_range(base, TARGET_SCALAR),
        "contour_value": CONTOUR_VALUE,
    }


def write_tetrahedra(base, output_dir, manifest):
    """Unstructured grid of tetrahedra."""
    tets = Tetrahedralize(Input=base, registrationName="vv_tets")
    UpdatePipeline(proxy=tets)

    path = os.path.join(output_dir, "tetra_unstructured.vtu")
    SaveData(path, proxy=tets, PointDataArrays=[TARGET_SCALAR])
    log("wrote {0}".format(path))
    manifest["tetra"] = {
        "path": os.path.basename(path),
        "topology": "unstructured grid (tetrahedra)",
        "scalar": TARGET_SCALAR,
        "association": "POINTS",
        "scalar_range": point_array_range(tets, TARGET_SCALAR),
        "contour_value": CONTOUR_VALUE,
    }
    Delete(tets)


def write_polydata(base, output_dir, manifest):
    """Triangulated polygonal surface carrying a scalar that varies ALONG it.

    The surface is the isosurface of the wavelet at CONTOUR_VALUE, so on it
    the wavelet scalar is exactly CONTOUR_VALUE everywhere -- range
    [150, 150]. Shipping that array under the name the vignettes contour on
    made ex09's polydata case empty by construction: contouring a constant
    field at its own constant value produces nothing, in ParaView and in
    VisIt alike, and no version change would ever have fixed it.

    What ex09 says it wants from this dataset is the case where "a volume
    contour becomes an isoline and the filter has to cope with it". An
    isoline needs a field that varies across the surface, so `scalar` is
    overwritten here with the Y coordinate, and the manifest records the
    isovalue to cut it at -- measured, not assumed.
    """
    surface = Contour(Input=base, registrationName="vv_surface")
    surface.ContourBy = ["POINTS", TARGET_SCALAR]
    surface.Isosurfaces = [CONTOUR_VALUE]
    surface.PointMergeMethod = "Uniform Binning"
    UpdatePipeline(proxy=surface)

    varying = Calculator(Input=surface, registrationName="vv_surface_scalar")
    varying.AttributeType = "Point Data"
    varying.ResultArrayName = TARGET_SCALAR
    varying.Function = "coordsY"
    UpdatePipeline(proxy=varying)

    scalar_range = point_array_range(varying, TARGET_SCALAR)
    isovalue = interior_value(scalar_range)
    if isovalue is None:
        raise RuntimeError(
            "surface scalar did not vary across the polydata: range "
            "{0}".format(scalar_range)
        )

    path = os.path.join(output_dir, "surface_polydata.vtp")
    SaveData(path, proxy=varying, PointDataArrays=[TARGET_SCALAR])
    log(
        "wrote {0} (scalar range {1}, isovalue {2})".format(
            path, scalar_range, isovalue
        )
    )
    manifest["polydata"] = {
        "path": os.path.basename(path),
        "topology": "polydata surface (triangles)",
        "scalar": TARGET_SCALAR,
        "association": "POINTS",
        "scalar_range": scalar_range,
        "contour_value": isovalue,
        # The input is 2D, so its contour is 1D. ex09 reads this to decide
        # whether the contour can carry a frame on its own (a surface can) or
        # needs its input drawn underneath it (a curve does). Stated here
        # because the generator is what knows; a vignette would be guessing.
        "contour_is_lower_dimensional": True,
        "note": "Already a surface, so `scalar` here is the Y coordinate "
        "rather than the wavelet field: contouring the surface at its own "
        "defining isovalue is empty by construction. Contouring this at the "
        "recorded value yields isolines, which is the degenerate-input case "
        "ex09 exists to exercise.",
    }
    Delete(varying)
    Delete(surface)


def write_ragged_multiblock(base, output_dir, manifest):
    """Multiblock whose blocks are deliberately different sizes.

    Even decompositions hide off-by-one errors. These voxel-of-interest
    extents share faces but have unequal spans in every axis, so a reader or
    filter that assumes uniform partitioning produces visible seams here.
    """
    lo, hi = WAVELET_EXTENT[0], WAVELET_EXTENT[1]
    mid_a = lo + 11  # deliberately not the midpoint
    mid_b = lo + 31

    voi_specs = [
        ("block_small", [lo, mid_a, lo, hi, lo, hi]),
        ("block_medium", [mid_a, mid_b, lo, hi, lo, hi]),
        ("block_large", [mid_b, hi, lo, hi, lo, hi]),
    ]

    # VisIt's VTK reader does not consume a .vtm, so each block is also
    # written as a standalone .vti indexed by a .visit file. That is VisIt's
    # native multi-domain idiom and gives the VisIt half of ex09 a genuinely
    # ragged partitioned dataset rather than a substitute.
    blocks_dir = os.path.join(output_dir, "ragged_blocks")
    os.makedirs(blocks_dir, exist_ok=True)

    blocks = []
    block_report = []
    block_files = []

    for index, (name, voi) in enumerate(voi_specs):
        subset = ExtractSubset(Input=base, registrationName="vv_" + name)
        subset.VOI = voi
        UpdatePipeline(proxy=subset)

        info = subset.GetDataInformation()
        block_report.append(
            {
                "name": name,
                "voi": voi,
                "points": int(info.GetNumberOfPoints()),
                "cells": int(info.GetNumberOfCells()),
            }
        )

        block_filename = "ragged_block_{0:02d}.vti".format(index)
        SaveData(
            os.path.join(blocks_dir, block_filename),
            proxy=subset,
            PointDataArrays=[TARGET_SCALAR],
        )
        block_files.append(block_filename)

        blocks.append(subset)

    group = GroupDatasets(Input=blocks, registrationName="vv_ragged")
    UpdatePipeline(proxy=group)

    path = os.path.join(output_dir, "ragged_multiblock.vtm")
    SaveData(path, proxy=group, PointDataArrays=[TARGET_SCALAR])
    log("wrote {0}".format(path))

    # Paths inside a .visit index are resolved relative to the index file, so
    # this stays correct wherever the data directory is moved to.
    visit_index = os.path.join(output_dir, "ragged_multidomain.visit")
    with open(visit_index, "w") as handle:
        handle.write("!NBLOCKS {0}\n".format(len(block_files)))
        for block_filename in block_files:
            handle.write("ragged_blocks/{0}\n".format(block_filename))
    log("wrote {0}".format(visit_index))

    sizes = [entry["points"] for entry in block_report]
    manifest["ragged"] = {
        "path": os.path.basename(path),
        "visit_path": os.path.basename(visit_index),
        "topology": "multiblock dataset (unequal blocks)",
        "scalar": TARGET_SCALAR,
        "association": "POINTS",
        "scalar_range": point_array_range(base, TARGET_SCALAR),
        "contour_value": CONTOUR_VALUE,
        "blocks": block_report,
        "deliberately_ragged": len(set(sizes)) > 1,
    }

    Delete(group)
    for block in blocks:
        Delete(block)


def _save_amr(produced, output_dir):
    """Write the AMR hierarchy, trying each extension this ParaView may know.

    Returns (path, None) on success and (None, error) when no writer in this
    build accepted any of them. Probing rather than branching on the ParaView
    version keeps this correct for builds that carry both writers and for
    whatever the next release renames it to, provided the name is added here.
    """
    last_error = None
    for extension in AMR_EXTENSIONS:
        path = os.path.join(output_dir, "amr_hierarchy" + extension)
        try:
            SaveData(path, proxy=produced)
        except Exception as exc:  # noqa: BLE001 - probing for a usable writer
            last_error = exc
            continue
        if os.path.exists(path):
            return path, None
        last_error = RuntimeError(
            "the writer for {0} was accepted but produced no file".format(extension)
        )
    return None, last_error


def write_amr(output_dir, manifest):
    """Overlapping AMR hierarchy.

    ParaView's AMRGaussianPulseSource is the reliable way to obtain a real
    vtkOverlappingAMR without hand-assembling vtkAMRBox objects, whose Python
    API has changed shape across VTK 9.x releases.

    The pulse array is cell-centred and named "Gaussian-Pulse". This converts
    it to point data and renames it, and if either step is unavailable in the
    installed ParaView the native array name is recorded in the manifest so
    the vignettes still know what to contour.
    """
    try:
        amr = AMRGaussianPulseSource(registrationName="vv_amr")
    except (NameError, RuntimeError) as exc:
        log(
            "AMRGaussianPulseSource unavailable ({0}). Skipping the AMR "
            "dataset; ex09 will fail on the missing manifest entry, which is "
            "the honest outcome -- it cannot test a topology that does not "
            "exist.".format(exc)
        )
        manifest["amr"] = {
            "path": None,
            "topology": "overlapping AMR",
            "available": False,
            "reason": str(exc),
        }
        return

    UpdatePipeline(proxy=amr)

    scalar_name = TARGET_SCALAR
    association = "POINTS"
    produced = amr

    try:
        to_points = CellDatatoPointData(Input=amr, registrationName="vv_amr_points")
        to_points.CellDataArraytoprocess = ["Gaussian-Pulse"]
        UpdatePipeline(proxy=to_points)

        renamed = Calculator(Input=to_points, registrationName="vv_amr_named")
        renamed.AttributeType = "Point Data"
        renamed.ResultArrayName = TARGET_SCALAR
        renamed.Function = '"Gaussian-Pulse"'
        UpdatePipeline(proxy=renamed)
        produced = renamed
    except Exception as exc:  # noqa: BLE001 - report and degrade, never guess
        log(
            "Could not rename the AMR array ({0}); keeping the native "
            "cell array name.".format(exc)
        )
        scalar_name = "Gaussian-Pulse"
        association = "CELLS"
        produced = amr

    path, write_error = _save_amr(produced, output_dir)
    if path is None:
        log(
            "No AMR writer in this ParaView accepted {0} ({1}). Recording the "
            "dataset as unavailable.".format(" or ".join(AMR_EXTENSIONS), write_error)
        )
        manifest["amr"] = {
            "path": None,
            "topology": "overlapping AMR",
            "available": False,
            "reason": str(write_error),
        }
        return

    # The Gaussian pulse's range is a property of the source, not something
    # to assume. amr_contour_value() returned 0.5 down both of its branches;
    # the pulse actually tops out near 0.33, so ex09's AMR contour was empty
    # on every run and the assertion that it produced geometry always failed.
    scalar_range = (
        point_array_range(produced, scalar_name) if association == "POINTS" else None
    )
    isovalue = interior_value(scalar_range)
    if isovalue is None:
        isovalue = AMR_FALLBACK_CONTOUR_VALUE
        log(
            "could not measure the AMR scalar range; falling back to "
            "isovalue {0}".format(isovalue)
        )

    log(
        "wrote {0} (scalar range {1}, isovalue {2})".format(
            path, scalar_range, isovalue
        )
    )
    manifest["amr"] = {
        "path": os.path.basename(path),
        "topology": "overlapping AMR hierarchy",
        "scalar": scalar_name,
        "association": association,
        "available": True,
        "scalar_range": scalar_range,
        "contour_value": isovalue,
    }


def amr_contour_value(manifest):
    """Isovalue for the AMR dataset, kept for backwards compatibility.

    Every dataset now records its own measured `contour_value`, and that is
    what the vignettes read. This top-level key is preserved so a manifest
    consumer written against the previous layout still finds it -- but it
    reports the measured value rather than the constant 0.5 it used to
    return down both branches, which was above the pulse's actual maximum.
    """
    entry = manifest.get("amr", {})
    recorded = entry.get("contour_value")
    if recorded is not None:
        return float(recorded)
    return AMR_FALLBACK_CONTOUR_VALUE


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate the static topology datasets used by ex09 and "
        "the shared scalar field used by ex07, ex08, ex10 and ex12.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Destination directory. Defaults to <repo>/data/topologies.",
    )
    args, _unknown = parser.parse_known_args(argv)

    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    else:
        data_dir = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(data_dir, "topologies")

    os.makedirs(output_dir, exist_ok=True)
    log("output directory: {0}".format(output_dir))

    # Provenance. These datasets are NOT portable between ParaView major.minor
    # versions and the failure is silent: an AMR hierarchy written by 6.1.0 is
    # opened without complaint by 6.0.1, which then reads 216 points and 125
    # cells where 6.1.0 wrote 842 and 605. Nothing errors; ex09 simply reports
    # different numbers and fails its numeric gate for a reason that looks
    # nothing like "your data was generated by a different ParaView".
    #
    # Recording the version here lets the vignettes say so instead.
    manifest = {
        "generator": "make_topology_datasets.py",
        "paraview_version": _paraview_version_string(),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "target_scalar": TARGET_SCALAR,
        "contour_value": CONTOUR_VALUE,
        "wavelet_extent": WAVELET_EXTENT,
        "datasets": {},
    }
    datasets = manifest["datasets"]

    base = build_base_field()
    write_uniform(base, output_dir, datasets)
    write_tetrahedra(base, output_dir, datasets)
    write_polydata(base, output_dir, datasets)
    write_ragged_multiblock(base, output_dir, datasets)
    write_amr(output_dir, datasets)

    manifest["amr_contour_value"] = amr_contour_value(datasets)

    manifest_path = os.path.join(output_dir, "topologies_manifest.json")
    with open(manifest_path, "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    log("wrote {0}".format(manifest_path))

    log("done -- {0} dataset(s) described".format(len(datasets)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
