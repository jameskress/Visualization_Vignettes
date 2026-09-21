#
# Visualization Vignettes
#
# ex10_pvColormapFidelity -- four transfer function configurations, one field
#
# WHY THIS VIGNETTE EXISTS
#
#   Colour mapping is the most version-fragile part of a ParaView script and
#   the single most common source of "the picture changed after the upgrade".
#   Preset names get renamed, default opacity handling shifts, scalar bar
#   layout properties move, and log scaling silently clamps a range that
#   crosses zero. None of that is covered anywhere else in this repository.
#
# THE FOUR CONFIGURATIONS
#
#   preset       a built-in preset applied by name, rescaled to the data
#   custom       a colour map loaded from ex10_custom_colormap.xml through
#                ImportPresets() and applied by name
#   log          the same custom map with UseLogScale enabled, over a range
#                forced strictly positive first -- a log scale across zero is
#                undefined and ParaView's silent clamp is itself a regression
#                worth pinning down
#   categorical  an indexed map over a derived integer field, with per-value
#                annotations, using InterpretValuesAsCategories
#
#   Every configuration renders with its colour legend visible and explicitly
#   formatted, because the legend is where preset and label-format drift
#   shows up first.
#
# WHAT IT ASSERTS
#
#   Per configuration: the lookup table reports the range that was set, the
#   scalar bar is visible, and an image was written at the requested
#   resolution. Plus the two structural properties that silently break across
#   versions -- log scaling actually enabled with a strictly positive range,
#   and the categorical map actually interpreting values as categories with
#   the expected number of annotations.
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
#   pvbatch --force-offscreen-rendering ex10_pvColormapFidelity.py
#   pvbatch --force-offscreen-rendering ex10_pvColormapFidelity.py --only log
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


VIGNETTE = "ex10_pvColormapFidelity"
TOOL = "ParaView"

CUSTOM_PRESET_NAME = "VV Ember"
CATEGORICAL_PRESET_NAME = "VV Categorical"
CUSTOM_XML = "ex10_custom_colormap.xml"

CONFIGURATIONS = ("preset", "custom", "log", "categorical")

# Number of bins the categorical field is quantised into. Matches the count
# of IndexedColor entries in ex10_custom_colormap.xml.
CATEGORY_COUNT = 5

CATEGORY_LABELS = ("coolest", "cool", "middle", "warm", "warmest")


def add_arguments(parser):
    parser.add_argument(
        "--only",
        choices=CONFIGURATIONS,
        default=None,
        help="Render a single configuration instead of all four.",
    )
    parser.add_argument(
        "--preset",
        default="Cool to Warm (Extended)",
        help="Built-in preset name used by the 'preset' configuration.",
    )
    parser.add_argument(
        "--scalar",
        default=vc.SHARED_SCALAR,
        help="Point scalar to colour by.",
    )


def format_scalar_bar(view, lut, title, component_title=""):
    """Make the colour legend legible and, more importantly, deterministic.

    Every property here is set explicitly. Leaving them at their defaults
    means the legend silently restyles itself between ParaView releases and
    every baseline image in this vignette fails for a reason that has nothing
    to do with the colour map.
    """
    bar = GetScalarBar(lut, view)
    bar.Title = title
    bar.ComponentTitle = component_title

    bar.TitleFontFamily = "Arial"
    bar.TitleFontSize = 18
    bar.TitleBold = 1
    bar.TitleColor = [0.94, 0.95, 0.97]

    bar.LabelFontFamily = "Arial"
    bar.LabelFontSize = 14
    bar.LabelBold = 0
    bar.LabelColor = [0.86, 0.88, 0.92]

    bar.Orientation = "Vertical"
    bar.WindowLocation = "Any Location"
    bar.Position = [0.86, 0.16]
    bar.ScalarBarLength = 0.68
    bar.ScalarBarThickness = 18

    bar.AutomaticLabelFormat = 0
    # ParaView 6 formats these with std::format specs, not printf ones, and
    # prints an unrecognised spec verbatim -- so a hard-coded "%-#6.3g" makes
    # every tick label on the legend read "%-#6.3g". vc.number_format reads
    # the build's own default to decide which dialect to emit, which keeps
    # one script correct on 6.1 here and on 5.13.1 from the cluster modules.
    bar.LabelFormat = vc.number_format(bar, "%-#6.3g", "LabelFormat")
    bar.RangeLabelFormat = vc.number_format(bar, "%-#6.3g", "RangeLabelFormat")
    bar.AddRangeLabels = 1
    bar.DrawTickMarks = 1
    bar.DrawTickLabels = 1
    return bar


def build_view(ctx):
    view = GetActiveViewOrCreate("RenderView")
    view.ViewSize = [ctx.args.image_width, ctx.args.image_height]
    view.ShowAnnotation = False
    view.OrientationAxesVisibility = 0
    view.UseColorPaletteForBackground = 0
    view.BackgroundColorMode = "Single Color"
    view.Background = [0.09, 0.10, 0.12]
    return view


def positive_log_range(scalar_range):
    """A strictly positive range suitable for log scaling.

    ParaView clamps a log range that reaches zero or below, and does it
    quietly. Deriving an explicitly positive range here means the vignette
    controls what is being tested instead of testing the clamp.
    """
    low, high = float(scalar_range[0]), float(scalar_range[1])
    if low > 0.0:
        return low, high
    # One part in a thousand of the span, floored well above zero.
    span = high - low
    safe_low = max(span * 1e-3, 1e-6)
    return safe_low, max(high, safe_low * 10.0)


def render_configuration(ctx, view, source, scalar, config, scalar_range):
    """Apply one transfer-function configuration and render it."""
    ctx.log("-" * 60)
    ctx.log("configuration: {0}".format(config))

    display = Show(source, view)
    display.Representation = "Surface"
    ColorBy(display, ("POINTS", scalar))

    lut = GetColorTransferFunction(scalar)
    pwf = GetOpacityTransferFunction(scalar)

    # Reset the properties the previous configuration may have changed, so
    # each configuration starts from the same place regardless of order.
    lut.InterpretValuesAsCategories = 0
    lut.UseLogScale = 0
    lut.AnnotationsInitialized = 0
    lut.Annotations = []

    report = {"configuration": config}

    if config == "preset":
        vc.apply_color_preset(lut, (ctx.args.preset,), ctx)
        lut.RescaleTransferFunction(scalar_range[0], scalar_range[1])
        pwf.RescaleTransferFunction(scalar_range[0], scalar_range[1])
        title = "{0} -- preset".format(scalar)
        applied_range = tuple(scalar_range)
        report["preset"] = ctx.args.preset

    elif config == "custom":
        vc.apply_color_preset(lut, (CUSTOM_PRESET_NAME,), ctx)
        lut.RescaleTransferFunction(scalar_range[0], scalar_range[1])
        pwf.RescaleTransferFunction(scalar_range[0], scalar_range[1])
        title = "{0} -- custom XML".format(scalar)
        applied_range = tuple(scalar_range)
        report["preset"] = CUSTOM_PRESET_NAME

    elif config == "log":
        low, high = positive_log_range(scalar_range)
        vc.apply_color_preset(lut, (CUSTOM_PRESET_NAME,), ctx)
        # Rescale BEFORE enabling log scaling: enabling it against a range
        # that still reaches zero is what triggers the silent clamp.
        lut.RescaleTransferFunction(low, high)
        pwf.RescaleTransferFunction(low, high)
        lut.UseLogScale = 1
        title = "{0} -- log scale".format(scalar)
        applied_range = (low, high)
        report["preset"] = CUSTOM_PRESET_NAME

    else:  # categorical
        lut = GetColorTransferFunction("category")
        ColorBy(display, ("POINTS", "category"))
        vc.apply_color_preset(lut, (CATEGORICAL_PRESET_NAME,), ctx)
        lut.InterpretValuesAsCategories = 1
        lut.AnnotationsInitialized = 1

        annotations = []
        for index in range(CATEGORY_COUNT):
            annotations.extend([str(index), CATEGORY_LABELS[index]])
        lut.Annotations = annotations

        title = "category -- indexed"
        applied_range = (0.0, float(CATEGORY_COUNT - 1))
        report["preset"] = CATEGORICAL_PRESET_NAME

    display.SetScalarBarVisibility(view, True)
    bar = format_scalar_bar(view, lut, title)

    ResetCamera(view)

    image_name = "{0}_{1}.png".format(VIGNETTE, config)
    image_path = ctx.image_path(image_name)
    with ctx.phase("render_{0}".format(config)):
        Render(view)
        SaveScreenshot(
            image_path,
            view,
            ImageResolution=[ctx.args.image_width, ctx.args.image_height],
        )

    width, height = vc.png_size(image_path)

    # -- metrics ----------------------------------------------------------
    reported_range = list(lut.RGBPoints[0::4]) if lut.RGBPoints else []
    lut_min = min(reported_range) if reported_range else 0.0
    lut_max = max(reported_range) if reported_range else 0.0

    ctx.add_metric("{0}_lut_min".format(config), round(float(lut_min), 6))
    ctx.add_metric("{0}_lut_max".format(config), round(float(lut_max), 6))
    ctx.add_metric("{0}_use_log_scale".format(config), int(lut.UseLogScale))
    ctx.add_metric(
        "{0}_categorical".format(config), int(lut.InterpretValuesAsCategories)
    )
    ctx.add_metric("{0}_scalar_bar_visible".format(config), int(bar.Visibility))

    report.update(
        {
            "title": title,
            "applied_min": applied_range[0],
            "applied_max": applied_range[1],
            "lut_min": float(lut_min),
            "lut_max": float(lut_max),
            "use_log_scale": int(lut.UseLogScale),
            "categorical": int(lut.InterpretValuesAsCategories),
            "image": image_name,
            "image_width": width,
            "image_height": height,
            "render_time_s": ctx.timings.get("render_{0}".format(config), 0.0),
        }
    )

    # -- assertions --------------------------------------------------------
    ctx.assert_true(
        "{0}: colour legend is visible".format(config),
        bool(bar.Visibility),
        "scalar bar visibility={0}".format(bar.Visibility),
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
            int(lut.UseLogScale) == 1,
            "UseLogScale={0}".format(lut.UseLogScale),
        )
        ctx.assert_true(
            "log: range is strictly positive",
            applied_range[0] > 0.0,
            "range=[{0}, {1}] -- a log scale reaching zero is silently "
            "clamped by ParaView".format(applied_range[0], applied_range[1]),
        )
    elif config == "categorical":
        ctx.assert_true(
            "categorical: values are interpreted as categories",
            int(lut.InterpretValuesAsCategories) == 1,
            "InterpretValuesAsCategories={0}".format(lut.InterpretValuesAsCategories),
        )
        ctx.assert_true(
            "categorical: every category is annotated",
            len(lut.Annotations) == CATEGORY_COUNT * 2,
            "expected {0} annotation entries, got {1}".format(
                CATEGORY_COUNT * 2, len(lut.Annotations)
            ),
        )
    else:
        ctx.assert_true(
            "{0}: lookup table covers the data range".format(config),
            lut_max > lut_min,
            "lut range=[{0}, {1}]".format(lut_min, lut_max),
        )

    Hide(source, view)
    return report


def run(ctx):
    paraview.simple._DisableFirstRenderCameraReset()

    scalar = ctx.args.scalar
    dataset = ctx.dataset("varying_first")
    ctx.log("dataset: {0}".format(dataset))

    # -- load the custom colour maps --------------------------------------
    preset_xml = os.path.join(SCRIPT_DIR, CUSTOM_XML)
    if not os.path.exists(preset_xml):
        raise vc.VignetteError("Custom colour map not found: {0}".format(preset_xml))

    with ctx.phase("import_presets"):
        if not ImportPresets(filename=preset_xml):
            raise vc.VignetteError("ImportPresets() rejected {0}".format(preset_xml))
    ctx.log("imported custom presets from {0}".format(CUSTOM_XML))

    # -- read ---------------------------------------------------------------
    with ctx.phase("io"):
        reader = LegacyVTKReader(registrationName="ex10_reader", FileNames=[dataset])
        UpdatePipeline(proxy=reader)

    array_info = reader.PointData.GetArray(scalar)
    if array_info is None:
        available = [
            reader.PointData.GetArray(i).GetName() for i in range(len(reader.PointData))
        ]
        raise vc.VignetteError(
            "Scalar '{0}' not found. Available point arrays: {1}".format(
                scalar, available
            )
        )
    scalar_range = array_info.GetRange(0)
    ctx.log("scalar range: [{0}, {1}]".format(scalar_range[0], scalar_range[1]))

    ctx.add_metric("scalar_min", round(float(scalar_range[0]), 6))
    ctx.add_metric("scalar_max", round(float(scalar_range[1]), 6))

    # -- derive the categorical field ---------------------------------------
    # floor() of the normalised scalar gives CATEGORY_COUNT integer bins, and
    # the max is clamped so the top value lands in the last bin rather than
    # creating a sixth one with a single member.
    span = float(scalar_range[1]) - float(scalar_range[0])
    if span <= 0.0:
        raise vc.VignetteError(
            "Scalar '{0}' has a degenerate range [{1}, {2}]; cannot bin "
            "it".format(scalar, scalar_range[0], scalar_range[1])
        )

    binner = Calculator(Input=reader, registrationName="ex10_categories")
    binner.AttributeType = "Point Data"
    binner.ResultArrayName = "category"
    # Scale by CATEGORY_COUNT, clamp at CATEGORY_COUNT - 1. The scale factor
    # was CATEGORY_COUNT - 1, which is what the comment above says it is
    # avoiding: it gives four equal-width bins plus a fifth holding only the
    # exact maximum, so the five-colour indexed map this vignette exists to
    # verify was only ever asked to show four of its colours -- and the fifth
    # only if a single point happened to sit on the maximum.
    binner.Function = "min({0}, floor(({1} - {2}) / {3} * {4}))".format(
        CATEGORY_COUNT - 1, scalar, float(scalar_range[0]), span, CATEGORY_COUNT
    )
    UpdatePipeline(proxy=binner)
    ctx.debug("category function: {0}".format(binner.Function))

    view = build_view(ctx)

    selected = CONFIGURATIONS
    if ctx.args.only:
        selected = (ctx.args.only,)

    rows = []
    for config in selected:
        source = binner if config == "categorical" else reader
        rows.append(
            render_configuration(ctx, view, source, scalar, config, scalar_range)
        )

    ctx.write_timing_csv(filename="{0}_colormaps.csv".format(VIGNETTE), rows=rows)
    ctx.add_metric("configurations_rendered", len(rows))


def main():
    args = vc.parse_args(
        VIGNETTE,
        TOOL,
        description="Render one field through four transfer function "
        "configurations with formatted colour legends.",
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
