#
# Visualization Vignettes
#
# ex09_visitMeshTopologies -- one pipeline, four mesh topologies
#
# WHAT THIS VIGNETTE DEMONSTRATES
#
#   The VisIt counterpart to ex09_pvMeshTopologies. One identical pipeline --
#   contour the shared scalar, query node and zone counts, render a frame --
#   run across four structurally different datasets.
#
# WHICH FOUR, AND WHY THEY DIFFER FROM THE PARAVIEW SET
#
#     unstructured  tetra_unstructured.vtu    explicit tetrahedral cells
#     polydata      surface_polydata.vtp      triangulated surface
#     uniform       scalar_field.vti          uniform image data
#     ragged        ragged_multidomain.visit  UNEQUAL multi-domain blocks
#
#   The ragged case is the one that earns its keep: blocks with different
#   spans in every axis, because an even decomposition is exactly what hides
#   off-by-one errors in partitioned readers.
#
#   ParaView's fourth topology is an overlapping AMR hierarchy in a .vth.
#   VisIt's VTK reader does not consume .vth, and VisIt reads AMR from Silo,
#   Chombo or BoxLib instead. Rather than pretend otherwise, this vignette
#   substitutes uniform image data as its fourth topology and reports the AMR
#   gap explicitly in its notes. If AMR coverage in VisIt matters to you, the
#   honest route is a Silo or Chombo AMR dataset, not a .vth.
#
#   The ragged multi-domain index is genuinely VisIt-native: a .visit file
#   with !NBLOCKS listing three unequal .vti blocks, written by
#   data/make_topology_datasets.py.
#
# DATA
#
#   Produced once by:  pvbatch data/make_topology_datasets.py
#
# RUNNING IT
#
#   visit -cli -nowin -s ex09_visitMeshTopologies.py
#   visit -cli -nowin -s ex09_visitMeshTopologies.py --only ragged
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
    except NameError:  # pragma: no cover - VisIt CLI without __file__
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


VIGNETTE = "ex09_visitMeshTopologies"
TOOL = "VisIt"

# (key, manifest key, label). The manifest key names the record that carries
# the scalar name; the dataset key names the file VisIt should open.
TOPOLOGIES = (
    ("tetra", "tetra", "path", "unstructured tetrahedra"),
    ("polydata", "polydata", "path", "polydata surface"),
    ("uniform", "uniform", "path", "uniform image data"),
    ("ragged", "ragged", "visit_path", "ragged multi-domain"),
)


def add_arguments(parser):
    parser.add_argument(
        "--only",
        choices=[key for key, _m, _p, _l in TOPOLOGIES],
        default=None,
        help="Process a single topology instead of all four.",
    )


def query_value(name, **kwargs):
    """Run a VisIt query and return its numeric output.

    A query against a plot that failed returns None, and the callers feed
    that straight into int() -- so the symptom is a TypeError about NoneType
    several lines away from the plot that actually broke. Failing here names
    the query instead.
    """
    Query(name, **kwargs)
    value = GetQueryOutputValue()
    if value is None:
        raise vc.VignetteError(
            "VisIt query {0!r} returned no value. The plot is usually already "
            "in an error state by this point -- check the log above for the "
            "reason.".format(name)
        )
    return value


def configure_annotations():
    annotation = AnnotationAttributes()
    annotation.userInfoFlag = 0
    annotation.databaseInfoFlag = 0
    annotation.legendInfoFlag = 0
    SetAnnotationAttributes(annotation)


def save_attributes(ctx, filename):
    save_atts = SaveWindowAttributes()
    save_atts.family = 0
    save_atts.format = save_atts.PNG
    save_atts.width = ctx.args.image_width
    save_atts.height = ctx.args.image_height
    save_atts.resConstraint = save_atts.NoConstraint
    save_atts.outputToCurrentDirectory = 0
    save_atts.outputDirectory = ctx.output_dir
    save_atts.fileName = filename
    return save_atts


def process_topology(ctx, manifest, key, manifest_key, path_field, label):
    """Open, contour, query and render one topology. Returns a report dict."""
    ctx.log("-" * 60)
    ctx.log("topology: {0} ({1})".format(key, label))

    entry = manifest.get("datasets", {}).get(manifest_key) or {}
    filename = entry.get(path_field)
    if not filename:
        raise vc.VignetteError(
            "Manifest has no '{0}' for topology '{1}'. Re-run "
            "data/make_topology_datasets.py.".format(path_field, manifest_key)
        )

    path = os.path.join(ctx.data_dir, "topologies", filename)
    if not os.path.exists(path):
        raise vc.VignetteError(
            "Manifest lists {0} but the file is absent: {1}".format(key, path)
        )

    scalar = entry.get("scalar", vc.TOPOLOGY_SCALAR)
    # Each dataset records the isovalue measured from its own data. The
    # polydata surface is the case that matters: it carries a coordinate
    # rather than the wavelet field, because contouring a surface at its own
    # defining isovalue is empty by construction. The top-level key is the
    # fallback for a manifest from an older generator.
    isovalue = float(entry.get("contour_value", manifest.get("contour_value", 150.0)))

    ctx.log("  file      : {0}".format(filename))
    ctx.log("  scalar    : {0}".format(scalar))
    ctx.log("  isovalue  : {0}".format(isovalue))

    with ctx.phase("io_{0}".format(key)):
        if not OpenDatabase(path, 0):
            raise vc.VignetteError("OpenDatabase failed for {0}".format(path))

    AddPlot("Pseudocolor", scalar, 1, 0)

    pc_atts = PseudocolorAttributes()
    # viridis IS a VisIt colour table -- it just is not one of the 18 that
    # are compiled in. It ships as a .ct under the install's resources, which
    # -noconfig stops VisIt loading, so it has to be added explicitly.
    #
    # Without that, VisIt does not refuse the name here. The plot fails
    # asynchronously with "There is no color table named viridis", after
    # which every query against it returns None, and the vignette died three
    # steps later on int(None) with nothing pointing at the colour table.
    pc_atts.colorTableName = vc.ensure_color_table(
        ctx,
        "viridis",
        ColorTableNames,
        AddColorTable,
        ColorControlPointList,
        ColorControlPoint,
    )
    SetPlotOptions(pc_atts)

    configure_annotations()

    # Raw geometry, before the isosurface operator is applied.
    with ctx.phase("draw_{0}".format(key)):
        DrawPlots()

    input_nodes = int(query_value("NumNodes", use_actual_data=1))
    input_zones = int(query_value("NumZones", use_actual_data=1))
    ctx.log("  input     : {0} nodes, {1} zones".format(input_nodes, input_zones))

    minmax = query_value("MinMax", use_actual_data=1)
    if isinstance(minmax, (list, tuple)) and len(minmax) >= 2:
        scalar_min, scalar_max = float(minmax[0]), float(minmax[1])
    else:
        scalar_min = scalar_max = 0.0

    # -- context, where the contour would otherwise be a hairline ---------
    #
    # Same reasoning as ParaView's ex09: a 2D input contours to a 1D curve,
    # which on its own is about 1% ink in a 1024x1024 frame. The input gets
    # drawn underneath, and the isoline is thickened and given a flat white
    # table so it does not take the colour of whatever it is lying on.
    #
    # Order matters. VisIt applies an operator to the ACTIVE plot, so the
    # context plot is added first and the plot that will carry the
    # Isosurface operator is made active again before it goes on.
    if entry.get("contour_is_lower_dimensional"):
        AddPlot("Pseudocolor", scalar, 1, 0)
        context_atts = PseudocolorAttributes()
        context_atts.colorTableName = pc_atts.colorTableName
        context_atts.legendFlag = 0
        SetPlotOptions(context_atts)

        # Put the contoured plot back in front for the operator and the
        # queries that follow it.
        SetActivePlots((0,))
        iso_atts_line = PseudocolorAttributes()
        iso_atts_line.colorTableName = vc.ensure_flat_color_table(
            ctx,
            "VV Isoline",
            (1.0, 1.0, 1.0),
            ColorTableNames,
            AddColorTable,
            ColorControlPointList,
            ColorControlPoint,
        )
        iso_atts_line.lineWidth = 4
        iso_atts_line.legendFlag = 0
        SetPlotOptions(iso_atts_line)
        ctx.log("  drew the input surface as context for a 1D contour")

    # -- contour ----------------------------------------------------------
    AddOperator("Isosurface")
    iso_atts = IsosurfaceAttributes()
    iso_atts.contourMethod = iso_atts.Value
    iso_atts.contourValue = (isovalue,)
    iso_atts.variable = scalar
    SetOperatorOptions(iso_atts)

    with ctx.phase("contour_{0}".format(key)):
        DrawPlots()

    contour_nodes = int(query_value("NumNodes", use_actual_data=1))
    contour_zones = int(query_value("NumZones", use_actual_data=1))
    ctx.log("  contour   : {0} nodes, {1} zones".format(contour_nodes, contour_zones))

    # -- render -----------------------------------------------------------
    ResetView()
    image_name = "{0}_{1}.png".format(VIGNETTE, key)
    SetSaveWindowAttributes(save_attributes(ctx, image_name))

    with ctx.phase("render_{0}".format(key)):
        SaveWindow()

    image_path = os.path.join(ctx.output_dir, image_name)
    ctx.image_path(image_name)
    width, height = vc.png_size(image_path)

    DeleteAllPlots()
    CloseDatabase(path)

    # -- metrics -----------------------------------------------------------
    ctx.add_metric("{0}_input_nodes".format(key), input_nodes)
    ctx.add_metric("{0}_input_zones".format(key), input_zones)
    ctx.add_metric("{0}_contour_zones".format(key), contour_zones)
    ctx.add_metric("{0}_scalar_min".format(key), round(scalar_min, 6))
    ctx.add_metric("{0}_scalar_max".format(key), round(scalar_max, 6))

    # -- assertions --------------------------------------------------------
    ctx.assert_true(
        "{0}: dataset has geometry".format(key),
        input_nodes > 0 and input_zones > 0,
        "{0} nodes, {1} zones".format(input_nodes, input_zones),
    )
    ctx.assert_true(
        "{0}: contour produced geometry".format(key),
        contour_zones > 0,
        "contour_zones={0} at isovalue {1} over range [{2}, {3}]".format(
            contour_zones, isovalue, scalar_min, scalar_max
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
        "file": filename,
        "scalar": scalar,
        "isovalue": isovalue,
        "input_nodes": input_nodes,
        "input_zones": input_zones,
        "contour_nodes": contour_nodes,
        "contour_zones": contour_zones,
        "scalar_min": scalar_min,
        "scalar_max": scalar_max,
        "io_time_s": ctx.timings.get("io_{0}".format(key), 0.0),
        "contour_time_s": ctx.timings.get("contour_{0}".format(key), 0.0),
        "render_time_s": ctx.timings.get("render_{0}".format(key), 0.0),
    }


def run(ctx):
    vc.open_visit_engine(ctx, OpenComputeEngine)

    manifest = ctx.topology_manifest()
    ctx.log("manifest target scalar: {0}".format(manifest.get("target_scalar")))

    # Recorded so the AMR gap is visible in the results rather than being an
    # unexplained difference between the two ex09 vignettes.
    ctx.notes.append(
        "AMR is covered by ex09_pvMeshTopologies only: VisIt's VTK reader "
        "does not consume .vth. VisIt AMR requires Silo, Chombo or BoxLib."
    )

    selected = TOPOLOGIES
    if ctx.args.only:
        selected = tuple(item for item in TOPOLOGIES if item[0] == ctx.args.only)

    rows = []
    for key, manifest_key, path_field, label in selected:
        rows.append(
            process_topology(ctx, manifest, key, manifest_key, path_field, label)
        )

    ctx.write_timing_csv(filename="{0}_topologies.csv".format(VIGNETTE), rows=rows)
    ctx.add_metric("topologies_processed", len(rows))

    ragged_entry = manifest.get("datasets", {}).get("ragged", {})
    if ragged_entry and any(row["topology"] == "ragged" for row in rows):
        ctx.assert_true(
            "ragged multi-domain really is ragged",
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
        code = ctx.finish()
    except Exception as exc:  # noqa: BLE001 - a vignette must report, not raise
        code = ctx.abort(exc)

    vc.finish_visit_session(
        ctx, code, close_compute_engine=CloseComputeEngine, exit_func=exit
    )


if __name__ == "__main__":
    main()
