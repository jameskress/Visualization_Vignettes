#
# Visualization Vignettes
#
# ex09_pvMeshTopologies -- one pipeline, four mesh topologies
#
# WHAT THIS VIGNETTE DEMONSTRATES
#
#   Everything else in this repository reads a uniform or rectilinear grid.
#   Real simulations do not. This vignette runs one identical pipeline --
#   contour the shared scalar, query the geometry, render a frame -- across
#   four structurally different datasets:
#
#     unstructured    tetrahedral cells, explicit connectivity
#     amr             overlapping AMR hierarchy, multiple refinement levels
#     polydata        a triangulated surface, where a volume contour becomes
#                     an isoline and the filter has to cope with it
#     ragged          a multiblock whose blocks are deliberately UNEQUAL
#
#   The ragged case is the one that earns its keep. A decomposition whose
#   extents divide evenly is exactly the case that hides off-by-one errors in
#   partitioned readers, writers and filters, so the blocks here have
#   different spans in every axis on purpose.
#
# WHAT IT ASSERTS
#
#   Per topology: the dataset opened, it reports a non-zero point and cell
#   count, the contour produced geometry, and an image was written at the
#   requested resolution. Point and cell counts are recorded as metrics, so a
#   reader that starts dropping a block or an AMR level fails the numeric
#   comparison even when the rendered image still looks plausible.
#
# DATA
#
#   Produced once by data/make_topology_datasets.py:
#     pvbatch data/make_topology_datasets.py
#
#   The generator writes a manifest recording each dataset's scalar name and
#   association. This vignette reads the manifest rather than assuming, since
#   the AMR source's array cannot always be renamed.
#
# RUNNING IT
#
#   pvbatch --force-offscreen-rendering ex09_pvMeshTopologies.py
#   pvbatch --force-offscreen-rendering ex09_pvMeshTopologies.py --only ragged
#
# Author: James Kress, <james@jameskress.com>
#
import os
import sys


def _bootstrap_common():
    """Put Testing/ on sys.path so vignette_common can be imported."""
    here = None
    try:
        here = os.path.abspath(os.path.dirname(__file__))
    except NameError:  # pragma: no cover
        here = None
    if not here and sys.argv and sys.argv[0]:
        here = os.path.abspath(os.path.dirname(sys.argv[0]))
    if not here:
        here = os.getcwd()
    testing = os.path.abspath(os.path.join(here, "..", "..", "Testing"))
    if testing not in sys.path:
        sys.path.insert(0, testing)
    return here


SCRIPT_DIR = _bootstrap_common()

import vignette_common as vc  # noqa: E402

import paraview  # noqa: E402
from paraview.simple import *  # noqa: E402,F401,F403


VIGNETTE = "ex09_pvMeshTopologies"
TOOL = "ParaView"

# Manifest key -> human label. Order is fixed so the report reads the same
# way every run and the images sort predictably.
TOPOLOGIES = (
    ("tetra", "unstructured tetrahedra"),
    ("amr", "overlapping AMR hierarchy"),
    ("polydata", "polydata surface"),
    ("ragged", "ragged multiblock"),
)

# Datasets whose type is composite. ParaView's contour accepts composite
# input, but flattening first gives one predictable code path across
# multiblock and AMR and avoids per-level ghost handling differences between
# ParaView releases.
COMPOSITE_KEYS = ("amr", "ragged")


def add_arguments(parser):
    parser.add_argument(
        "--only",
        choices=[key for key, _ in TOPOLOGIES],
        default=None,
        help="Process a single topology instead of all four.",
    )


def dataset_entry(manifest, key):
    """Manifest record for one topology, or None when it was not produced."""
    entry = manifest.get("datasets", {}).get(key)
    if not entry or not entry.get("path"):
        return None
    return entry


def contour_value_for(manifest, key):
    """Isovalue appropriate to this dataset.

    The AMR Gaussian pulse spans roughly 0 to 1, so the shared value used for
    the Wavelet-derived datasets would produce an empty contour there. The
    generator records the right value; this never hard-codes a constant.
    """
    if key == "amr":
        return float(manifest.get("amr_contour_value", 0.5))
    return float(manifest.get("contour_value", 150.0))


def build_view(ctx):
    view = GetActiveViewOrCreate("RenderView")
    view.ViewSize = [ctx.args.image_width, ctx.args.image_height]
    view.ShowAnnotation = False
    view.OrientationAxesVisibility = 0
    view.UseColorPaletteForBackground = 0
    view.BackgroundColorMode = "Single Color"
    view.Background = [0.09, 0.10, 0.12]
    return view


def process_topology(ctx, manifest, view, key, label):
    """Open, contour, query and render one topology. Returns a report dict."""
    ctx.log("-" * 60)
    ctx.log("topology: {0} ({1})".format(key, label))

    entry = dataset_entry(manifest, key)
    if entry is None:
        reason = (manifest.get("datasets", {}).get(key) or {}).get(
            "reason", "not produced by make_topology_datasets.py"
        )
        raise vc.VignetteError(
            "Topology '{0}' is missing from the manifest: {1}. Re-run "
            "data/make_topology_datasets.py.".format(key, reason)
        )

    path = os.path.join(ctx.data_dir, "topologies", entry["path"])
    if not os.path.exists(path):
        raise vc.VignetteError(
            "Manifest lists {0} but the file is absent: {1}".format(key, path)
        )

    scalar = entry.get("scalar", vc.TOPOLOGY_SCALAR)
    association = entry.get("association", "POINTS")
    isovalue = contour_value_for(manifest, key)

    ctx.log("  file      : {0}".format(os.path.basename(path)))
    ctx.log("  scalar    : {0} ({1})".format(scalar, association))
    ctx.log("  isovalue  : {0}".format(isovalue))

    # OpenDataFile picks the reader from the extension, which keeps this
    # working across .vti / .vtu / .vtp / .vtm / .vth without a lookup table
    # that would need updating whenever ParaView renames a reader proxy.
    with ctx.phase("io_{0}".format(key)):
        reader = OpenDataFile(path)
        if reader is None:
            raise vc.VignetteError("No reader available for {0}".format(path))
        UpdatePipeline(proxy=reader)

    source = reader
    if key in COMPOSITE_KEYS:
        source = MergeBlocks(Input=reader, registrationName="ex09_merge_" + key)
        UpdatePipeline(proxy=source)
        ctx.debug("  flattened composite input with MergeBlocks")

    # Cell-centred scalars have to become point-centred before contouring.
    if association == "CELLS":
        source = CellDatatoPointData(
            Input=source, registrationName="ex09_c2p_" + key
        )
        source.CellDataArraytoprocess = [scalar]
        UpdatePipeline(proxy=source)
        ctx.debug("  converted cell scalar '{0}' to point data".format(scalar))

    info = source.GetDataInformation()
    input_points = int(info.GetNumberOfPoints())
    input_cells = int(info.GetNumberOfCells())
    ctx.log("  input     : {0} points, {1} cells".format(input_points, input_cells))

    array_info = source.PointData.GetArray(scalar)
    if array_info is None:
        available = [
            source.PointData.GetArray(i).GetName()
            for i in range(len(source.PointData))
        ]
        raise vc.VignetteError(
            "Scalar '{0}' absent from {1}. Available point arrays: {2}".format(
                scalar, os.path.basename(path), available
            )
        )
    scalar_range = array_info.GetRange(0)

    with ctx.phase("contour_{0}".format(key)):
        contour = Contour(Input=source, registrationName="ex09_contour_" + key)
        contour.ContourBy = ["POINTS", scalar]
        contour.Isosurfaces = [isovalue]
        contour.PointMergeMethod = "Uniform Binning"
        UpdatePipeline(proxy=contour)

    contour_info = contour.GetDataInformation()
    contour_points = int(contour_info.GetNumberOfPoints())
    contour_cells = int(contour_info.GetNumberOfCells())
    ctx.log(
        "  contour   : {0} points, {1} cells".format(contour_points, contour_cells)
    )

    # -- render -----------------------------------------------------------
    display = Show(contour, view)
    display.Representation = "Surface"
    ColorBy(display, ("POINTS", scalar))
    lut = GetColorTransferFunction(scalar)
    lut.ApplyPreset("Viridis (matplotlib)", True)
    lut.RescaleTransferFunction(float(scalar_range[0]), float(scalar_range[1]))
    display.SetScalarBarVisibility(view, False)

    ResetCamera(view)

    image_name = "{0}_{1}.png".format(VIGNETTE, key)
    image_path = ctx.image_path(image_name)
    with ctx.phase("render_{0}".format(key)):
        Render(view)
        SaveScreenshot(
            image_path,
            view,
            ImageResolution=[ctx.args.image_width, ctx.args.image_height],
        )

    width, height = vc.png_size(image_path)

    Hide(contour, view)

    # -- metrics ----------------------------------------------------------
    ctx.add_metric("{0}_input_points".format(key), input_points)
    ctx.add_metric("{0}_input_cells".format(key), input_cells)
    ctx.add_metric("{0}_contour_cells".format(key), contour_cells)
    ctx.add_metric("{0}_scalar_min".format(key), round(float(scalar_range[0]), 6))
    ctx.add_metric("{0}_scalar_max".format(key), round(float(scalar_range[1]), 6))

    # -- assertions -------------------------------------------------------
    ctx.assert_true(
        "{0}: dataset has geometry".format(key),
        input_points > 0 and input_cells > 0,
        "{0} points, {1} cells".format(input_points, input_cells),
    )
    ctx.assert_true(
        "{0}: contour produced geometry".format(key),
        contour_cells > 0,
        "contour_cells={0} at isovalue {1} over range [{2}, {3}]".format(
            contour_cells, isovalue, scalar_range[0], scalar_range[1]
        ),
    )
    ctx.assert_true(
        "{0}: image written at requested resolution".format(key),
        (width, height) == (ctx.args.image_width, ctx.args.image_height),
        "requested {0}x{1}, got {2}x{3}".format(
            ctx.args.image_width, ctx.args.image_height, width, height
        ),
    )

    return {
        "topology": key,
        "label": label,
        "file": os.path.basename(path),
        "scalar": scalar,
        "isovalue": isovalue,
        "input_points": input_points,
        "input_cells": input_cells,
        "contour_points": contour_points,
        "contour_cells": contour_cells,
        "scalar_min": float(scalar_range[0]),
        "scalar_max": float(scalar_range[1]),
        "io_time_s": ctx.timings.get("io_{0}".format(key), 0.0),
        "contour_time_s": ctx.timings.get("contour_{0}".format(key), 0.0),
        "render_time_s": ctx.timings.get("render_{0}".format(key), 0.0),
    }


def run(ctx):
    paraview.simple._DisableFirstRenderCameraReset()

    manifest = ctx.topology_manifest()
    ctx.log("manifest target scalar: {0}".format(manifest.get("target_scalar")))

    selected = TOPOLOGIES
    if ctx.args.only:
        selected = tuple(item for item in TOPOLOGIES if item[0] == ctx.args.only)

    view = build_view(ctx)

    rows = []
    for key, label in selected:
        rows.append(process_topology(ctx, manifest, view, key, label))

    ctx.write_timing_csv(
        filename="{0}_topologies.csv".format(VIGNETTE), rows=rows
    )

    ctx.add_metric("topologies_processed", len(rows))

    # The ragged multiblock is only doing its job if its blocks really are
    # unequal. If the generator ever starts producing even blocks, this
    # vignette stops testing what it claims to test -- so check it.
    ragged_entry = manifest.get("datasets", {}).get("ragged", {})
    if ragged_entry and any(row["topology"] == "ragged" for row in rows):
        ctx.assert_true(
            "ragged multiblock really is ragged",
            bool(ragged_entry.get("deliberately_ragged")),
            "block point counts: {0}".format(
                [b["points"] for b in ragged_entry.get("blocks", [])]
            ),
        )


def main():
    args = vc.parse_args(
        VIGNETTE,
        TOOL,
        description="Run one contour pipeline across four mesh topologies.",
        extend=add_arguments,
    )
    ctx = vc.VignetteContext(VIGNETTE, TOOL, args, script_dir=SCRIPT_DIR)
    try:
        run(ctx)
    except Exception as exc:  # noqa: BLE001 - a vignette must report, not raise
        return ctx.abort(exc)
    return ctx.finish()


if __name__ == "__main__":
    sys.exit(main())
