#
# Visualization Vignettes
#
# ex08_visitBackendCheck -- verify the compute engine's offscreen rendering
#                           context actually initialised
#
# WHY THIS VIGNETTE EXISTS
#
#   The counterpart to ex08_pvBackendCheck. Same failure being hunted: a
#   headless job that believes it is rendering on a GPU while something else
#   quietly does the work, or an engine that never came up at the size the
#   job asked for.
#
# WHAT VISIT CAN AND CANNOT TELL YOU
#
#   Being straight about this, because the ParaView half of ex08 reads
#   GL_RENDERER directly and this half cannot: VisIt's Python interface does
#   not expose the engine's OpenGL vendor or renderer string. There is no
#   supported client-side call that returns it. Writing code that pretended
#   to read one would be a lie in a test.
#
#   What VisIt does expose, and what this vignette therefore checks:
#
#     1. The compute engine exists and reports the parallelism that was
#        requested -- GetProcessAttributes("engine") gives numProcs, numNodes
#        and isParallel. An engine that silently came up serial when eight
#        ranks were asked for is caught here.
#
#     2. Scalable (engine-side) rendering can be forced on and a frame comes
#        back. This is the real offscreen-context test: in scalable mode the
#        engine rasterises and ships an image to the client, so a successful
#        render proves the engine built a usable offscreen context on the
#        compute node -- exactly the thing that fails when EGL or GLX is
#        missing there.
#
#     3. The saved PNG is the resolution that was requested. A fallback
#        context frequently cannot honour the requested window size.
#
#   Pass --hw-accel to add VisIt's -hw-accel flag to the engine launch, which
#   requests a hardware-accelerated offscreen context. Combined with check 2,
#   a failure then means the GPU context specifically did not come up.
#
# DATA
#
#   data/varying_data/varying*.vtk, point scalar "temp". Shipped with the
#   repository.
#
# RUNNING IT
#
#   Locally, serial:
#     visit -cli -nowin -s ex08_visitBackendCheck.py
#
#   On an Ibex GPU node, demanding a hardware offscreen context:
#     visit -cli -nowin -s ex08_visitBackendCheck.py \
#         --machine ibex --nodes 1 --ranks 8 --hw-accel --require-parallel
#
#   This vignette is registered in test_suite.is_gpu_test_allowed_to_fail, so
#   --non_gpu_machine downgrades its GPU expectations to warnings.
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


VIGNETTE = "ex08_visitBackendCheck"
TOOL = "VisIt"


def add_arguments(parser):
    parser.add_argument(
        "--hw-accel",
        action="store_true",
        help="Add VisIt's -hw-accel to the engine launch, requesting a "
        "hardware-accelerated offscreen context on the compute node.",
    )
    parser.add_argument(
        "--require-parallel",
        action="store_true",
        help="Fail unless the engine came up parallel with the requested "
        "rank and node counts.",
    )
    parser.add_argument(
        "--scalar",
        default=vc.SHARED_SCALAR,
        help="Point scalar to plot while exercising the render path.",
    )


def engine_attributes(ctx):
    """Read the compute engine's process attributes, or None.

    Only meaningful once a plot has been drawn, because that is when VisIt
    actually launches an engine for a locally-opened database.
    """
    try:
        attributes = GetProcessAttributes("engine")
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        ctx.warn("GetProcessAttributes('engine') failed: {0}".format(exc))
        return None

    if attributes is None:
        return None

    def field(name, default=0):
        return getattr(attributes, name, default)

    hosts = list(field("hosts", []) or [])
    return {
        "num_procs": int(field("numProcs", 0)),
        "num_nodes": int(field("numNodes", 0)),
        "is_parallel": bool(field("isParallel", False)),
        "hosts": hosts,
        "unique_hosts": sorted(set(hosts)),
    }


def force_scalable_rendering(ctx):
    """Turn on engine-side (scalable) rendering.

    In scalable mode the engine rasterises on the compute node and sends an
    image to the client. A render that succeeds in this mode proves the
    engine built a working offscreen context -- which is what we are testing.
    """
    rendering = GetRenderingAttributes()
    rendering.scalableActivationMode = rendering.Always
    SetRenderingAttributes(rendering)
    ctx.log("scalable (engine-side) rendering forced on")
    return rendering


def run(ctx):
    scalar = ctx.args.scalar

    extra_engine_args = ["-hw-accel"] if ctx.args.hw_accel else None
    if ctx.args.hw_accel:
        ctx.log("requesting hardware-accelerated offscreen context (-hw-accel)")

    engine_launched = vc.open_visit_engine(
        ctx, OpenComputeEngine, extra=extra_engine_args
    )

    ctx.log("VisIt version: {0}".format(Version()))
    ctx.notes.append("visit_version={0}".format(Version()))

    # -- Open data and draw so an engine exists ---------------------------
    dataset = ctx.dataset("varying_first")
    if not OpenDatabase(dataset, 0):
        raise vc.VignetteError("OpenDatabase failed for {0}".format(dataset))

    AddPlot("Pseudocolor", scalar, 1, 0)

    annotation = AnnotationAttributes()
    annotation.userInfoFlag = 0
    annotation.databaseInfoFlag = 0
    annotation.legendInfoFlag = 0
    SetAnnotationAttributes(annotation)

    DrawPlots()

    # -- 1. Engine parallelism --------------------------------------------
    attributes = engine_attributes(ctx)
    if attributes is None:
        ctx.warn("engine process attributes unavailable")
        num_procs = num_nodes = 0
        is_parallel = False
    else:
        num_procs = attributes["num_procs"]
        num_nodes = attributes["num_nodes"]
        is_parallel = attributes["is_parallel"]
        ctx.log(
            "engine: {0} proc(s) on {1} node(s), parallel={2}, hosts={3}".format(
                num_procs, num_nodes, is_parallel, attributes["unique_hosts"]
            )
        )
        ctx.notes.append("engine_hosts={0}".format(",".join(attributes["unique_hosts"])))

    ctx.add_metric("compute_engine_launched", bool(engine_launched))
    ctx.add_metric("engine_is_parallel", bool(is_parallel))
    ctx.add_metric("hw_accel_requested", bool(ctx.args.hw_accel))

    # Process and node counts are recorded as notes rather than metrics: they
    # are a property of how the job was launched, not of the data, so
    # baselining them would make every differently-sized run fail.
    ctx.notes.append("engine_num_procs={0}".format(num_procs))
    ctx.notes.append("engine_num_nodes={0}".format(num_nodes))

    # -- 2. Engine-side render --------------------------------------------
    force_scalable_rendering(ctx)

    save_atts = SaveWindowAttributes()
    save_atts.family = 0
    save_atts.format = save_atts.PNG
    save_atts.width = ctx.args.image_width
    save_atts.height = ctx.args.image_height
    save_atts.resConstraint = save_atts.NoConstraint
    save_atts.outputToCurrentDirectory = 0
    save_atts.outputDirectory = ctx.output_dir

    image_name = "{0}_probe.png".format(VIGNETTE)
    save_atts.fileName = image_name
    SetSaveWindowAttributes(save_atts)

    ResetView()

    render_ok = True
    with ctx.phase("render"):
        try:
            RedrawWindow()
            SaveWindow()
        except Exception as exc:  # noqa: BLE001 - this failing IS the result
            render_ok = False
            ctx.warn("engine-side render failed: {0}".format(exc))

    image_path = os.path.join(ctx.output_dir, image_name)
    ctx.image_path(image_name)

    written_width, written_height = vc.png_size(image_path)
    ctx.add_metric("image_width", written_width)
    ctx.add_metric("image_height", written_height)
    ctx.add_metric("engine_side_render_succeeded", bool(render_ok and written_width > 0))

    # -- Assertions --------------------------------------------------------
    ctx.assert_true(
        "compute engine reported its attributes",
        attributes is not None,
        "GetProcessAttributes('engine') returned nothing",
    )

    ctx.assert_true(
        "engine-side (scalable) render produced an image",
        render_ok and os.path.exists(image_path) and written_width > 0,
        "Scalable rendering runs on the compute node, so this failing means "
        "the engine could not create a usable offscreen context there"
        + (" even with -hw-accel" if ctx.args.hw_accel else ""),
    )

    ctx.assert_true(
        "rendered at the requested resolution",
        (written_width, written_height)
        == (ctx.args.image_width, ctx.args.image_height),
        "requested {0}x{1}, got {2}x{3}".format(
            ctx.args.image_width,
            ctx.args.image_height,
            written_width,
            written_height,
        ),
    )

    if ctx.args.require_parallel:
        ctx.assert_true(
            "engine came up parallel",
            is_parallel,
            "engine reports isParallel={0}; a serial engine when ranks were "
            "requested means the launch profile was ignored".format(is_parallel),
        )
        ctx.assert_true(
            "engine has the requested rank count",
            num_procs == ctx.args.ranks,
            "requested {0} rank(s), engine reports {1}".format(
                ctx.args.ranks, num_procs
            ),
        )
        ctx.assert_true(
            "engine spans the requested node count",
            num_nodes == ctx.args.nodes,
            "requested {0} node(s), engine reports {1}".format(
                ctx.args.nodes, num_nodes
            ),
        )
    else:
        ctx.log(
            "--require-parallel not set: engine parallelism reported but not "
            "asserted."
        )

    DeleteAllPlots()
    CloseDatabase(dataset)


def main():
    args = vc.parse_args(
        VIGNETTE,
        TOOL,
        description="Verify the VisIt compute engine's offscreen rendering "
        "context and parallelism.",
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
