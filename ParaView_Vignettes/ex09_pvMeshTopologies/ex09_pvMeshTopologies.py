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

    Two of the four topologies do not share the Wavelet's value range: the
    AMR Gaussian pulse tops out near 0.33, and the polydata surface carries
    a coordinate rather than the wavelet field. The generator measures each
    dataset's range and records an isovalue strictly inside it, so this reads
    that value and hard-codes nothing.

    The two fallbacks exist only for a manifest written by an older generator:
    the per-dataset key first, then the previous top-level keys.
    """
    entry = manifest.get("datasets", {}).get(key) or {}
    recorded = entry.get("contour_value")
    if recorded is not None:
        return float(recorded)

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
        # MergeBlocks accepts a vtkOverlappingAMR in ParaView 6.1 and refuses
        # it in 6.0.1 -- "Input ... is of type vtkOverlappingAMR, but a
        # vtkDataObjectTree is required" -- which matters because Ibex runs
        # 6.0.1 and Shaheen runs 6.1.0. VTK reports that through its error
        # channel rather than raising, so the failure arrives later and in
        # disguise: an empty output, and then "Scalar 'scalar' absent from
        # amr_hierarchy.vthb. Available point arrays: []".
        #
        # Rather than branching on a version, merge and then check whether
        # anything came out. ParaView's Contour takes composite input
        # directly, so the unmerged reader is a perfectly good fallback --
        # flattening was only ever for one predictable code path.
        merged = MergeBlocks(Input=reader, registrationName="ex09_merge_" + key)
        UpdatePipeline(proxy=merged)
        if int(merged.GetDataInformation().GetNumberOfPoints()) > 0:
            source = merged
            ctx.debug("  flattened composite input with MergeBlocks")
        else:
            Delete(merged)
            ctx.warn(
                "MergeBlocks produced no points for '{0}'; this ParaView "
                "cannot flatten that composite type. Contouring the "
                "composite directly instead.".format(key)
            )

    # Cell-centred scalars have to become point-centred before contouring.
    if association == "CELLS":
        source = CellDatatoPointData(Input=source, registrationName="ex09_c2p_" + key)
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
            source.PointData.GetArray(i).GetName() for i in range(len(source.PointData))
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
    ctx.log("  contour   : {0} points, {1} cells".format(contour_points, contour_cells))

    # -- render -----------------------------------------------------------
    #
    # Contouring a 2D input gives a 1D output. On its own that renders as a
    # hairline on an empty background: 0.06% of the frame here, which is an
    # image gate that would pass almost any regression and a picture that
    # shows a reader nothing. Where the manifest says the contour is
    # lower-dimensional than its input, the input is drawn underneath it.
    #
    # Only the picture changes. The pipeline, the queries, the metrics and
    # the assertions below are the same for all four topologies.
    # The lookup table is fetched and rescaled AFTER every Show/ColorBy
    # below, deliberately. Show() auto-rescales a representation's lookup
    # table to its own data range the first time it colours by an array, so
    # presetting and rescaling first has the rescale silently undone -- which
    # is how the three volumetric topologies, which this change was not
    # supposed to touch at all, came back 26.5% different on the first
    # attempt. That is the same 26.5% as the preset bug in section 4.16 of
    # the runbook, and for the same reason: the frame was drawn with a
    # lookup table nobody had actually configured.
    context = None
    if entry.get("contour_is_lower_dimensional"):
        context = Show(source, view)
        context.Representation = "Surface"
        ColorBy(context, ("POINTS", scalar))
        context.SetScalarBarVisibility(view, False)
        ctx.debug("  drew the input surface as context for a 1D contour")

    display = Show(contour, view)
    display.Representation = "Surface"
    if context is None:
        ColorBy(display, ("POINTS", scalar))
    else:
        # The isoline lies exactly ON the surface, so colouring it by the
        # same scalar would paint it the colour of what is directly behind
        # it. Solid white, thickened, reads as an annotation of the surface.
        ColorBy(display, None)
        display.AmbientColor = [1.0, 1.0, 1.0]
        display.DiffuseColor = [1.0, 1.0, 1.0]
        display.LineWidth = 5.0
        try:
            display.RenderLinesAsTubes = 1
        except AttributeError:  # older ParaView; the width alone is enough
            pass
    display.SetScalarBarVisibility(view, False)

    lut = GetColorTransferFunction(scalar)
    # ParaView 6.0 dropped the " (matplotlib)" suffix from these presets
    # and 6.1 raises rather than warning, so both spellings are offered.
    vc.apply_color_preset(lut, ("Viridis", "Viridis (matplotlib)"), ctx)
    lut.RescaleTransferFunction(float(scalar_range[0]), float(scalar_range[1]))

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
    if context is not None:
        Hide(source, view)

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

    # These datasets are generated, not shipped, and they do not survive a
    # ParaView major.minor change -- silently. Check before trusting them.
    vc.check_fixture_version(
        ctx,
        manifest.get("paraview_version"),
        vc.paraview_version_string(),
        "data/topologies (topologies_manifest.json)",
        "pvbatch data/make_topology_datasets.py",
    )

    selected = TOPOLOGIES
    if ctx.args.only:
        selected = tuple(item for item in TOPOLOGIES if item[0] == ctx.args.only)

    view = build_view(ctx)

    rows = []
    for key, label in selected:
        rows.append(process_topology(ctx, manifest, view, key, label))

    ctx.write_timing_csv(filename="{0}_topologies.csv".format(VIGNETTE), rows=rows)

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
    vc.exit_vignette(main())
