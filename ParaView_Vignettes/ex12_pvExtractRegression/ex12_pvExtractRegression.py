#
# Visualization Vignettes
#
# ex12_pvExtractRegression -- extractors, and a regression test that survives
#                             a ParaView upgrade
#
# WHY THIS VIGNETTE EXISTS
#
#   Every other vignette in this suite ultimately asserts on pixels. Pixel
#   comparison is fragile in a way that has nothing to do with correctness: a
#   driver update, a font change, a new default in the shader, and the diff
#   goes red while the science is untouched. Meanwhile a genuine numerical
#   regression that happens not to move many pixels slips through.
#
#   This vignette inverts that. It uses ParaView's extractor mechanism --
#   CreateExtractor plus SaveExtracts -- to emit three kinds of artifact side
#   by side:
#
#     data extracts   .vtp geometry of the contour, written by a VTK extractor
#     numerical CSV   integrated quantities and point/cell queries, which are
#                     compared numerically with a tolerance
#     image extracts  rendered frames, kept for eyeballing and for the
#                     existing image-comparison path
#
#   The CSV is the assertion. It is version-agnostic in a way an image never
#   is: a contour's cell count and surface area are properties of the data
#   and the algorithm, not of the renderer.
#
# WHAT IT ASSERTS
#
#   Every configured extractor actually wrote its file; the numeric CSV
#   contains the expected columns and rows; and the integrated quantities are
#   finite and non-zero. The values themselves are recorded as metrics, so
#   the harness compares them against the blessed baseline with a tolerance
#   rather than requiring bit-identical floats.
#
# DATA
#
#   data/varying_data/varying*.vtk, point scalar "temp". Shipped with the
#   repository.
#
# RUNNING IT
#
#   pvbatch --force-offscreen-rendering ex12_pvExtractRegression.py
#   pvbatch --force-offscreen-rendering ex12_pvExtractRegression.py --steps 5
#
# Author: James Kress, <james@jameskress.com>
#
import csv
import math
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
import paraview.servermanager as sm  # noqa: E402
from paraview.simple import *  # noqa: E402,F401,F403


VIGNETTE = "ex12_pvExtractRegression"
TOOL = "ParaView"

NUMERIC_CSV = "{0}_measurements.csv".format(VIGNETTE)

# Columns the numeric CSV must always carry. Checked explicitly so that a
# silently dropped column is a failure rather than a quietly shorter file.
REQUIRED_COLUMNS = (
    "timestep",
    "cycle",
    "time",
    "input_points",
    "input_cells",
    "contour_points",
    "contour_cells",
    "contour_area",
    "scalar_min",
    "scalar_max",
    "scalar_mean",
)

# Columns whose values are identities rather than measurements. Matched on,
# not compared. See ctx.add_numeric_extract() below.
CSV_KEY_COLUMNS = ("timestep",)

# Tolerances for the CSV comparison. Looser than the results-JSON defaults on
# purpose: these are integrals over a mesh, and their last couple of digits
# legitimately move with rank count, with the order cells are summed in, and
# with the compiler's floating-point contraction. A tolerance that fails on
# that is a tolerance people learn to ignore.
CSV_RTOL = 1e-6
CSV_ATOL = 1e-9


def add_arguments(parser):
    parser.add_argument(
        "--isovalue",
        type=float,
        default=3.0,
        help="Contour value on the scalar being extracted.",
    )
    parser.add_argument(
        "--scalar",
        default=vc.SHARED_SCALAR,
        help="Point scalar to contour and measure.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=3,
        help="How many timesteps to extract and measure.",
    )


def fetch_array_value(proxy, array_name, association="CELLS", index=0):
    """Fetch one value from an IntegrateVariables output, or None."""
    data = sm.Fetch(proxy)
    if data is None:
        return None

    attributes = data.GetCellData() if association == "CELLS" else data.GetPointData()
    array = attributes.GetArray(array_name)
    if array is None or array.GetNumberOfTuples() <= index:
        return None
    return float(array.GetValue(index))


def configure_data_extractor(ctx, source):
    """A VTP extractor over the contour geometry.

    CreateExtractor's generator names differ between ParaView releases, so
    the candidates are tried in turn and the first that constructs is used.
    Failing to find any is reported rather than swallowed.
    """
    for generator in ("VTP", "VTPD"):
        try:
            extractor = CreateExtractor(generator, source, registrationName="ex12_data")
        except Exception as exc:  # noqa: BLE001 - try the next generator
            ctx.debug("CreateExtractor('{0}') failed: {1}".format(generator, exc))
            continue

        extractor.Trigger = "TimeStep"
        writer = extractor.Writer
        writer.FileName = "{0}_contour_{{timestep:06d}}.vtp".format(VIGNETTE)
        ctx.log("data extractor: {0} -> {1}".format(generator, writer.FileName))
        return extractor, generator

    raise vc.VignetteError(
        "No VTP extractor generator available in this ParaView build. "
        "Tried: VTP, VTPD."
    )


def configure_image_extractor(ctx, view):
    """A PNG extractor over the render view."""
    extractor = CreateExtractor("PNG", view, registrationName="ex12_image")
    extractor.Trigger = "TimeStep"
    writer = extractor.Writer
    writer.FileName = "{0}_frame_{{timestep:06d}}.png".format(VIGNETTE)
    writer.ImageResolution = [ctx.args.image_width, ctx.args.image_height]
    ctx.log("image extractor: PNG -> {0}".format(writer.FileName))
    return extractor


def reader_cycle(reader):
    """The simulation cycle this timestep says it is, or None.

    It lives in the dataset's field data as CYCLE, written there by
    data/make_time_series.py. ParaView takes its TIME from the .pvd instead
    (its readers ignore a field-data time), so this is the one number that
    comes out of the file itself on the ParaView side -- and it agrees with
    what VisIt reads, which is the check worth having.
    """
    try:
        field_data = reader.FieldData
        array = field_data.GetArray("CYCLE")
        if array is None:
            return None
        return int(round(array.GetRange(0)[0]))
    except Exception:  # noqa: BLE001 - an absent cycle is not a failure
        return None


def measure(ctx, reader, contour, integrate_contour, integrate_input, scalar, step, time_value):
    """Collect the numerical measurements for one timestep."""
    reader_info = reader.GetDataInformation()
    contour_info = contour.GetDataInformation()

    array_info = reader.PointData.GetArray(scalar)
    scalar_range = array_info.GetRange(0) if array_info else (0.0, 0.0)

    contour_area = fetch_array_value(integrate_contour, "Area", "CELLS")

    # IntegrateVariables divided by the integrated volume gives the
    # volume-weighted mean, which is a far more sensitive regression signal
    # than min/max: it moves when any cell changes, not just the extremes.
    integrated_scalar = fetch_array_value(integrate_input, scalar, "POINTS")
    integrated_volume = fetch_array_value(integrate_input, "Volume", "CELLS")
    if integrated_scalar is not None and integrated_volume:
        scalar_mean = integrated_scalar / integrated_volume
    else:
        scalar_mean = float("nan")

    return {
        "timestep": step,
        "cycle": reader_cycle(reader),
        "time": float(time_value),
        "input_points": int(reader_info.GetNumberOfPoints()),
        "input_cells": int(reader_info.GetNumberOfCells()),
        "contour_points": int(contour_info.GetNumberOfPoints()),
        "contour_cells": int(contour_info.GetNumberOfCells()),
        "contour_area": contour_area if contour_area is not None else float("nan"),
        "scalar_min": float(scalar_range[0]),
        "scalar_max": float(scalar_range[1]),
        "scalar_mean": scalar_mean,
    }


def write_numeric_csv(ctx, rows):
    """Write the version-agnostic numerical record and declare it."""
    path = os.path.join(ctx.output_dir, NUMERIC_CSV)
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in REQUIRED_COLUMNS})
    ctx.log("wrote numeric extract: {0}".format(path))

    # This is the line that routes the file into verify.compare_csv instead
    # of leaving it as an unchecked artifact beside the images.
    ctx.add_numeric_extract(
        NUMERIC_CSV,
        key_columns=CSV_KEY_COLUMNS,
        rtol=CSV_RTOL,
        atol=CSV_ATOL,
    )
    return path


def run(ctx):
    paraview.simple._DisableFirstRenderCameraReset()

    scalar = ctx.args.scalar
    # The XML series. The legacy varying*.vtk files carry no time, so
    # reader.TimestepValues below would be the file index dressed up as a
    # simulation time -- and the CSV's "time" column would be a copy of its
    # "timestep" column. See vc.time_series_index().
    index_path = ctx.time_series_index()
    series = ctx.timestep_files()
    ctx.log("time series index: {0}".format(os.path.basename(index_path)))
    ctx.log("time series: {0} file(s)".format(len(series)))

    # -- pipeline ----------------------------------------------------------
    with ctx.phase("io"):
        reader = PVDReader(registrationName="ex12_series", FileName=index_path)
        UpdatePipeline(proxy=reader)

    if reader.PointData.GetArray(scalar) is None:
        available = [
            reader.PointData.GetArray(i).GetName()
            for i in range(len(reader.PointData))
        ]
        raise vc.VignetteError(
            "Scalar '{0}' not found. Available point arrays: {1}".format(
                scalar, available
            )
        )

    contour = Contour(Input=reader, registrationName="ex12_contour")
    contour.ContourBy = ["POINTS", scalar]
    contour.Isosurfaces = [ctx.args.isovalue]
    contour.PointMergeMethod = "Uniform Binning"

    integrate_contour = IntegrateVariables(
        Input=contour, registrationName="ex12_integrate_contour"
    )
    integrate_input = IntegrateVariables(
        Input=reader, registrationName="ex12_integrate_input"
    )

    # -- view --------------------------------------------------------------
    view = GetActiveViewOrCreate("RenderView")
    view.ViewSize = [ctx.args.image_width, ctx.args.image_height]
    view.ShowAnnotation = False
    view.OrientationAxesVisibility = 0
    view.UseColorPaletteForBackground = 0
    view.BackgroundColorMode = "Single Color"
    view.Background = [0.09, 0.10, 0.12]

    display = Show(contour, view)
    display.Representation = "Surface"
    ColorBy(display, ("POINTS", scalar))
    lut = GetColorTransferFunction(scalar)
    vc.apply_color_preset(lut, ("Cool to Warm",), ctx)
    display.SetScalarBarVisibility(view, False)

    UpdatePipeline(proxy=contour)
    ResetCamera(view)
    Render(view)

    # -- extractors --------------------------------------------------------
    # Everything already in output/ before this run starts. The file counts
    # below are the metrics that gate this vignette, and counting the whole
    # directory made them a function of run history rather than of this run:
    # a second invocation, or one with a different --steps, saw the previous
    # run's .vtp and .png files and reported a larger number than it wrote.
    # Nothing clears output/ between runs -- the harness only cleans
    # Testing/ -- so the baseline was reproducible exactly once, on a clean
    # checkout, and never again.
    try:
        pre_existing = set(os.listdir(ctx.output_dir))
    except OSError:
        pre_existing = set()
    if pre_existing:
        ctx.log(
            "{0} file(s) already in output/; they are excluded from the "
            "extract counts".format(len(pre_existing))
        )

    data_extractor, data_generator = configure_data_extractor(ctx, contour)
    image_extractor = configure_image_extractor(ctx, view)

    ctx.add_metric("data_extractor_generator", data_generator)

    timestep_values = list(reader.TimestepValues) or [0.0]
    step_count = max(1, min(ctx.args.steps, len(timestep_values)))
    ctx.log("extracting {0} of {1} timestep(s)".format(step_count, len(timestep_values)))

    scene = GetAnimationScene()
    scene.UpdateAnimationUsingDataTimeSteps()

    rows = []
    for index in range(step_count):
        time_value = timestep_values[index]
        scene.AnimationTime = time_value
        UpdatePipeline(time=time_value, proxy=integrate_contour)
        UpdatePipeline(time=time_value, proxy=integrate_input)

        with ctx.phase("extract", accumulate=True):
            # FrameWindow pins this call to the one timestep the loop is on.
            # Without it SaveExtracts runs the WHOLE animation every call, so
            # a --steps 3 run wrote all 20 timesteps, three times over: the
            # extract timing measured 20 frames rather than one, the work was
            # done 3x, and data_extract_files reported 20 against
            # steps_extracted of 3 -- a count that would not have moved had
            # the per-step extraction stopped working altogether.
            SaveExtracts(
                ExtractsOutputDirectory=ctx.output_dir,
                FrameWindow=[index, index],
            )

        row = measure(
            ctx,
            reader,
            contour,
            integrate_contour,
            integrate_input,
            scalar,
            index,
            time_value,
        )
        rows.append(row)
        ctx.log(
            "  step {0}: t={1} contour {2} cells, area={3:.4f}, mean={4:.6f}".format(
                index,
                time_value,
                row["contour_cells"],
                row["contour_area"],
                row["scalar_mean"],
            )
        )

    csv_path = write_numeric_csv(ctx, rows)

    # -- record what landed on disk ---------------------------------------
    # Only files this run created, so the counts describe the run and not the
    # directory. A file the extractor overwrote in place keeps its old name
    # and is excluded, which is correct: the assertion below is about the
    # extractor producing one frame per step, and an overwritten frame means
    # the {timestep} substitution stopped advancing -- a failure worth
    # reporting, not a count to inflate past it.
    produced = sorted(set(os.listdir(ctx.output_dir)) - pre_existing)
    vtp_files = [name for name in produced if name.lower().endswith(".vtp")]
    png_files = [
        name
        for name in produced
        if name.lower().endswith(".png") and name.startswith(VIGNETTE)
    ]
    for name in png_files:
        ctx.image_path(name)
    for name in vtp_files:
        ctx.extract_path(name)

    ctx.log("data extracts : {0}".format(len(vtp_files)))
    ctx.log("image extracts: {0}".format(len(png_files)))

    # -- metrics ------------------------------------------------------------
    last = rows[-1]
    ctx.add_metric("steps_extracted", len(rows))
    ctx.add_metric("data_extract_files", len(vtp_files))
    ctx.add_metric("image_extract_files", len(png_files))
    ctx.add_metric("input_points", last["input_points"])
    ctx.add_metric("input_cells", last["input_cells"])
    ctx.add_metric("contour_cells", last["contour_cells"])
    ctx.add_metric("contour_area", round(last["contour_area"], 4))
    ctx.add_metric("scalar_min", round(last["scalar_min"], 6))
    ctx.add_metric("scalar_max", round(last["scalar_max"], 6))
    ctx.add_metric("scalar_mean", round(last["scalar_mean"], 6))

    # -- assertions ---------------------------------------------------------
    ctx.assert_true(
        "data extractor wrote at least one file",
        len(vtp_files) > 0,
        "found {0} .vtp file(s) in {1}".format(len(vtp_files), ctx.output_dir),
    )
    ctx.assert_true(
        "image extractor wrote one frame per step",
        len(png_files) >= step_count,
        "expected at least {0}, found {1}".format(step_count, len(png_files)),
    )
    ctx.assert_true(
        "numeric CSV was written",
        os.path.exists(csv_path),
        NUMERIC_CSV,
    )

    with open(csv_path, "r") as handle:
        reader_csv = csv.DictReader(handle)
        header = reader_csv.fieldnames or []
        csv_rows = list(reader_csv)

    ctx.assert_true(
        "numeric CSV carries every required column",
        all(column in header for column in REQUIRED_COLUMNS),
        "missing: {0}".format(
            [column for column in REQUIRED_COLUMNS if column not in header]
        ),
    )
    ctx.assert_true(
        "numeric CSV has one row per extracted step",
        len(csv_rows) == step_count,
        "expected {0} row(s), found {1}".format(step_count, len(csv_rows)),
    )
    ctx.assert_true(
        "every contour is non-empty",
        all(row["contour_cells"] > 0 for row in rows),
        "cell counts: {0}".format([row["contour_cells"] for row in rows]),
    )
    ctx.assert_true(
        "every integrated area is finite and positive",
        all(
            not math.isnan(row["contour_area"]) and row["contour_area"] > 0.0
            for row in rows
        ),
        "areas: {0}".format([row["contour_area"] for row in rows]),
    )
    ctx.assert_true(
        "volume-weighted mean is finite",
        not math.isnan(last["scalar_mean"]),
        "mean={0}".format(last["scalar_mean"]),
    )

    Delete(image_extractor)
    Delete(data_extractor)


def main():
    args = vc.parse_args(
        VIGNETTE,
        TOOL,
        description="Emit data, numeric and image extracts, and regression "
        "test the numbers rather than the pixels.",
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
