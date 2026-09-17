#
# Visualization Vignettes
#
# run_tests.py
#
# Launches a single vignette and reports, unambiguously, whether it worked.
#
# WHAT CHANGED AND WHY
#
#   Exit codes now propagate. The original called subprocess.run() without
#   checking the return code, so a segfaulting vignette and a successful one
#   were indistinguishable to the harness -- both were recorded as a run with
#   a timing. Every launch now writes Testing/run_result.json carrying the
#   return code, the command, the duration, and whether it timed out, and
#   this script exits non-zero when the vignette did.
#
#   Rank count is a parameter. ParaView was hard-wired to `-np 1`, so the
#   parallel path -- the entire point of an HPC visualization repository --
#   had no coverage at all. --ranks now flows through to mpirun/srun for
#   ParaView, and through to OpenComputeEngine for VisIt.
#
#   Nothing runs unguarded. A missing visit or pvbatch binary is reported as
#   a clear failure instead of calling subprocess.run([None, ...]), and every
#   launch carries a timeout so a hung collective cannot wedge CI forever.
#
#   --no-metrics is honoured and propagated. This script writes no permanent
#   history itself -- run_result.json is scratch, and is cleaned -- but the
#   flag is accepted so a direct `python3 run_tests.py <dir> --no-metrics`
#   behaves like the same flag on test_suite.py: it is recorded in
#   run_result.json, exported as $VV_NO_METRICS, and forwarded to the
#   vignette's own CLI.
#
#   The OpenGL backend is selected the way the site's own launcher selects
#   it. run_pvserver.sbat, the script behind the interactive ParaView
#   sessions on Ibex and Shaheen, exports VTK_DEFAULT_OPENGL_WINDOW according
#   to whether the loaded module is a -mesa or an -egl build. ParaView 6.0+
#   needs that hint, so pvbatch launched from here gets the same treatment
#   from the same evidence.
#
# Author: James Kress, <james@jameskress.com>
#
import argparse
import json
import os
import shutil
import subprocess
import sys
import time


# Helper scripts that live beside a vignette but are not the vignette.
HELPER_SUFFIXES = ("_make_state.py", "_validate.py", "_common.py")
HELPER_PREFIXES = ("make_", "run_", "conftest")

DEFAULT_TIMEOUT_SECONDS = 3600

RUN_RESULT_FILENAME = "run_result.json"


# ---------------------------------------------------------------------------
# Environment probes
# ---------------------------------------------------------------------------
def is_gpu_available():
    """True when nvidia-smi runs successfully on this node."""
    try:
        result = subprocess.run(
            ["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False


def is_ppn_node():
    """True when the hostname marks this as a Shaheen pre/post node."""
    try:
        return "ppn" in os.uname().nodename
    except AttributeError:  # pragma: no cover - non-POSIX
        return False


def find_executable(executable_name, env_var):
    """Locate a tool via its environment variable, then via PATH."""
    executable_path = os.getenv(env_var)
    if executable_path:
        candidate = os.path.join(executable_path, executable_name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which(executable_name)


# ---------------------------------------------------------------------------
# OpenGL backend selection
#
# Mirrors the auto-detect block in the site's run_pvserver.sbat. The module
# names are paraview/<version>-gnu-mesa and paraview/<version>-gnu-egl on Ibex
# and paraview/<version>-mesa / -egl on Shaheen, so a substring test on the
# loaded module name is the same test the site launcher makes.
# ---------------------------------------------------------------------------
OPENGL_WINDOW_BY_VARIANT = {
    "mesa": "vtkOSOpenGLRenderWindow",
    "egl": "vtkEGLRenderWindow",
}


def loaded_paraview_module():
    """The ParaView module currently loaded, or '' if none can be identified.

    $VV_PARAVIEW_MODULE is set by the repository's MODULES.sh. $LOADEDMODULES
    is set by every Lmod and Environment Modules installation, and is the
    fallback for a shell where ParaView was loaded by hand.
    """
    explicit = os.environ.get("VV_PARAVIEW_MODULE")
    if explicit:
        return explicit
    for entry in os.environ.get("LOADEDMODULES", "").split(":"):
        if entry.lower().startswith("paraview"):
            return entry
    return ""


def select_opengl_window(env):
    """Set VTK_DEFAULT_OPENGL_WINDOW from the loaded module, if it is unset.

    An explicit setting in the environment always wins: someone who exported
    it deliberately is telling us something we cannot infer.
    """
    if env.get("VTK_DEFAULT_OPENGL_WINDOW"):
        print(
            "Honouring VTK_DEFAULT_OPENGL_WINDOW={0} from the "
            "environment.".format(env["VTK_DEFAULT_OPENGL_WINDOW"])
        )
        return env["VTK_DEFAULT_OPENGL_WINDOW"]

    module = loaded_paraview_module().lower()
    for variant, window in OPENGL_WINDOW_BY_VARIANT.items():
        if variant in module:
            env["VTK_DEFAULT_OPENGL_WINDOW"] = window
            print(
                "Detected {0} module '{1}': VTK_DEFAULT_OPENGL_WINDOW={2}".format(
                    variant, loaded_paraview_module(), window
                )
            )
            return window

    if module:
        print(
            "ParaView module '{0}' names neither 'mesa' nor 'egl'; leaving "
            "VTK_DEFAULT_OPENGL_WINDOW unset and letting VTK choose.".format(module)
        )
    return None


def default_thread_count():
    """Threads per rank, taken from the allocation when Slurm provides one."""
    for var in ("SLURM_CPUS_PER_TASK", "OMP_NUM_THREADS"):
        value = os.environ.get(var)
        if value and value.isdigit() and int(value) > 0:
            return int(value)
    return max(1, os.cpu_count() or 1)


# ---------------------------------------------------------------------------
# Result recording
# ---------------------------------------------------------------------------
def write_run_result(output_dir, payload):
    """Record how the launch went so test_suite.py can gate on it."""
    path = os.path.join(output_dir, RUN_RESULT_FILENAME)
    try:
        with open(path, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except OSError as exc:
        print("Warning: could not write {0}: {1}".format(path, exc))
    return path


def read_run_result(testing_dir):
    """Read back a previously recorded launch result, or None."""
    path = os.path.join(testing_dir, RUN_RESULT_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as handle:
            return json.load(handle)
    except (ValueError, OSError):
        return None


def _execute(cmd, output_dir, env, timeout):
    """Run a vignette, tee its streams to disk, and report the outcome."""
    print("Executing: {0}".format(" ".join(str(part) for part in cmd)))
    sys.stdout.flush()

    stdout_path = os.path.join(output_dir, "output.log")
    stderr_path = os.path.join(output_dir, "error.log")

    started = time.time()
    timed_out = False
    returncode = None

    try:
        with open(stdout_path, "w") as stdout_file, open(
            stderr_path, "w"
        ) as stderr_file:
            completed = subprocess.run(
                cmd,
                stdout=stdout_file,
                stderr=stderr_file,
                env=env,
                timeout=timeout,
            )
        returncode = completed.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        returncode = 124  # conventional timeout status
        with open(stderr_path, "a") as stderr_file:
            stderr_file.write(
                "\n[run_tests] Vignette exceeded the {0}s timeout and was "
                "killed. A hung collective is a failure, not a skip.\n".format(timeout)
            )
    except (OSError, ValueError) as exc:
        returncode = 127
        with open(stderr_path, "a") as stderr_file:
            stderr_file.write("\n[run_tests] Could not launch: {0}\n".format(exc))

    duration = time.time() - started

    payload = {
        "command": [str(part) for part in cmd],
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_s": round(duration, 6),
        "stdout_log": stdout_path,
        "stderr_log": stderr_path,
        "succeeded": (returncode == 0),
    }
    write_run_result(output_dir, payload)

    if returncode == 0:
        print("Vignette completed successfully in {0:.2f}s".format(duration))
    else:
        print(
            "Vignette FAILED (exit {0}{1}) after {2:.2f}s -- see {3}".format(
                returncode,
                ", timed out" if timed_out else "",
                duration,
                stderr_path,
            )
        )
    return payload


def _launch_failure(output_dir, message):
    """Record a launch that never started as a hard failure."""
    print("Error: {0}".format(message))
    stderr_path = os.path.join(output_dir, "error.log")
    try:
        with open(stderr_path, "a") as stderr_file:
            stderr_file.write("\n[run_tests] {0}\n".format(message))
    except OSError:
        pass
    payload = {
        "command": [],
        "returncode": 127,
        "timed_out": False,
        "duration_s": 0.0,
        "stdout_log": os.path.join(output_dir, "output.log"),
        "stderr_log": stderr_path,
        "succeeded": False,
        "error": message,
    }
    write_run_result(output_dir, payload)
    return payload


# ---------------------------------------------------------------------------
# VisIt
# ---------------------------------------------------------------------------
def run_local_visit(script_path, vignette_args, output_dir, args):
    """Run a VisIt vignette through the CLI.

    VisIt is never wrapped in mpirun here: parallelism is the compute
    engine's job, launched from inside the script via OpenComputeEngine using
    the --ranks/--nodes flags this function forwards.
    """
    visit_exec = find_executable("visit", "VISIT_PATH")
    if not visit_exec:
        return _launch_failure(
            output_dir,
            "VisIt executable not found. Set VISIT_PATH to the directory "
            "containing 'visit', or put it on PATH.",
        )

    cmd = [visit_exec, "-cli", "-nowin", "-s", script_path]
    cmd.extend(vignette_args)

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(args.threads)
    if not args.write_metrics:
        env["VV_NO_METRICS"] = "1"

    return _execute(cmd, output_dir, env, args.timeout)


# ---------------------------------------------------------------------------
# ParaView
# ---------------------------------------------------------------------------
def build_paraview_command(script_path, vignette_args, args):
    """Assemble the pvbatch command line for the current launcher.

    Returns (cmd, error_message). Exactly one of the two is meaningful.
    """
    pvbatch_exec = find_executable("pvbatch", "PARAVIEW_PATH")
    if not pvbatch_exec:
        return None, (
            "pvbatch not found. Set PARAVIEW_PATH to the directory containing "
            "'pvbatch', or put it on PATH."
        )

    pv_flags = ["--force-offscreen-rendering"] if args.offscreen else []
    launcher = args.launcher

    if launcher == "auto":
        # A Shaheen pre/post node with a real GPU renders best without a
        # launcher wrapping it, but only when a single rank was requested.
        if args.ranks == 1 and is_ppn_node() and is_gpu_available():
            launcher = "none"
        elif find_executable("mpirun", "MPI_EXEC_PATH"):
            launcher = "mpirun"
        elif find_executable("srun", "SRUN_PATH"):
            launcher = "srun"
        else:
            launcher = "none"

    if launcher == "none":
        if args.ranks > 1:
            return None, (
                "Requested {0} ranks but neither mpirun nor srun is available. "
                "Install an MPI launcher or run with --ranks 1.".format(args.ranks)
            )
        print("Running ParaView with pvbatch directly (no launcher).")
        cmd = [pvbatch_exec] + pv_flags + [script_path]

    elif launcher == "mpirun":
        mpi_exec = find_executable("mpirun", "MPI_EXEC_PATH")
        if not mpi_exec:
            return None, "mpirun requested but not found on PATH or $MPI_EXEC_PATH."
        print("Running ParaView with mpirun on {0} rank(s).".format(args.ranks))
        cmd = [
            mpi_exec,
            "-np",
            str(args.ranks),
            "--bind-to",
            "none",
        ]
        # Placement policy copied from the site's run_pvserver.sbat, which
        # maps by ppr:<tasks-per-node>:node. Without it Open MPI packs every
        # rank onto the first node of a multi-node allocation, and a scaling
        # study measures one node no matter how many were requested.
        if args.nodes > 1:
            per_node = -(-args.ranks // args.nodes)  # ceil, so ranks are covered
            cmd += ["--map-by", "ppr:{0}:node".format(per_node)]
        cmd += [pvbatch_exec] + pv_flags + [script_path]

    elif launcher == "srun":
        srun_exec = find_executable("srun", "SRUN_PATH")
        if not srun_exec:
            return None, "srun requested but not found on PATH or $SRUN_PATH."
        print(
            "Running ParaView with srun on {0} rank(s) across {1} node(s).".format(
                args.ranks, args.nodes
            )
        )
        cmd = [
            srun_exec,
            "--hint=nomultithread",
            "--nodes={0}".format(args.nodes),
            "--ntasks={0}".format(args.ranks),
            "--cpus-per-task={0}".format(args.threads),
            "--mem-bind=v,none",
            "--cpu-bind=v,cores",
            pvbatch_exec,
        ] + pv_flags + [script_path]

    else:  # pragma: no cover - argparse constrains the choices
        return None, "Unknown launcher: {0}".format(launcher)

    cmd.extend(vignette_args)
    return cmd, None


def run_local_paraview(script_path, vignette_args, output_dir, args):
    """Run a ParaView vignette through pvbatch."""
    cmd, error = build_paraview_command(script_path, vignette_args, args)
    if error:
        return _launch_failure(output_dir, error)

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(args.threads)
    env["TBB_NUM_THREADS"] = str(args.threads)
    select_opengl_window(env)
    if not args.write_metrics:
        env["VV_NO_METRICS"] = "1"

    return _execute(cmd, output_dir, env, args.timeout)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
def ensure_testing_directory(test_dir):
    """Ensure the 'Testing' directory exists in the vignette directory."""
    output_dir = os.path.join(test_dir, "Testing")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _is_helper(filename):
    if filename.endswith(HELPER_SUFFIXES):
        return True
    return any(filename.startswith(prefix) for prefix in HELPER_PREFIXES)


def find_test_script(test_dir):
    """Locate the vignette script in a vignette directory.

    Prefers <dirname>.py, which is the convention every vignette follows, and
    otherwise takes the single remaining non-helper .py file. The original
    returned whatever os.listdir yielded first, which becomes ambiguous the
    moment a directory holds a state generator or a validator alongside the
    vignette.
    """
    dir_name = os.path.basename(os.path.normpath(test_dir))
    preferred = os.path.join(test_dir, dir_name + ".py")
    if os.path.isfile(preferred):
        return preferred

    candidates = [
        name
        for name in sorted(os.listdir(test_dir))
        if name.endswith(".py") and not _is_helper(name)
    ]

    if len(candidates) == 1:
        return os.path.join(test_dir, candidates[0])
    if not candidates:
        raise FileNotFoundError(
            "No vignette script found in {0}".format(test_dir)
        )
    raise FileNotFoundError(
        "Ambiguous vignette directory {0}: candidates are {1}. Rename the "
        "primary script to {2}.py.".format(test_dir, candidates, dir_name)
    )


def detect_tool(script_path, test_dir):
    """Decide whether a script is a ParaView or a VisIt vignette.

    Keyed off the vignette suite directory rather than a substring of the
    absolute path, so a checkout living under a directory whose name happens
    to contain 'visit' does not send every ParaView vignette to the wrong
    interpreter.
    """
    absolute = os.path.abspath(test_dir)
    if "VisIt_Vignettes" in absolute.split(os.sep):
        return "VisIt"
    if "ParaView_Vignettes" in absolute.split(os.sep):
        return "ParaView"

    name = os.path.basename(script_path).lower()
    if "visit" in name:
        return "VisIt"
    if "pv" in name or "paraview" in name:
        return "ParaView"
    raise ValueError(
        "Cannot determine whether {0} is a ParaView or VisIt vignette. "
        "Pass --tool explicitly.".format(script_path)
    )


def build_vignette_args(args, output_dir):
    """Flags forwarded into the vignette's own CLI (see vignette_common)."""
    forwarded = [
        "--machine",
        args.machine,
        "--ranks",
        str(args.ranks),
        "--nodes",
        str(args.nodes),
        "--partition",
        args.partition,
        "--walltime",
        args.walltime,
        "--testing-dir",
        output_dir,
    ]
    if args.account:
        forwarded += ["--account", args.account]
    if args.data_dir:
        forwarded += ["--data-dir", args.data_dir]
    if args.image_width:
        forwarded += ["--image-width", str(args.image_width)]
    if args.image_height:
        forwarded += ["--image-height", str(args.image_height)]
    if args.timesteps:
        forwarded += ["--timesteps", str(args.timesteps)]
    if args.verbose:
        forwarded.append("--verbose")
    if not args.write_metrics:
        forwarded.append("--no-metrics")
    forwarded.extend(args.vignette_arg)
    return forwarded


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        description="Run one Visualization Vignette and report its exit status.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "test_dir", type=str, help="The vignette directory to run."
    )
    parser.add_argument(
        "--tool",
        choices=("auto", "ParaView", "VisIt"),
        default="auto",
        help="Which application drives the vignette.",
    )
    parser.add_argument(
        "--ranks", type=int, default=1, help="MPI ranks to launch."
    )
    parser.add_argument(
        "--nodes", type=int, default=1, help="Compute nodes to spread ranks across."
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=None,
        help="Threads per rank. Defaults to $SLURM_CPUS_PER_TASK, then the "
        "host CPU count.",
    )
    parser.add_argument(
        "--launcher",
        choices=("auto", "mpirun", "srun", "none"),
        default="auto",
        help="How to launch pvbatch. Ignored for VisIt, which parallelises "
        "through its compute engine instead.",
    )
    parser.add_argument(
        "--machine",
        choices=("local", "ibex", "shaheen"),
        default="local",
        help="Execution site, forwarded to the vignette.",
    )
    parser.add_argument("--partition", default="batch", help="Scheduler partition.")
    parser.add_argument("--account", default=None, help="Scheduler account.")
    parser.add_argument(
        "--walltime", default="00:20:00", help="Walltime for a VisIt compute engine."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Seconds before the vignette is killed and marked failed.",
    )
    parser.add_argument(
        "--offscreen",
        dest="offscreen",
        action="store_true",
        default=True,
        help="Pass --force-offscreen-rendering to pvbatch.",
    )
    parser.add_argument(
        "--no-offscreen",
        dest="offscreen",
        action="store_false",
        help="Do not force offscreen rendering (needed for the Xvfb vignettes).",
    )
    parser.add_argument("--data-dir", default=None, help="Static dataset directory.")
    parser.add_argument("--image-width", type=int, default=None, help="Image width.")
    parser.add_argument("--image-height", type=int, default=None, help="Image height.")
    parser.add_argument(
        "--timesteps", type=int, default=None, help="Timesteps to process."
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Verbose vignette logging."
    )
    parser.add_argument(
        "--no-metrics",
        "--ephemeral",
        dest="write_metrics",
        action="store_false",
        default=True,
        help="Mark this as a throwaway run. Nothing here appends to the "
        "committed performance history in any case, but the flag is recorded "
        "in run_result.json, exported as $VV_NO_METRICS, and forwarded to the "
        "vignette so the whole chain agrees.",
    )
    parser.add_argument(
        "--vignette-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="Extra argument forwarded verbatim to the vignette. Repeatable.",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.threads is None:
        args.threads = default_thread_count()

    test_dir = os.path.abspath(args.test_dir)
    if not os.path.isdir(test_dir):
        print("Error: {0} is not a directory.".format(test_dir))
        return 2

    output_dir = ensure_testing_directory(test_dir)

    try:
        script_path = find_test_script(test_dir)
    except FileNotFoundError as exc:
        _launch_failure(output_dir, str(exc))
        return 2

    tool = args.tool
    if tool == "auto":
        try:
            tool = detect_tool(script_path, test_dir)
        except ValueError as exc:
            _launch_failure(output_dir, str(exc))
            return 2

    vignette_args = build_vignette_args(args, output_dir)

    if not args.write_metrics:
        print("--no-metrics: this run will not be recorded in the history.")

    if tool == "VisIt":
        payload = run_local_visit(script_path, vignette_args, output_dir, args)
    else:
        payload = run_local_paraview(script_path, vignette_args, output_dir, args)

    # Recorded after the fact so test_suite.py can tell an ephemeral run from
    # a recorded one when it reads back run_result.json.
    if not args.write_metrics:
        payload["metrics_suppressed"] = True
        write_run_result(output_dir, payload)

    return 0 if payload.get("succeeded") else 1


if __name__ == "__main__":
    sys.exit(main())
