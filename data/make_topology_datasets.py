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
#   amr_hierarchy.vth         overlapping AMR hierarchy
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
import json
import os
import sys

from paraview.simple import *  # noqa: F401,F403


# The scalar every dataset should expose, and the isovalue the vignettes
# contour at. Chosen to sit inside the Wavelet source's natural RTData range
# (roughly 37 to 276) so the contour is non-empty on every topology.
TARGET_SCALAR = "scalar"
CONTOUR_VALUE = 150.0

# Wavelet extent. 51^3 points is large enough that a contour has real
# geometry to compare and small enough that the whole set of datasets stays
# a few tens of megabytes.
WAVELET_EXTENT = [-25, 25, -25, 25, -25, 25]


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
    }
    Delete(tets)


def write_polydata(base, output_dir, manifest):
    """Triangulated polygonal surface carrying the same scalar."""
    surface = Contour(Input=base, registrationName="vv_surface")
    surface.ContourBy = ["POINTS", TARGET_SCALAR]
    surface.Isosurfaces = [CONTOUR_VALUE]
    surface.PointMergeMethod = "Uniform Binning"
    UpdatePipeline(proxy=surface)

    path = os.path.join(output_dir, "surface_polydata.vtp")
    SaveData(path, proxy=surface, PointDataArrays=[TARGET_SCALAR])
    log("wrote {0}".format(path))
    manifest["polydata"] = {
        "path": os.path.basename(path),
        "topology": "polydata surface (triangles)",
        "scalar": TARGET_SCALAR,
        "association": "POINTS",
        "note": "Already a surface; ex09 contours it in-plane to exercise the "
        "degenerate case rather than skipping it.",
    }
    Delete(surface)


def write_ragged_multiblock(base, output_dir, manifest):
    """Multiblock whose blocks are deliberately different sizes.

    Even decompositions hide off-by-one errors. These voxel-of-interest
    extents share faces but have unequal spans in every axis, so a reader or
    filter that assumes uniform partitioning produces visible seams here.
    """
    lo, hi = WAVELET_EXTENT[0], WAVELET_EXTENT[1]
    mid_a = lo + 11   # deliberately not the midpoint
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
        "blocks": block_report,
        "deliberately_ragged": len(set(sizes)) > 1,
    }

    Delete(group)
    for block in blocks:
        Delete(block)


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
    path = os.path.join(output_dir, "amr_hierarchy.vth")

    try:
        amr = AMRGaussianPulseSource(registrationName="vv_amr")
    except (NameError, RuntimeError) as exc:
        log(
            "AMRGaussianPulseSource unavailable ({0}). Skipping the AMR "
            "dataset; ex09 will report it as unavailable rather than "
            "failing.".format(exc)
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
        to_points = CellDatatoPointData(
            Input=amr, registrationName="vv_amr_points"
        )
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

    SaveData(path, proxy=produced)
    log("wrote {0}".format(path))
    manifest["amr"] = {
        "path": os.path.basename(path),
        "topology": "overlapping AMR hierarchy",
        "scalar": scalar_name,
        "association": association,
        "available": True,
    }


def amr_contour_value(manifest):
    """Isovalue for the AMR dataset.

    The Gaussian pulse spans roughly 0 to 1, so the shared value of 150 would
    produce an empty contour. Recorded in the manifest so ex09 never has to
    hard-code a per-dataset constant.
    """
    entry = manifest.get("amr", {})
    if entry.get("scalar") == TARGET_SCALAR and entry.get("association") == "POINTS":
        return 0.5
    return 0.5


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

    manifest = {
        "generator": "make_topology_datasets.py",
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
