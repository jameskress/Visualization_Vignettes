#
# Visualization Vignettes
#
# ex07_visitScaling -- isosurface extraction with database, pipeline and
#                      render time separated
#
# WHAT THIS VIGNETTE DEMONSTRATES
#
#   The same isosurface study as ex07_pvScaling, driven through VisIt's
#   compute engine so the two tools can be compared on identical data at
#   identical rank counts.
#
#   Parallelism in VisIt is the compute engine's job, not the client's. This
#   script is never launched under mpirun; it asks OpenComputeEngine for the
#   node and rank count it was given on the command line. That is why
#   run_tests.py wraps pvbatch in a launcher but never wraps visit.
#
# AN HONEST NOTE ON THE TIMING MODEL
#
#   VisIt's pipeline is lazy and fuses reading with filtering: by the time
#   DrawPlots() returns, the database read and the contour have executed
#   together and there is no supported way to separate them from the client.
#   So this vignette reports:
#
#     open_time_s      OpenDatabase -- metadata open, no bulk read
#     pipeline_time_s  DrawPlots    -- fused read + isosurface execution
#     render_time_s    SaveWindow   -- rasterisation and image write
#
#   The CSV carries a timing_model column recording this, so a VisIt row is
#   never silently averaged against a ParaView row whose io_time_s means
#   something different.
#
# WHAT IT ASSERTS
#
#   Geometry is rank-invariant: zone count of the extracted isosurface, the
#   scalar range, and the surface area must not change with the engine's rank
#   count. Node counts are recorded but not asserted, because a node on a
#   domain boundary is duplicated per domain.
#
# DATA
#
#   data/varying_data/varying*.vtk, point scalar "temp". Shipped with the
#   repository. A .visit index carrying absolute paths is written into the
#   output directory at run time, because the shipped data/varying.visit uses
#   paths relative to a working directory the harness does not guarantee.
#
# RUNNING IT
#
#   Standalone, serial, no engine launch:
#     visit -cli -nowin -s ex07_visitScaling.py
#
#   On Ibex, 8 ranks across 2 nodes:
#     visit -cli -nowin -s ex07_visitScaling.py \
#         --machine ibex --nodes 2 --ranks 8 --partition batch
#
#   Through the harness:
#     python3 Testing/test_suite.py ../ --test_type VisIt --ranks 8 --nodes 2 \
#         --machine ibex --machine_name ibex-cpu
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


VIGNETTE = "ex07_visitScaling"
TOOL = "VisIt"


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


def write_visit_index(ctx, series):
    """Write a .visit index with absolute paths.

    The shipped data/varying.visit lists paths relative to the repository
    root, so opening it only works from one particular working directory.
    Writing our own index removes that dependency entirely.
    """
    index_path = os.path.join(ctx.output_dir, "{0}_series.visit".format(VIGNETTE))
    with open(index_path, "w") as handle:
        handle.write("!NBLOCKS 1\n")
        for path in series:
            handle.write(path + "\n")
    ctx.log("wrote database index: {0}".format(index_path))
    return index_path


def query_value(name, **kwargs):
    """Run a VisIt query and return its numeric output.

    GetQueryOutputValue() returns a float for scalar queries and a tuple for
    multi-valued ones such as MinMax.
    """
    Query(name, **kwargs)
    return GetQueryOutputValue()


def run(ctx):
    scalar = ctx.args.scalar
    series = ctx.timestep_files()
    ctx.log("time series: {0} file(s)".format(len(series)))
    ctx.log("contouring '{0}' at {1}".format(scalar, ctx.args.isovalue))

    # Launch the compute engine when a site was named. `--machine local`
    # deliberately stays in-process.
    engine_launched = vc.open_visit_engine(ctx, OpenComputeEngine)
    # A note, not a metric. `metrics` is a correctness gate compared against
    # the baseline; how the engine was launched is a property of the run,
    # not of the result. Gating on it makes every rank change look like a
    # regression -- measured: the same suite at --ranks 8 produced
    # bit-identical images and failed here on "expected false, got true".
    # ex08_visitBackendCheck keeps it as a metric, because the backend IS
    # its subject.
    ctx.notes.append("compute_engine_launched={0}".format(bool(engine_launched)))

    index_path = write_visit_index(ctx, series)

    # -- Database open ---------------------------------------------------
    with ctx.phase("open"):
        if not OpenDatabase(index_path, 0):
            raise vc.VignetteError("OpenDatabase failed for {0}".format(index_path))

    n_states = TimeSliderGetNStates()
    ctx.log("timesteps in database: {0}".format(n_states))

    requested = ctx.args.timesteps or n_states
    n_steps = max(1, min(requested, n_states))

    # -- Plot and operator ------------------------------------------------
    AddPlot("Pseudocolor", scalar, 1, 0)

    pc_atts = PseudocolorAttributes()
    pc_atts.colorTableName = "hot_desaturated"
    SetPlotOptions(pc_atts)

    AddOperator("Isosurface")
    iso_atts = IsosurfaceAttributes()
    iso_atts.contourMethod = iso_atts.Value
    iso_atts.contourValue = (ctx.args.isovalue,)
    iso_atts.variable = scalar
    SetOperatorOptions(iso_atts)

    annotation = AnnotationAttributes()
    annotation.userInfoFlag = 0
    annotation.databaseInfoFlag = 0
    annotation.legendInfoFlag = 0
    SetAnnotationAttributes(annotation)

    # -- Timed sweep over the series --------------------------------------
    # DrawPlots() is where the read and the contour both happen. Accumulating
    # across every timestep gives a far steadier number than one step does.
    zones = nodes = 0
    scalar_min = scalar_max = 0.0

    for state in range(n_steps):
        SetTimeSliderState(state)
        with ctx.phase("pipeline", accumulate=True):
            DrawPlots()

        zones = int(query_value("NumZones", use_actual_data=1))
        nodes = int(query_value("NumNodes", use_actual_data=1))
        ctx.debug("state {0}: {1} zones / {2} nodes".format(state, zones, nodes))

    # use_actual_data=0, deliberately. This plot carries the Isosurface
    # operator, so with use_actual_data=1 every point IS the isovalue and
    # MinMax returns (3.0, 3.0) -- measured on VisIt 3.4.2. The assertion
    # below ("scalar range is non-degenerate") could therefore never pass, and
    # the recorded scalar_min/scalar_max were the isovalue twice rather than
    # anything about the data. Asking for the original data range is what the
    # metric was always meant to report.
    minmax = query_value("MinMax", use_actual_data=0)
    if isinstance(minmax, (list, tuple)) and len(minmax) >= 2:
        scalar_min, scalar_max = float(minmax[0]), float(minmax[1])

    surface_area = float(query_value("3D surface area"))

    ctx.add_metric("timesteps_processed", n_steps)
    ctx.add_metric("isosurface_zones", zones)
    ctx.add_metric("scalar_min", round(scalar_min, 6))
    ctx.add_metric("scalar_max", round(scalar_max, 6))
    ctx.add_metric("surface_area", round(surface_area, 4))

    # -- Render -----------------------------------------------------------
    ResetView()

    save_atts = SaveWindowAttributes()
    save_atts.family = 0
    save_atts.format = save_atts.PNG
    save_atts.width = ctx.args.image_width
    save_atts.height = ctx.args.image_height
    save_atts.resConstraint = save_atts.NoConstraint
    save_atts.outputToCurrentDirectory = 0
    save_atts.outputDirectory = ctx.output_dir

    image_name = "{0}_isosurface.png".format(VIGNETTE)
    save_atts.fileName = image_name
    SetSaveWindowAttributes(save_atts)

    with ctx.phase("render"):
        SaveWindow()

    ctx.image_path(image_name)

    # -- Scaling CSV -------------------------------------------------------
    row = {
        "vignette": VIGNETTE,
        "tool": TOOL,
        "timing_model": "visit-fused-read-filter",
        "machine": ctx.args.machine,
        "nodes": ctx.args.nodes,
        "ranks": ctx.args.ranks,
        "engine_launched": int(bool(engine_launched)),
        "timesteps": n_steps,
        "isosurface_zones": zones,
        "isosurface_nodes": nodes,
        "surface_area": surface_area,
        "open_time_s": ctx.timings.get("open", 0.0),
        "pipeline_time_s": ctx.timings.get("pipeline", 0.0),
        "render_time_s": ctx.timings.get("render", 0.0),
        "image_width": ctx.args.image_width,
        "image_height": ctx.args.image_height,
    }
    ctx.write_timing_csv(rows=[row])

    ctx.log(
        "open={0:.4f}s  pipeline={1:.4f}s  render={2:.4f}s".format(
            ctx.timings.get("open", 0.0),
            ctx.timings.get("pipeline", 0.0),
            ctx.timings.get("render", 0.0),
        )
    )

    # -- Assertions --------------------------------------------------------
    ctx.assert_true(
        "database reports timesteps",
        n_states > 0,
        "n_states={0}".format(n_states),
    )
    ctx.assert_true(
        "isosurface is non-empty",
        zones > 0,
        "zones={0}".format(zones),
    )
    ctx.assert_true(
        "isosurface has finite area",
        surface_area > 0.0,
        "area={0}".format(surface_area),
    )
    ctx.assert_true(
        "scalar range is non-degenerate",
        scalar_max > scalar_min,
        "range=[{0}, {1}]".format(scalar_min, scalar_max),
    )
    ctx.assert_true(
        "image was written",
        os.path.exists(os.path.join(ctx.output_dir, image_name)),
        image_name,
    )
    ctx.assert_true(
        "pipeline and render phases were both timed",
        ctx.timings.get("pipeline", 0.0) > 0.0 and ctx.timings.get("render", 0.0) > 0.0,
        "pipeline={0:.6f}s render={1:.6f}s".format(
            ctx.timings.get("pipeline", 0.0), ctx.timings.get("render", 0.0)
        ),
    )

    DeleteAllPlots()
    CloseDatabase(index_path)


def main():
    args = vc.parse_args(
        VIGNETTE,
        TOOL,
        description="Isosurface scaling study driven through the VisIt "
        "compute engine.",
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
