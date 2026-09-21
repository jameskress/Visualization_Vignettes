#
# Visualization Vignettes
#
# ex07_pvScaling -- isosurface extraction with I/O and render time separated
#
# WHAT THIS VIGNETTE DEMONSTRATES
#
#   Running the same isosurface pipeline across a varying number of MPI ranks
#   and recording where the time actually goes. Reading, filtering and
#   rendering are timed as three separate phases, because they scale
#   differently and a single wall-clock number tells you nothing about which
#   one is the bottleneck on your allocation.
#
#   The timings land in a structured CSV next to the rendered images, so a
#   scaling study is an ordinary spreadsheet rather than something you have
#   to reconstruct by scraping logs.
#
# WHAT IT ASSERTS
#
#   Geometry is rank-invariant. The input point and cell counts, the scalar
#   range, the number of cells in the extracted isosurface and its total
#   surface area must be identical whether the pipeline ran on 1 rank or 64.
#   If they are not, the parallel path is producing different science from
#   the serial path -- the failure this vignette exists to catch.
#
#   Contour POINT counts legitimately differ between rank counts, because a
#   point on a partition boundary is duplicated into every piece that touches
#   it. Point count is therefore written to the CSV for information and
#   deliberately left out of the asserted metrics.
#
# DATA
#
#   data/varying_data/varying*.vtk -- a 50^3 rectilinear grid time series
#   carrying the point scalar "temp". Shipped with the repository; needs no
#   preparation step.
#
# RUNNING IT
#
#   Standalone, serial:
#     pvbatch --force-offscreen-rendering ex07_pvScaling.py
#
#   Standalone, 8 ranks:
#     mpirun -np 8 pvbatch --force-offscreen-rendering ex07_pvScaling.py --ranks 8
#
#   Through the harness, at 8 ranks:
#     python3 Testing/test_suite.py ../ --test_type ParaView --ranks 8 \
#         --launcher mpirun --machine_name my-machine
#
#   Building a scaling curve -- run at each rank count and concatenate the
#   per-run CSVs, which all share one header:
#     for n in 1 2 4 8 16; do
#       mpirun -np $n pvbatch --force-offscreen-rendering ex07_pvScaling.py \
#           --ranks $n --output-dir output/np$n
#     done
#
#   pvbatch is not symmetric by default: this script executes on rank 0 only,
#   while the remaining ranks act as data and render servers. That is what
#   makes it safe to write files and to Fetch results from inside the script.
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
    except NameError:  # pragma: no cover - interpreter without __file__
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


VIGNETTE = "ex07_pvScaling"
TOOL = "ParaView"


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
        help="Point scalar to contour.",
    )


def available_point_arrays(source):
    """Names of the point arrays a source exposes, for error messages."""
    point_data = source.PointData
    return [point_data.GetArray(i).GetName() for i in range(len(point_data))]


def fetch_integrated_value(proxy, array_name, association="CELLS"):
    """Fetch one integrated quantity from an IntegrateVariables output.

    Returns None when the array is absent, which is what happens for an empty
    contour. The caller decides whether that is a failure.
    """
    data = sm.Fetch(proxy)
    if data is None:
        return None

    attributes = data.GetCellData() if association == "CELLS" else data.GetPointData()
    array = attributes.GetArray(array_name)
    if array is None or array.GetNumberOfTuples() < 1:
        return None
    return float(array.GetValue(0))


def run(ctx):
    scalar = ctx.args.scalar
    series = ctx.timestep_files()
    ctx.log("time series: {0} file(s)".format(len(series)))
    ctx.log("contouring '{0}' at {1}".format(scalar, ctx.args.isovalue))

    paraview.simple._DisableFirstRenderCameraReset()

    # -- Reader ----------------------------------------------------------
    reader = LegacyVTKReader(registrationName="ex07_series", FileNames=series)
    UpdatePipeline(proxy=reader)

    if reader.PointData.GetArray(scalar) is None:
        raise vc.VignetteError(
            "Scalar '{0}' not found. Available point arrays: {1}".format(
                scalar, available_point_arrays(reader)
            )
        )

    timestep_values = list(reader.TimestepValues) or [0.0]
    ctx.log("timesteps reported by the reader: {0}".format(len(timestep_values)))

    # -- Contour ---------------------------------------------------------
    contour = Contour(Input=reader, registrationName="ex07_contour")
    contour.ContourBy = ["POINTS", scalar]
    contour.Isosurfaces = [ctx.args.isovalue]
    contour.PointMergeMethod = "Uniform Binning"

    integrate = IntegrateVariables(Input=contour, registrationName="ex07_integrate")

    # -- Timed sweep over the series -------------------------------------
    # Both phases accumulate so the reported totals cover the whole sweep,
    # which gives a far more stable scaling measurement than a single step.
    # Metrics are taken from the LAST timestep so they stay deterministic.
    input_points = input_cells = 0
    contour_points = contour_cells = 0
    scalar_range = (0.0, 0.0)

    for step_time in timestep_values:
        with ctx.phase("io", accumulate=True):
            UpdatePipeline(time=step_time, proxy=reader)

        with ctx.phase("filter", accumulate=True):
            UpdatePipeline(time=step_time, proxy=contour)

        reader_info = reader.GetDataInformation()
        input_points = int(reader_info.GetNumberOfPoints())
        input_cells = int(reader_info.GetNumberOfCells())
        scalar_range = reader.PointData.GetArray(scalar).GetRange(0)

        contour_info = contour.GetDataInformation()
        contour_points = int(contour_info.GetNumberOfPoints())
        contour_cells = int(contour_info.GetNumberOfCells())

        ctx.debug(
            "t={0}: input {1} pts / {2} cells, contour {3} pts / {4} cells".format(
                step_time, input_points, input_cells, contour_points, contour_cells
            )
        )

    ctx.add_metric("timesteps_processed", len(timestep_values))
    ctx.add_metric("input_points", input_points)
    ctx.add_metric("input_cells", input_cells)
    ctx.add_metric("scalar_min", round(float(scalar_range[0]), 6))
    ctx.add_metric("scalar_max", round(float(scalar_range[1]), 6))
    ctx.add_metric("contour_cells", contour_cells)

    with ctx.phase("integrate"):
        UpdatePipeline(time=timestep_values[-1], proxy=integrate)
        surface_area = fetch_integrated_value(integrate, "Area", "CELLS")

    if surface_area is not None:
        ctx.add_metric("contour_area", round(surface_area, 4))

    # -- Render ----------------------------------------------------------
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
    lut.RescaleTransferFunction(float(scalar_range[0]), float(scalar_range[1]))
    display.SetScalarBarVisibility(view, False)

    ResetCamera(view)

    image_name = "{0}_isosurface.png".format(VIGNETTE)
    with ctx.phase("render"):
        Render(view)
        SaveScreenshot(
            ctx.image_path(image_name),
            view,
            ImageResolution=[ctx.args.image_width, ctx.args.image_height],
        )

    # -- Scaling CSV -----------------------------------------------------
    row = {
        "vignette": VIGNETTE,
        "tool": TOOL,
        "machine": ctx.args.machine,
        "nodes": ctx.args.nodes,
        "ranks": ctx.args.ranks,
        "timesteps": len(timestep_values),
        "input_points": input_points,
        "input_cells": input_cells,
        "contour_points": contour_points,
        "contour_cells": contour_cells,
        "contour_area": surface_area if surface_area is not None else "",
        "io_time_s": ctx.timings.get("io", 0.0),
        "filter_time_s": ctx.timings.get("filter", 0.0),
        "integrate_time_s": ctx.timings.get("integrate", 0.0),
        "render_time_s": ctx.timings.get("render", 0.0),
        "image_width": ctx.args.image_width,
        "image_height": ctx.args.image_height,
    }
    ctx.write_timing_csv(rows=[row])

    ctx.log(
        "io={0:.4f}s  filter={1:.4f}s  render={2:.4f}s".format(
            ctx.timings.get("io", 0.0),
            ctx.timings.get("filter", 0.0),
            ctx.timings.get("render", 0.0),
        )
    )

    # -- Assertions ------------------------------------------------------
    ctx.assert_true(
        "time series was read",
        input_points > 0 and input_cells > 0,
        "points={0} cells={1}".format(input_points, input_cells),
    )
    ctx.assert_true(
        "isosurface is non-empty",
        contour_cells > 0,
        "contour_cells={0}".format(contour_cells),
    )
    ctx.assert_true(
        "isosurface has finite area",
        surface_area is not None and surface_area > 0.0,
        "area={0}".format(surface_area),
    )
    ctx.assert_true(
        "image was written",
        os.path.exists(os.path.join(ctx.output_dir, image_name)),
        image_name,
    )
    ctx.assert_true(
        "io and render phases were both timed",
        ctx.timings.get("io", 0.0) > 0.0 and ctx.timings.get("render", 0.0) > 0.0,
        "io={0:.6f}s render={1:.6f}s".format(
            ctx.timings.get("io", 0.0), ctx.timings.get("render", 0.0)
        ),
    )


def main():
    args = vc.parse_args(
        VIGNETTE,
        TOOL,
        description="Isosurface scaling study with I/O and render time "
        "measured separately.",
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
