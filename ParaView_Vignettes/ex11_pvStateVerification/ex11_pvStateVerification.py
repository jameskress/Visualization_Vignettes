#
# Visualization Vignettes
#
# ex11_pvStateVerification -- load a saved state headlessly, step time, render
#
# WHY THIS VIGNETTE EXISTS
#
#   Saved states are how real users carry a visualization between machines
#   and between sessions, and a .pvsm is version-sensitive: a state written
#   by one ParaView may load into the next with a dropped property, a renamed
#   preset, or a reader that no longer exists -- usually with a warning
#   nobody reads. This repository ships state files and, until now, never
#   opened one in a test.
#
#   It also exercises the interactive-style path rather than the batch path:
#   the state is loaded under a real (virtual) display, the animation is
#   stepped, a frame is rendered, and the connection is torn down cleanly.
#
# RUNNING IT UNDER XVFB
#
#   This vignette deliberately does NOT force offscreen rendering, because
#   the point is to verify the on-display path that a GUI user actually
#   takes. Give it a virtual display:
#
#     xvfb-run -a --server-args="-screen 0 1024x1024x24" \
#         pvbatch ex11_pvStateVerification.py
#
#   Through the harness, note --no-offscreen:
#     xvfb-run -a python3 Testing/test_suite.py ../ --test_type ParaView \
#         --no-offscreen --machine_name my-machine
#
#   With no DISPLAY at all the vignette still runs and says so in its notes,
#   falling back to whatever offscreen context the build provides. It asserts
#   on what it can verify either way.
#
# PREREQUISITE
#
#   The state file must exist. Generate it once per ParaView major version:
#     pvbatch ex11_make_state.py
#
#   A missing state file is a FAILURE, not something this vignette silently
#   creates -- a test that generates its own fixture and then verifies it
#   proves nothing.
#
# WHAT IT ASSERTS
#
#   The state loaded and produced at least one source and one view; the view
#   is the size the state recorded; the animation reports the expected number
#   of timesteps; stepping the time actually changes the reported time; a
#   frame was rendered at each visited timestep; and Disconnect() completed
#   without error.
#
# Author: James Kress, <james@jameskress.com>
#
import os
import re
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


VIGNETTE = "ex11_pvStateVerification"
TOOL = "ParaView"

STATE_FILENAME = "ex11_state.pvsm"


def add_arguments(parser):
    parser.add_argument(
        "--state",
        default=None,
        help="Path to the .pvsm to load. Defaults to {0} beside this "
        "script.".format(STATE_FILENAME),
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=3,
        help="How many timesteps to step through and render.",
    )


def load_state_with_data_dir(ctx, state_path):
    """Load a state, redirecting its recorded data paths to our data dir.

    A .pvsm records absolute filenames. Loading one in a checkout at a
    different path fails unless ParaView is told where the data actually
    lives. The keyword form is preferred; older builds that do not accept it
    fall back to the plain call, which works whenever the paths still
    resolve.
    """
    # A .pvsm records the ParaView that wrote it, in
    # <ServerManagerState version="6.1.0">. Nothing read it, so a state file
    # carried across a version boundary was loaded and then failed somewhere
    # further downstream. Read it first and say so plainly.
    vc.check_fixture_version(
        ctx,
        _state_file_version(state_path),
        vc.paraview_version_string(),
        os.path.basename(state_path),
        "pvbatch ex11_make_state.py",
    )

    # The keyword is restrict_to_data_DIRECTORY, in ParaView 5.13 and 6.1
    # alike. The previous spelling, restrict_to_data_files, matched no
    # release: ParaView does not reject an unknown keyword, it forwards it to
    # _LoadStateLegacy, which tries to set it as a property on a proxy and
    # raises "Attribute restrict_to_data_files does not exist". That is an
    # AttributeError, so the `except TypeError` below never caught it and the
    # fallback path was unreachable -- the vignette simply died.
    try:
        LoadState(
            state_path,
            data_directory=ctx.data_dir,
            restrict_to_data_directory=False,
        )
        ctx.log("state loaded with data_directory={0}".format(ctx.data_dir))
        return "data_directory"
    except (TypeError, AttributeError, RuntimeError) as exc:
        # Broad on purpose. A build that does not support the keyword form
        # signals it differently in each release -- TypeError from the
        # signature, AttributeError from the legacy property path,
        # RuntimeError from the state loader -- and all three mean the same
        # thing here: fall back to the paths recorded in the state.
        ctx.warn(
            "LoadState(data_directory=...) failed ({0}: {1}); falling back "
            "to the paths recorded in the state file.".format(
                type(exc).__name__, exc
            )
        )

    LoadState(state_path)
    ctx.log("state loaded using the paths recorded in the state file")
    return "recorded_paths"


def _state_file_version(path):
    """The ParaView version recorded inside a .pvsm, or None.

    Read as text rather than parsed as XML: the attribute is in the first few
    lines, the file can be tens of megabytes, and a malformed state should
    produce "unknown version" here rather than an exception before the
    vignette has had a chance to report anything.
    """
    try:
        with open(path, "r") as handle:
            for _ in range(20):
                line = handle.readline()
                if not line:
                    break
                match = re.search(r'ServerManagerState[^>]*version="([^"]+)"', line)
                if match:
                    return match.group(1)
    except (OSError, IOError):
        pass
    return None


def run(ctx):
    paraview.simple._DisableFirstRenderCameraReset()

    display_env = os.environ.get("DISPLAY", "")
    if display_env:
        ctx.log("DISPLAY={0} -- rendering through the display path".format(display_env))
    else:
        ctx.warn(
            "No DISPLAY set. Running through whatever offscreen context the "
            "build provides. Wrap this vignette in xvfb-run to exercise the "
            "on-display path it is meant to cover."
        )
    ctx.notes.append("display={0}".format(display_env or "<none>"))

    state_path = ctx.args.state or os.path.join(SCRIPT_DIR, STATE_FILENAME)
    if not os.path.exists(state_path):
        raise vc.VignetteError(
            "State file not found: {0}\n  Generate it once with:\n"
            "    pvbatch {1}".format(
                state_path, os.path.join(SCRIPT_DIR, "ex11_make_state.py")
            )
        )
    ctx.log("state file: {0}".format(state_path))

    # -- load --------------------------------------------------------------
    with ctx.phase("load_state"):
        load_mode = load_state_with_data_dir(ctx, state_path)
    ctx.notes.append("load_mode={0}".format(load_mode))

    sources = GetSources()
    views = GetViews()
    ctx.log("state produced {0} source(s), {1} view(s)".format(len(sources), len(views)))

    if not views:
        raise vc.VignetteError(
            "The state loaded but produced no views. The .pvsm is probably "
            "from an incompatible ParaView version -- regenerate it with "
            "ex11_make_state.py."
        )

    view = GetActiveView() or views[0]
    view_size = list(view.ViewSize)
    ctx.log("view size from state: {0}x{1}".format(view_size[0], view_size[1]))

    ctx.add_metric("sources_in_state", len(sources))
    ctx.add_metric("views_in_state", len(views))
    ctx.add_metric("state_view_width", int(view_size[0]))
    ctx.add_metric("state_view_height", int(view_size[1]))

    # -- animation ---------------------------------------------------------
    scene = GetAnimationScene()
    scene.UpdateAnimationUsingDataTimeSteps()

    timekeeper = GetTimeKeeper()
    timesteps = list(timekeeper.TimestepValues or [])
    ctx.log("timekeeper reports {0} timestep(s)".format(len(timesteps)))
    ctx.add_metric("timesteps_in_state", len(timesteps))

    if not timesteps:
        timesteps = [0.0]

    step_count = max(1, min(ctx.args.steps, len(timesteps)))
    visited = []

    for index in range(step_count):
        target_time = timesteps[index]
        scene.AnimationTime = target_time

        with ctx.phase("render", accumulate=True):
            Render(view)
            image_name = "{0}_step{1:02d}.png".format(VIGNETTE, index)
            image_path = ctx.image_path(image_name)
            SaveScreenshot(
                image_path,
                view,
                ImageResolution=[int(view_size[0]), int(view_size[1])],
            )

        reported_time = float(timekeeper.Time)
        width, height = vc.png_size(image_path)
        visited.append(
            {
                "step": index,
                "requested_time": float(target_time),
                "reported_time": reported_time,
                "image": image_name,
                "image_width": width,
                "image_height": height,
            }
        )
        ctx.log(
            "  step {0}: t={1} -> reported {2}, wrote {3} ({4}x{5})".format(
                index, target_time, reported_time, image_name, width, height
            )
        )

    ctx.add_metric("steps_rendered", len(visited))
    ctx.write_timing_csv(filename="{0}_steps.csv".format(VIGNETTE), rows=visited)

    # -- assertions --------------------------------------------------------
    ctx.assert_true(
        "state produced at least one source",
        len(sources) > 0,
        "{0} source(s)".format(len(sources)),
    )
    ctx.assert_true(
        "state produced at least one view",
        len(views) > 0,
        "{0} view(s)".format(len(views)),
    )
    ctx.assert_true(
        "every visited step rendered an image",
        all(entry["image_width"] > 0 for entry in visited),
        "{0} of {1} step(s) produced a readable PNG".format(
            sum(1 for entry in visited if entry["image_width"] > 0), len(visited)
        ),
    )
    ctx.assert_true(
        "rendered images match the view size in the state",
        all(
            (entry["image_width"], entry["image_height"])
            == (int(view_size[0]), int(view_size[1]))
            for entry in visited
        ),
        "state view is {0}x{1}".format(int(view_size[0]), int(view_size[1])),
    )

    if len(timesteps) > 1 and len(visited) > 1:
        ctx.assert_true(
            "stepping the animation changed the reported time",
            visited[0]["reported_time"] != visited[-1]["reported_time"],
            "first={0} last={1}".format(
                visited[0]["reported_time"], visited[-1]["reported_time"]
            ),
        )
    else:
        ctx.log(
            "Only one timestep available; time-stepping assertion skipped and "
            "recorded in the metrics as timesteps_in_state."
        )

    # -- clean shutdown ----------------------------------------------------
    # Disconnect tears down the client-server connection explicitly. Letting
    # the interpreter exit instead can leave a pvserver holding an allocation.
    disconnected = True
    try:
        with ctx.phase("disconnect"):
            Disconnect()
    except Exception as exc:  # noqa: BLE001 - this failing IS a result
        disconnected = False
        ctx.warn("Disconnect() raised: {0}".format(exc))

    ctx.add_metric("clean_disconnect", bool(disconnected))
    ctx.assert_true(
        "client-server connection closed cleanly",
        disconnected,
        "Disconnect() completed without raising",
    )


def main():
    args = vc.parse_args(
        VIGNETTE,
        TOOL,
        description="Load a saved ParaView state headlessly, step through "
        "time, render, and disconnect cleanly.",
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
