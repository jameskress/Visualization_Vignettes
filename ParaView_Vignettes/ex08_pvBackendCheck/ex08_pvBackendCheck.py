#
# Visualization Vignettes
#
# ex08_pvBackendCheck -- assert the render backend is the one you asked for
#
# WHY THIS VIGNETTE EXISTS
#
#   The most expensive failure in HPC visualization is silent: a job requests
#   a GPU, the EGL context fails to initialise, Mesa's llvmpipe picks up the
#   work, and everything still renders -- forty times slower, on hardware you
#   are being charged for. Nothing errors. The images look fine. The only
#   symptom is a job that took an hour instead of ninety seconds.
#
#   This vignette turns that into a test failure.
#
# WHAT IT DOES
#
#   Reads the live OpenGL vendor, renderer and version strings out of the
#   running ParaView through GetOpenGLInformation(), classifies the backend
#   as hardware-accelerated or software, and compares that against what the
#   caller said to expect.
#
#   It then renders a real frame and checks that the PNG came out at the
#   requested resolution -- the second half of the same failure, since a
#   fallback context frequently cannot honour the requested window size.
#
# EXPECTATIONS
#
#   --expect-backend gpu       fail if the renderer is a software rasteriser
#   --expect-backend egl       same as gpu, and record that EGL was intended
#   --expect-backend osmesa    fail if a GPU was used -- catches a CPU-only
#                              queue that unexpectedly bound a device
#   --expect-backend software  synonym for osmesa
#   --expect-backend auto      report only; assert only that a usable GL
#                              context exists at all (the default, so the
#                              vignette is useful before you know what the
#                              node has)
#
#   EGL and OSMesa cannot be told apart from GL strings alone -- an EGL build
#   on a node with no device reports exactly what an OSMesa build reports. So
#   the assertion is framed as hardware versus software, which is the
#   distinction that actually costs money, and the intended backend is
#   recorded alongside it for the record.
#
# RUNNING IT
#
#   On a GPU node, demanding hardware acceleration:
#     pvbatch ex08_pvBackendCheck.py --expect-backend gpu
#
#   On a CPU-only queue:
#     pvbatch --force-offscreen-rendering ex08_pvBackendCheck.py \
#         --expect-backend osmesa
#
#   Through the harness -- note that this vignette is registered in
#   test_suite.is_gpu_test_allowed_to_fail, so --non_gpu_machine downgrades a
#   GPU expectation failure to a warning:
#     python3 Testing/test_suite.py ../ --test_type ParaView --machine_name ci
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


VIGNETTE = "ex08_pvBackendCheck"
TOOL = "ParaView"

# Substrings that identify a software rasteriser in a GL_RENDERER string.
# llvmpipe and softpipe are Mesa's CPU rasterisers; swrast is the classic
# software path; "Mesa OffScreen" is what several OSMesa builds report.
SOFTWARE_RENDERER_MARKERS = (
    "llvmpipe",
    "softpipe",
    "swrast",
    "mesa offscreen",
    "software rasterizer",
    "lavapipe",
)

# Vendors that only ship hardware drivers. Used as a positive signal so that
# an unfamiliar renderer string on a real GPU is not misclassified.
HARDWARE_VENDOR_MARKERS = ("nvidia", "advanced micro devices", "amd", "ati", "intel")

EXPECT_HARDWARE = ("gpu", "egl")
EXPECT_SOFTWARE = ("osmesa", "software")


def add_arguments(parser):
    parser.add_argument(
        "--expect-backend",
        choices=("auto", "gpu", "egl", "osmesa", "software"),
        default="auto",
        help="Backend the caller believes this job asked for.",
    )


def collect_opengl_information(ctx):
    """Read GL strings from the render server, falling back to the client.

    In a client-server or parallel launch the render server is the process
    whose backend matters. In pvbatch's builtin session the two are the same
    process, and the RENDER_SERVER location is still valid.
    """
    from paraview.servermanager import vtkPVSession

    attempts = [
        ("render_server", vtkPVSession.RENDER_SERVER),
        ("client", vtkPVSession.CLIENT),
    ]

    for label, location in attempts:
        try:
            info = GetOpenGLInformation(location)
        except Exception as exc:  # noqa: BLE001 - try the next location
            ctx.debug("GetOpenGLInformation({0}) failed: {1}".format(label, exc))
            continue

        if info is None:
            continue

        vendor = info.GetVendor() or ""
        renderer = info.GetRenderer() or ""
        version = info.GetVersion() or ""

        if vendor or renderer:
            ctx.log("OpenGL information source: {0}".format(label))
            return {
                "source": label,
                "vendor": vendor,
                "renderer": renderer,
                "version": version,
                "capabilities": info.GetCapabilities() or "",
            }

    raise vc.VignetteError(
        "GetOpenGLInformation() returned no usable vendor or renderer string. "
        "There is no OpenGL context at all -- check that the build has a "
        "rendering backend and that the job has a display or an offscreen "
        "context available."
    )


# VTK_DEFAULT_OPENGL_WINDOW values and what each one is asking for. Both the
# site's run_pvserver.sbat and this repository's ParaView_Vignettes/MODULES.sh
# set this variable from the loaded module name, so it records the intent of
# whoever configured the job -- which is a different thing from what the
# driver actually gave us, and worth comparing against it.
OPENGL_WINDOW_INTENT = {
    "vtkeglrenderwindow": "hardware",
    "vtkosopenglrenderwindow": "software",
    "vtkosmesarenderwindow": "software",
    "vtkxopenglrenderwindow": "display",
    "vtkwin32openglrenderwindow": "display",
    "vtkcocoarenderwindow": "display",
}

EXPECT_HARDWARE = ("gpu", "egl")


def report_backend_environment(ctx):
    """Record how the environment asked for a backend, and check it agrees.

    Returns True when the request is self-consistent. A job that loads a
    Mesa module and then demands a GPU has a configuration bug that no
    amount of rendering will reveal -- both halves succeed on their own
    terms -- so it is caught here, before the render, and named.
    """
    window = os.environ.get("VTK_DEFAULT_OPENGL_WINDOW", "")
    module = os.environ.get("VV_PARAVIEW_MODULE", "")
    expected = ctx.args.expect_backend

    ctx.notes.append("VTK_DEFAULT_OPENGL_WINDOW={0}".format(window or "<unset>"))
    ctx.notes.append("VV_PARAVIEW_MODULE={0}".format(module or "<unset>"))
    ctx.log("VTK_DEFAULT_OPENGL_WINDOW: {0}".format(window or "<unset>"))
    ctx.log("ParaView module          : {0}".format(module or "<unset>"))

    if not window:
        ctx.warn(
            "VTK_DEFAULT_OPENGL_WINDOW is unset. ParaView 6.0+ picks a render "
            "window class from it, and the site's run_pvserver.sbat sets it "
            "from the module name. Source ParaView_Vignettes/MODULES.sh, or "
            "export it by hand, so the backend is chosen rather than guessed."
        )
        return True

    intent = OPENGL_WINDOW_INTENT.get(window.strip().lower())
    if intent is None:
        ctx.warn(
            "VTK_DEFAULT_OPENGL_WINDOW={0} is not a class this vignette "
            "recognises; its intent cannot be checked against "
            "--expect-backend.".format(window)
        )
        return True

    if expected == "auto":
        ctx.log("--expect-backend auto: not cross-checking the environment.")
        return True

    wants_hardware = expected in EXPECT_HARDWARE
    if wants_hardware and intent == "software":
        ctx.error(
            "configuration contradiction: --expect-backend {0} asks for "
            "hardware rendering, but VTK_DEFAULT_OPENGL_WINDOW={1} selects a "
            "software render window. The loaded module is {2}. Load the -egl "
            "variant, or expect osmesa.".format(expected, window, module or "<unknown>")
        )
        return False

    if not wants_hardware and intent == "hardware":
        ctx.error(
            "configuration contradiction: --expect-backend {0} asks for "
            "software rendering, but VTK_DEFAULT_OPENGL_WINDOW={1} selects an "
            "EGL render window. The loaded module is {2}. Load the -mesa "
            "variant, or expect gpu.".format(expected, window, module or "<unknown>")
        )
        return False

    ctx.log(
        "environment agrees with --expect-backend {0} "
        "(window class intent: {1}).".format(expected, intent)
    )
    return True


def classify_backend(vendor, renderer):
    """Return 'software', 'hardware', or 'unknown' for these GL strings."""
    haystack = (renderer + " " + vendor).lower()

    for marker in SOFTWARE_RENDERER_MARKERS:
        if marker in haystack:
            return "software"

    for marker in HARDWARE_VENDOR_MARKERS:
        if marker in vendor.lower():
            return "hardware"

    # A renderer string that names neither a known software rasteriser nor a
    # known hardware vendor. Report it rather than guessing.
    return "unknown"


def run(ctx):
    expected = ctx.args.expect_backend
    ctx.log("expected backend: {0}".format(expected))

    paraview.simple._DisableFirstRenderCameraReset()

    gl_info = collect_opengl_information(ctx)
    vendor = gl_info["vendor"]
    renderer = gl_info["renderer"]
    version = gl_info["version"]

    ctx.log("GL_VENDOR   : {0}".format(vendor))
    ctx.log("GL_RENDERER : {0}".format(renderer))
    ctx.log("GL_VERSION  : {0}".format(version))

    classification = classify_backend(vendor, renderer)
    ctx.log("classified as: {0}".format(classification))

    # The GL strings themselves are recorded as notes, not metrics: they are
    # legitimately different on every machine, so baselining them would make
    # the test fail everywhere except the machine it was blessed on.
    ctx.notes.append("GL_VENDOR={0}".format(vendor))
    ctx.notes.append("GL_RENDERER={0}".format(renderer))
    ctx.notes.append("GL_VERSION={0}".format(version))

    ctx.add_metric("backend_classification", classification)
    ctx.add_metric("expected_backend", expected)
    ctx.add_metric("has_gl_context", bool(vendor or renderer))

    # Does the environment ask for the backend this run expects? True in every
    # correctly configured job on every machine, so unlike the GL strings this
    # one is safe to baseline.
    environment_consistent = report_backend_environment(ctx)
    ctx.add_metric("backend_request_consistent", environment_consistent)
    ctx.assert_true(
        "backend_request_consistent",
        environment_consistent,
        "VTK_DEFAULT_OPENGL_WINDOW and --expect-backend must not ask for "
        "opposite things.",
    )

    # -- Render a real frame ---------------------------------------------
    # A vendor string proves a context was queried. Only an actual render
    # proves the context can rasterise, which is the thing under test.
    source = Sphere(registrationName="ex08_probe")
    source.ThetaResolution = 64
    source.PhiResolution = 64

    view = GetActiveViewOrCreate("RenderView")
    view.ViewSize = [ctx.args.image_width, ctx.args.image_height]
    view.ShowAnnotation = False
    view.OrientationAxesVisibility = 0
    view.UseColorPaletteForBackground = 0
    view.BackgroundColorMode = "Single Color"
    view.Background = [0.09, 0.10, 0.12]

    display = Show(source, view)
    display.Representation = "Surface"
    display.AmbientColor = [1.0, 1.0, 1.0]
    display.DiffuseColor = [0.35, 0.52, 0.90]

    ResetCamera(view)

    image_name = "{0}_probe.png".format(VIGNETTE)
    image_path = ctx.image_path(image_name)

    with ctx.phase("render"):
        Render(view)
        SaveScreenshot(
            image_path,
            view,
            ImageResolution=[ctx.args.image_width, ctx.args.image_height],
        )

    written_width, written_height = vc.png_size(image_path)
    ctx.add_metric("image_width", written_width)
    ctx.add_metric("image_height", written_height)

    # -- Assertions -------------------------------------------------------
    ctx.assert_true(
        "an OpenGL context exists",
        bool(vendor or renderer),
        "vendor='{0}' renderer='{1}'".format(vendor, renderer),
    )

    ctx.assert_true(
        "a frame was rendered and written",
        os.path.exists(image_path) and written_width > 0,
        "{0} ({1}x{2})".format(image_name, written_width, written_height),
    )

    # A fallback context often cannot honour the requested window size, so a
    # resolution mismatch here is a backend symptom, not a cosmetic one.
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

    if expected in EXPECT_HARDWARE:
        ctx.assert_true(
            "hardware acceleration is active",
            classification == "hardware",
            "expected {0} but GL_RENDERER '{1}' classifies as {2}. A software "
            "rasteriser here means the {0} context failed to initialise and "
            "Mesa took over.".format(expected, renderer, classification),
        )
    elif expected in EXPECT_SOFTWARE:
        ctx.assert_true(
            "software rendering is active as requested",
            classification == "software",
            "expected {0} but GL_RENDERER '{1}' classifies as {2}".format(
                expected, renderer, classification
            ),
        )
    else:
        ctx.log(
            "--expect-backend auto: reporting only. Pass gpu/egl/osmesa to "
            "turn the classification into an assertion."
        )
        # Neutral wording on purpose: assert_true prints this detail whether
        # the assertion passed or failed, so a sentence phrased as the failure
        # reason reads as a contradiction next to [PASS].
        ctx.assert_true(
            "backend classification is conclusive",
            classification in ("hardware", "software"),
            "GL_RENDERER '{0}' classified as {1}".format(renderer, classification),
        )


def main():
    args = vc.parse_args(
        VIGNETTE,
        TOOL,
        description="Verify the active OpenGL backend and fail on a silent "
        "software fallback.",
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
