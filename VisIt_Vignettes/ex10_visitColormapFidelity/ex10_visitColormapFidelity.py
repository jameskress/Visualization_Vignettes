#
# Visualization Vignettes
#
# ex10_visitColormapFidelity -- four colour table configurations, one field
#
# WHY THIS VIGNETTE EXISTS
#
#   The VisIt counterpart to ex10_pvColormapFidelity, over the same dataset
#   and the same scalar, so the two suites can be read side by side.
#
#   Colour mapping is the most version-fragile part of a visualisation
#   script and the most common source of "the picture changed after the
#   upgrade". Colour table names get renamed, legend layout properties move,
#   and a log scale over a range that reaches zero is silently clamped.
#   Nothing else in this suite covers any of it.
#
# THE FOUR CONFIGURATIONS
#
#   preset       a built-in VisIt colour table applied by name
#   custom       a colour table read from ex10_ember.ct and registered at run
#                time with AddColorTable()
#   log          the same custom table with Pseudocolor scaling set to Log,
#                over a range forced strictly positive first
#   categorical  a DISCRETE colour table from ex10_categorical.ct, applied to
#                a derived integer field so each band means one category
#
#   Every configuration renders with its colour legend visible and explicitly
#   positioned and formatted, because the legend is where colour table and
#   number-format drift shows up first.
#
# HOW THIS DIFFERS FROM THE PARAVIEW VIGNETTE, AND WHY
#
#   ParaView imports a preset XML with ImportPresets() and applies it by
#   name. VisIt has no equivalent import for an arbitrary path: the GUI reads
#   .ct files from the user's .visit directory at startup. Rather than write
#   into a home directory, this vignette parses the .ct itself and registers
#   the table through AddColorTable(), which is the documented run-time
#   route. The .ct files stay in VisIt's own format, so they can also simply
#   be copied into ~/.visit and used from the GUI.
#
#   ParaView's categorical mode is InterpretValuesAsCategories on an indexed
#   map. VisIt's nearest native equivalent is a colour table with
#   discreteFlag set, which assigns each control point to one band instead of
#   interpolating between them. That is what ex10_categorical.ct carries.
#
# WHAT IT ASSERTS
#
#   Per configuration: the colour table the plot ended up with is the one
#   that was asked for, the legend is active, and an image was written at the
#   requested resolution. Plus the two structural properties that break
#   quietly across versions: log scaling actually enabled over a strictly
#   positive range, and the discrete table actually registered with the
#   expected number of control points.
#
#   The rendered images are the real assertion; the metrics exist so that a
#   change is reported as a named property rather than only as a pixel diff.
#
# DATA
#
#   data/varying_data/varying00.vtk, point scalar "temp". Shipped with the
#   repository; no preparation step required.
#
# RUNNING IT
#
#   visit -cli -nowin -s ex10_visitColormapFidelity.py
#   visit -cli -nowin -s ex10_visitColormapFidelity.py --only log
#
# Author: James Kress, <james@jameskress.com>
#
import os
import sys
import xml.etree.ElementTree as ET


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


VIGNETTE = "ex10_visitColormapFidelity"
TOOL = "VisIt"

# Registered names. Deliberately the same strings the ParaView vignette uses
# for the equivalent maps, so a reader moving between the two suites is
# looking at the same names as well as the same colours.
CUSTOM_TABLE_NAME = "VV Ember"
CATEGORICAL_TABLE_NAME = "VV Categorical"

CUSTOM_CT = "ex10_ember.ct"
CATEGORICAL_CT = "ex10_categorical.ct"

CONFIGURATIONS = ("preset", "custom", "log", "categorical")

# Bins the categorical field is quantised into. Must match the number of
# control points in ex10_categorical.ct; the vignette checks that it does.
CATEGORY_COUNT = 5

CATEGORY_EXPRESSION = "category"


def add_arguments(parser):
    parser.add_argument(
        "--only",
        choices=CONFIGURATIONS,
        default=None,
        help="Render a single configuration instead of all four.",
    )
    parser.add_argument(
        "--preset",
        default="hot_desaturated",
        help="Built-in VisIt colour table used by the 'preset' configuration.",
    )
    parser.add_argument(
        "--scalar",
        default=vc.SHARED_SCALAR,
        help="Point scalar to colour by.",
    )


# ---------------------------------------------------------------------------
# Colour table loading
# ---------------------------------------------------------------------------
def read_color_table(path):
    """Parse a VisIt .ct file into control points and flags.

    Driven by the file's structure rather than by hard-coded offsets, so a
    .ct saved from the VisIt GUI, which may carry extra fields and a
    different number of points, loads just as well as the ones shipped here.

    Returns {"points": [((r, g, b, a), position), ...], "smoothing": int,
             "equal_spacing": bool, "discrete": bool}.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise vc.VignetteError(
            "Colour table {0} is not well-formed XML: {1}\n"
            "  A double hyphen inside an XML comment is the usual "
            "cause.".format(path, exc)
        )

    ccpl = tree.getroot().find("./Object[@name='ColorControlPointList']")
    if ccpl is None:
        raise vc.VignetteError(
            "Colour table {0} has no ColorControlPointList object.".format(path)
        )

    points = []
    for node in ccpl.findall("./Object[@name='ColorControlPoint']"):
        colors_field = node.find("Field[@name='colors']")
        position_field = node.find("Field[@name='position']")
        if colors_field is None or position_field is None:
            raise vc.VignetteError(
                "Colour table {0} has a control point missing 'colors' or "
                "'position'.".format(path)
            )
        channels = [int(part) for part in (colors_field.text or "").split()]
        if len(channels) != 4:
            raise vc.VignetteError(
                "Colour table {0} has a control point with {1} channel(s); "
                "RGBA needs 4.".format(path, len(channels))
            )
        points.append((tuple(channels), float(position_field.text)))

    if not points:
        raise vc.VignetteError(
            "Colour table {0} defines no control points.".format(path)
        )

    def flag(name, default=False):
        field = ccpl.find("Field[@name='{0}']".format(name))
        if field is None or field.text is None:
            return default
        return field.text.strip().lower() in ("1", "true", "yes")

    def integer(name, default=0):
        field = ccpl.find("Field[@name='{0}']".format(name))
        if field is None or field.text is None:
            return default
        try:
            return int(field.text.strip())
        except ValueError:
            return default

    return {
        "points": points,
        "smoothing": integer("smoothing", 1),
        "equal_spacing": flag("equalSpacingFlag"),
        "discrete": flag("discreteFlag"),
    }


def set_if_present(ctx, obj, name, value):
    """Set an attribute that some VisIt versions do not expose.

    Reported rather than swallowed. A vignette whose job is to detect drift
    between versions should say when it met some, not quietly render a
    different picture.
    """
    if not hasattr(obj, name):
        ctx.warn(
            "{0} has no attribute '{1}' in this VisIt build; leaving it at "
            "its default.".format(type(obj).__name__, name)
        )
        return False
    setattr(obj, name, value)
    return True


def register_color_table(ctx, name, path):
    """Read a .ct and register it with VisIt under `name`."""
    table = read_color_table(path)

    ccpl = ColorControlPointList()
    for channels, position in table["points"]:
        point = ColorControlPoint()
        point.colors = channels
        point.position = position
        ccpl.AddControlPoints(point)

    set_if_present(ctx, ccpl, "smoothing", table["smoothing"])
    set_if_present(ctx, ccpl, "equalSpacingFlag", 1 if table["equal_spacing"] else 0)
    set_if_present(ctx, ccpl, "discreteFlag", 1 if table["discrete"] else 0)

    AddColorTable(name, ccpl)
    ctx.log(
        "registered colour table '{0}' from {1}: {2} point(s), "
        "discrete={3}".format(
            name, os.path.basename(path), len(table["points"]), table["discrete"]
        )
    )
    return table


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def format_legend(ctx, plot_name, title):
    """Make the colour legend legible and, more importantly, deterministic.

    Every property is set explicitly. Left at their defaults these silently
    restyle themselves between VisIt releases, and every baseline image in
    this vignette then fails for a reason that has nothing to do with the
    colour table.
    """
    legend = GetAnnotationObject(plot_name)

    legend.active = 1
    legend.drawTitle = 1
    legend.drawMinMax = 1

    # managePosition off is what makes the position below stick; with it on,
    # VisIt lays legends out itself and the explicit coordinates are ignored.
    legend.managePosition = 0
    legend.position = (0.86, 0.88)
    legend.xScale = 1.0
    legend.yScale = 2.4

    legend.orientation = legend.VerticalRight
    legend.controlTicks = 1
    legend.numTicks = 5
    legend.minMaxInclusive = 1

    legend.fontFamily = legend.Arial
    legend.fontBold = 1
    legend.fontItalic = 0
    legend.fontHeight = 0.022
    legend.useForegroundForTextColor = 0
    legend.textColor = (240, 242, 247, 255)

    # An explicit format string is the difference between a legend that reads
    # the same on every machine and one whose precision follows the locale
    # and the data range.
    legend.numberFormat = "%# -9.4g"

    set_if_present(ctx, legend, "drawLabels", legend.Values)
    legend.managePosition = 0

    if hasattr(legend, "customTitle"):
        legend.customTitle = title
        legend.useCustomTitle = 1

    return legend


def configure_annotations():
    """Chrome off, legend on.

    Every other vignette in this suite turns legendInfoFlag off. This one
    turns it on deliberately: the legend is the thing under test.
    """
    annotation = AnnotationAttributes()
    annotation.userInfoFlag = 0
    annotation.databaseInfoFlag = 0
    annotation.legendInfoFlag = 1
    annotation.axes3D.visible = 0
    annotation.axes3D.triadFlag = 0
    annotation.axes3D.bboxFlag = 0
    annotation.backgroundMode = annotation.Solid
    annotation.backgroundColor = (23, 26, 31, 255)
    annotation.foregroundColor = (240, 242, 247, 255)
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


def positive_log_range(scalar_range):
    """A strictly positive range suitable for log scaling.

    A log scale over a range that reaches zero or below is undefined, and
    VisIt clamps it quietly. Deriving an explicitly positive range here means
    the vignette controls what is being tested instead of testing the clamp.
    """
    low, high = float(scalar_range[0]), float(scalar_range[1])
    if low > 0.0:
        return low, high
    span = high - low
    safe_low = max(span * 1e-3, 1e-6)
    return safe_low, max(high, safe_low * 10.0)


def render_configuration(ctx, config, scalar, scalar_range, tables):
    """Apply one colour table configuration and render it."""
    ctx.log("-" * 60)
    ctx.log("configuration: {0}".format(config))

    variable = scalar
    table_name = ctx.args.preset
    applied_range = (float(scalar_range[0]), float(scalar_range[1]))
    scaling_is_log = False

    if config == "custom":
        table_name = CUSTOM_TABLE_NAME
    elif config == "log":
        table_name = CUSTOM_TABLE_NAME
        applied_range = positive_log_range(scalar_range)
        scaling_is_log = True
    elif config == "categorical":
        table_name = CATEGORICAL_TABLE_NAME
        variable = CATEGORY_EXPRESSION
        applied_range = (0.0, float(CATEGORY_COUNT - 1))

    AddPlot("Pseudocolor", variable, 1, 0)

    pc_atts = PseudocolorAttributes()
    pc_atts.colorTableName = table_name
    pc_atts.invertColorTable = 0
    pc_atts.opacityType = pc_atts.FullyOpaque
    pc_atts.legendFlag = 1

    # Limits are pinned on every configuration, not just the log one. A plot
    # left on automatic limits recolours itself whenever the data range moves
    # by a hair, which turns a colour-map test into a data test.
    pc_atts.minFlag = 1
    pc_atts.maxFlag = 1
    pc_atts.min = applied_range[0]
    pc_atts.max = applied_range[1]

    if scaling_is_log:
        pc_atts.scaling = pc_atts.Log
    else:
        pc_atts.scaling = pc_atts.Linear

    SetPlotOptions(pc_atts)
    configure_annotations()

    with ctx.phase("draw_{0}".format(config)):
        DrawPlots()

    # Read the attributes back rather than trusting what was set: the whole
    # point of this vignette is to catch a version where the set did not take.
    applied = GetPlotOptions()
    applied_table = getattr(applied, "colorTableName", "")
    applied_scaling = int(getattr(applied, "scaling", 0))
    log_enabled = applied_scaling == int(pc_atts.Log)

    plots = GetPlotList()
    plot_name = plots.GetPlots(plots.numPlots - 1).plotName
    legend = format_legend(ctx, plot_name, "{0} : {1}".format(variable, config))

    ResetView()

    image_name = "{0}_{1}.png".format(VIGNETTE, config)
    SetSaveWindowAttributes(save_attributes(ctx, image_name))
    with ctx.phase("render_{0}".format(config)):
        SaveWindow()

    image_path = os.path.join(ctx.output_dir, image_name)
    ctx.image_path(image_name)
    width, height = vc.png_size(image_path)

    DeleteAllPlots()

    # -- metrics -----------------------------------------------------------
    ctx.add_metric("{0}_applied_min".format(config), round(applied_range[0], 6))
    ctx.add_metric("{0}_applied_max".format(config), round(applied_range[1], 6))
    ctx.add_metric("{0}_log_scaling".format(config), int(log_enabled))
    ctx.add_metric("{0}_legend_active".format(config), int(legend.active))
    ctx.add_metric("{0}_color_table".format(config), applied_table)

    # -- assertions --------------------------------------------------------
    ctx.assert_true(
        "{0}: the requested colour table is the one in use".format(config),
        applied_table == table_name,
        "requested '{0}', plot reports '{1}'".format(table_name, applied_table),
    )
    ctx.assert_true(
        "{0}: colour legend is active".format(config),
        bool(legend.active),
        "legend.active={0}".format(legend.active),
    )
    ctx.assert_true(
        "{0}: image written at requested resolution".format(config),
        (width, height) == (ctx.args.image_width, ctx.args.image_height),
        "requested {0}x{1}, got {2}x{3}".format(
            ctx.args.image_width, ctx.args.image_height, width, height
        ),
    )

    if config == "log":
        ctx.assert_true(
            "log: log scaling is actually enabled",
            log_enabled,
            "scaling={0}, expected Log ({1})".format(
                applied_scaling, int(pc_atts.Log)
            ),
        )
        ctx.assert_true(
            "log: range is strictly positive",
            applied_range[0] > 0.0,
            "range=[{0}, {1}] -- a log scale reaching zero is silently "
            "clamped".format(applied_range[0], applied_range[1]),
        )
    elif config == "categorical":
        table = tables[CATEGORICAL_TABLE_NAME]
        ctx.assert_true(
            "categorical: the colour table is discrete",
            bool(table["discrete"]),
            "discreteFlag={0} in {1}".format(table["discrete"], CATEGORICAL_CT),
        )
        ctx.assert_true(
            "categorical: one colour per category",
            len(table["points"]) == CATEGORY_COUNT,
            "expected {0} control point(s), found {1}".format(
                CATEGORY_COUNT, len(table["points"])
            ),
        )
    else:
        ctx.assert_true(
            "{0}: colour table covers a non-degenerate range".format(config),
            applied_range[1] > applied_range[0],
            "range=[{0}, {1}]".format(applied_range[0], applied_range[1]),
        )

    return {
        "configuration": config,
        "variable": variable,
        "color_table": table_name,
        "applied_color_table": applied_table,
        "applied_min": applied_range[0],
        "applied_max": applied_range[1],
        "log_scaling": int(log_enabled),
        "legend_active": int(legend.active),
        "image": image_name,
        "image_width": width,
        "image_height": height,
        "draw_time_s": ctx.timings.get("draw_{0}".format(config), 0.0),
        "render_time_s": ctx.timings.get("render_{0}".format(config), 0.0),
    }


def run(ctx):
    scalar = ctx.args.scalar

    engine_launched = vc.open_visit_engine(ctx, OpenComputeEngine)
    ctx.add_metric("compute_engine_launched", bool(engine_launched))

    dataset = ctx.dataset("varying_first")
    ctx.log("dataset: {0}".format(dataset))

    # -- register the custom colour tables --------------------------------
    tables = {}
    with ctx.phase("register_tables"):
        tables[CUSTOM_TABLE_NAME] = register_color_table(
            ctx, CUSTOM_TABLE_NAME, os.path.join(SCRIPT_DIR, CUSTOM_CT)
        )
        tables[CATEGORICAL_TABLE_NAME] = register_color_table(
            ctx, CATEGORICAL_TABLE_NAME, os.path.join(SCRIPT_DIR, CATEGORICAL_CT)
        )

    # -- open --------------------------------------------------------------
    with ctx.phase("io"):
        if not OpenDatabase(dataset, 0):
            raise vc.VignetteError("OpenDatabase failed for {0}".format(dataset))

    # -- learn the data range ----------------------------------------------
    # A plot has to exist before MinMax can be queried, so this throwaway one
    # is drawn and discarded before the configurations begin.
    AddPlot("Pseudocolor", scalar, 1, 0)
    DrawPlots()
    Query("MinMax", use_actual_data=1)
    minmax = GetQueryOutputValue()
    DeleteAllPlots()

    if isinstance(minmax, (list, tuple)) and len(minmax) >= 2:
        scalar_range = (float(minmax[0]), float(minmax[1]))
    else:
        raise vc.VignetteError(
            "MinMax query on '{0}' returned {1!r}; cannot establish a colour "
            "range.".format(scalar, minmax)
        )

    ctx.log("scalar range: [{0}, {1}]".format(scalar_range[0], scalar_range[1]))
    ctx.add_metric("scalar_min", round(scalar_range[0], 6))
    ctx.add_metric("scalar_max", round(scalar_range[1], 6))

    span = scalar_range[1] - scalar_range[0]
    if span <= 0.0:
        raise vc.VignetteError(
            "Scalar '{0}' has a degenerate range [{1}, {2}]; cannot bin "
            "it.".format(scalar, scalar_range[0], scalar_range[1])
        )

    # -- derive the categorical field --------------------------------------
    # floor() of the normalised scalar gives CATEGORY_COUNT integer bins, and
    # min() clamps the top value into the last bin rather than creating a
    # sixth one with a single member in it.
    expression = "min({0}., floor(({1} - {2}) / {3} * {4}.))".format(
        CATEGORY_COUNT - 1, scalar, scalar_range[0], span, CATEGORY_COUNT
    )
    DefineScalarExpression(CATEGORY_EXPRESSION, expression)
    ctx.log("category expression: {0} = {1}".format(CATEGORY_EXPRESSION, expression))

    selected = CONFIGURATIONS
    if ctx.args.only:
        selected = (ctx.args.only,)

    rows = []
    for config in selected:
        rows.append(
            render_configuration(ctx, config, scalar, scalar_range, tables)
        )

    ctx.write_timing_csv(
        filename="{0}_colormaps.csv".format(VIGNETTE), rows=rows
    )
    ctx.add_metric("configurations_rendered", len(rows))

    CloseDatabase(dataset)


def main():
    args = vc.parse_args(
        VIGNETTE,
        TOOL,
        description="Render one field through four colour table "
        "configurations with formatted colour legends.",
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
