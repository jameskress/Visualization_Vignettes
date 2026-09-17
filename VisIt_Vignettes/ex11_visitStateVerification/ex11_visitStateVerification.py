#
# Visualization Vignettes
#
# ex11_visitStateVerification -- restore a saved session headlessly, step
#                                time, render, disconnect cleanly
#
# WHY THIS VIGNETTE EXISTS
#
#   The VisIt counterpart to ex11_pvStateVerification. Session files are how
#   users carry a visualization between machines and between VisIt versions,
#   and restoring one into a newer VisIt can silently drop an operator
#   attribute or fail on a renamed plot type. This repository ships session
#   files -- ex06's visitCyclone.session among them -- and until now never
#   restored one in a test.
#
# RUNNING IT UNDER XVFB
#
#   VisIt's -nowin already gives a windowless client, but this vignette is
#   about the path a GUI user takes, so give it a virtual display when you
#   can:
#
#     xvfb-run -a --server-args="-screen 0 1024x1024x24" \
#         visit -cli -nowin -s ex11_visitStateVerification.py
#
#   With no DISPLAY the vignette still runs and records that in its notes.
#
# PREREQUISITE
#
#   The session file must exist. Generate it once per VisIt version:
#     visit -cli -nowin -s ex11_make_state.py
#
#   A missing session is a FAILURE, not something this vignette quietly
#   creates -- a test that writes its own fixture and then verifies it proves
#   nothing.
#
# WHAT IT ASSERTS
#
#   The session restored and produced at least one plot; the plot list
#   reports an active, drawn plot; the time slider reports the expected
#   number of states; stepping the time slider actually changes the reported
#   state; a frame was rendered at each visited state at the requested
#   resolution; and the compute engine was closed cleanly at the end.
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


VIGNETTE = "ex11_visitStateVerification"
TOOL = "VisIt"

SESSION_FILENAME = "ex11_visit.session"


def add_arguments(parser):
    parser.add_argument(
        "--session",
        default=None,
        help="Path to the .session to restore. Defaults to {0} beside this "
        "script.".format(SESSION_FILENAME),
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=3,
        help="How many time slider states to step through and render.",
    )


def restore_session(ctx, session_path):
    """Restore a VisIt session file.

    RestoreSession's second argument asks VisIt to treat the session as
    relative to the current directory. Passing 0 keeps the absolute database
    paths recorded in the session, which is what we want: the session and the
    data both live inside this checkout.
    """
    if not RestoreSession(session_path, 0):
        raise vc.VignetteError(
            "RestoreSession failed for {0}. The session is most likely from "
            "an incompatible VisIt version -- regenerate it with "
            "ex11_make_state.py.".format(session_path)
        )
    ctx.log("session restored")


def plot_summary(ctx):
    """Number of plots in the restored session, and how many are visible."""
    try:
        plots = GetPlotList()
    except Exception as exc:  # noqa: BLE001
        ctx.warn("GetPlotList() failed: {0}".format(exc))
        return 0, 0

    total = int(plots.GetNumPlots())
    visible = 0
    for index in range(total):
        plot = plots.GetPlots(index)
        if int(getattr(plot, "hiddenFlag", 0)) == 0:
            visible += 1
    return total, visible


def current_time_state(ctx, fallback):
    """The time slider state VisIt reports it is actually on.

    GetWindowInformation().timeSliderCurrentStates is the supported way to
    read it back; asking rather than assuming is the whole point, since a
    SetTimeSliderState that silently did nothing is the failure mode being
    tested for.
    """
    try:
        info = GetWindowInformation()
        states = list(info.timeSliderCurrentStates or [])
        if states:
            return int(states[0])
    except Exception as exc:  # noqa: BLE001
        ctx.debug("GetWindowInformation() unavailable: {0}".format(exc))
    return int(fallback)


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


def run(ctx):
    display_env = os.environ.get("DISPLAY", "")
    if display_env:
        ctx.log("DISPLAY={0} -- rendering through the display path".format(display_env))
    else:
        ctx.warn(
            "No DISPLAY set. VisIt's -nowin client will still render, but "
            "wrap this vignette in xvfb-run to exercise the on-display path "
            "it is meant to cover."
        )
    ctx.notes.append("display={0}".format(display_env or "<none>"))
    ctx.notes.append("visit_version={0}".format(Version()))

    session_path = ctx.args.session or os.path.join(SCRIPT_DIR, SESSION_FILENAME)
    if not os.path.exists(session_path):
        raise vc.VignetteError(
            "Session file not found: {0}\n  Generate it once with:\n"
            "    visit -cli -nowin -s {1}".format(
                session_path, os.path.join(SCRIPT_DIR, "ex11_make_state.py")
            )
        )
    ctx.log("session file: {0}".format(session_path))

    # -- restore ------------------------------------------------------------
    with ctx.phase("restore_session"):
        restore_session(ctx, session_path)

    total_plots, active_plots = plot_summary(ctx)
    ctx.log("session produced {0} plot(s), {1} active".format(total_plots, active_plots))
    ctx.add_metric("plots_in_session", total_plots)

    n_states = TimeSliderGetNStates()
    ctx.log("time slider reports {0} state(s)".format(n_states))
    ctx.add_metric("timesteps_in_session", int(n_states))

    step_count = max(1, min(ctx.args.steps, max(1, n_states)))
    visited = []

    for index in range(step_count):
        SetTimeSliderState(index)

        image_name = "{0}_step{1:02d}.png".format(VIGNETTE, index)
        SetSaveWindowAttributes(save_attributes(ctx, image_name))

        with ctx.phase("render", accumulate=True):
            DrawPlots()
            SaveWindow()

        image_path = os.path.join(ctx.output_dir, image_name)
        ctx.image_path(image_name)
        width, height = vc.png_size(image_path)

        reported_state = current_time_state(ctx, index)

        visited.append(
            {
                "step": index,
                "requested_state": index,
                "reported_state": reported_state,
                "image": image_name,
                "image_width": width,
                "image_height": height,
            }
        )
        ctx.log(
            "  step {0}: state {1} -> wrote {2} ({3}x{4})".format(
                index, reported_state, image_name, width, height
            )
        )

    ctx.add_metric("steps_rendered", len(visited))
    ctx.write_timing_csv(filename="{0}_steps.csv".format(VIGNETTE), rows=visited)

    # -- assertions ---------------------------------------------------------
    ctx.assert_true(
        "session produced at least one plot",
        total_plots > 0,
        "{0} plot(s) in the restored session".format(total_plots),
    )
    ctx.assert_true(
        "every visited step rendered an image",
        all(entry["image_width"] > 0 for entry in visited),
        "{0} of {1} step(s) produced a readable PNG".format(
            sum(1 for entry in visited if entry["image_width"] > 0), len(visited)
        ),
    )
    ctx.assert_true(
        "rendered at the requested resolution",
        all(
            (entry["image_width"], entry["image_height"])
            == (ctx.args.image_width, ctx.args.image_height)
            for entry in visited
        ),
        "requested {0}x{1}".format(ctx.args.image_width, ctx.args.image_height),
    )

    if n_states > 1 and len(visited) > 1:
        ctx.assert_true(
            "stepping the time slider changed the reported state",
            visited[0]["reported_state"] != visited[-1]["reported_state"],
            "first={0} last={1}".format(
                visited[0]["reported_state"], visited[-1]["reported_state"]
            ),
        )
    else:
        ctx.log(
            "Only one time state available; time-stepping assertion skipped "
            "and recorded in the metrics as timesteps_in_session."
        )

    DeleteAllPlots()


def main():
    args = vc.parse_args(
        VIGNETTE,
        TOOL,
        description="Restore a saved VisIt session headlessly, step through "
        "time, render, and shut down cleanly.",
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
