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
import threading
import time

try:
    import psutil  # pyright: ignore[reportMissingModuleSource]
except ImportError:  # pragma: no cover - psutil is in the documented venv
    psutil = None


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


def visible_gpu_count():
    """Number of GPUs nvidia-smi reports, or 0 when it cannot be asked."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "-L"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, OSError):
        return 0
    if result.returncode != 0:
        return 0
    text = result.stdout.decode("utf-8", "replace")
    return sum(1 for line in text.splitlines() if line.startswith("GPU "))


def pin_render_device(env, ranks):
    """Make GPU selection deterministic for a single-rank render job.

    WHY THIS EXISTS

    ex06 produced a 4.67% pixel difference between two consecutive runs on
    the same workstation, with the same ParaView and the same data -- enough
    to fail against a baseline blessed from its own output minutes earlier.
    The difference was confined to the Surface LIC on the terrain. Surface
    LIC in isolation is bit-reproducible here; what is not reproducible is
    which of the two RTX A5000s the driver places the work on. Pinning to a
    single device took the same run-to-run comparison to 0.0079%, well
    inside the 0.1% image tolerance.

    A rendering baseline is only meaningful if the same input renders the
    same way twice, so the device a single-rank job renders on is pinned
    rather than left to the driver. That job was only ever going to use one
    GPU; this decides which one.

    Two deliberate limits:

      * Only when ranks == 1. A multi-rank GPU run wants every device, and
        pinning one would change what is being measured.
      * An explicit CUDA_VISIBLE_DEVICES from the caller always wins, so a
        site that assigns devices itself -- Slurm with --gres=gpu does
        exactly this -- is never overridden.

    Returns the value set, or None when nothing was changed.
    """
    if ranks != 1:
        return None
    if env.get("CUDA_VISIBLE_DEVICES"):
        print(
            "Honouring CUDA_VISIBLE_DEVICES={0} from the environment.".format(
                env["CUDA_VISIBLE_DEVICES"]
            )
        )
        return None

    count = visible_gpu_count()
    if count < 2:
        return None

    env["CUDA_VISIBLE_DEVICES"] = "0"
    print(
        "{0} GPUs visible and one rank requested: pinning "
        "CUDA_VISIBLE_DEVICES=0 so the render is reproducible. Set it "
        "yourself to choose a different device.".format(count)
    )
    return "0"


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


class _PeakRssSampler(object):
    """Sample a process tree's resident set and CPU time while it runs.

    WHY NOT resource.getrusage(RUSAGE_CHILDREN)

    ru_maxrss for children is a high-water mark over every child the calling
    process has EVER reaped, and it never goes down. test_suite.py runs all
    thirteen vignettes from one process, so once ex06 touched 62 GB, ex07
    through ex12 each recorded 61965.6 MB as their peak -- ex06's number,
    written into their committed history and compared against by the
    performance gate. Six of the thirteen memory figures in a full suite run
    were not measurements of anything.

    Sampling the child's own tree gives each vignette its own number. The
    sample interval is coarse on purpose: this measures a multi-second render,
    not a microbenchmark, and the sampler must not compete with it.

    Falls back to reporting nothing when psutil is unavailable, which is
    honest -- gather_metrics then says so rather than substituting a figure
    from a different test.

    THE SAME ARGUMENT APPLIES TO CPU TIME, AND HARDER FOR VisIt

    cpu_usage_percent came from RUSAGE_CHILDREN too, which counts only
    processes this harness reaped itself. For ParaView that is nearly the
    whole story -- pvbatch does the work in the process we launched. For
    VisIt it is not: `visit -cli` starts a viewer, an mdserver and a compute
    engine, and the engine is where every second of render and query time is
    spent. The first VisIt suite run measured ex06 at 13% CPU over 207
    seconds while its engine held 33 GB resident, which is not a number
    anybody should carry to Shaheen and compare against.

    Process CPU time is cumulative, so the maximum ever seen for a pid is its
    final total; summing those maxima recovers the tree's CPU even for
    processes that exited between samples. A process that both starts and
    ends inside one 0.25s interval is missed, which for a suite whose
    shortest vignette is 1.7 seconds is noise.
    """

    INTERVAL_S = 0.25

    def __init__(self, pid):
        self.pid = pid
        self.peak_bytes = 0
        self._cpu_by_pid = {}
        self._stop = threading.Event()
        self._thread = None

    def _account(self, process):
        """Record one process's RSS, and its CPU time if it is higher than
        anything seen for that pid before. Returns the RSS."""
        rss = process.memory_info().rss
        try:
            times = process.cpu_times()
            seconds = float(times.user) + float(times.system)
            key = (process.pid, process.create_time())
            if seconds > self._cpu_by_pid.get(key, 0.0):
                self._cpu_by_pid[key] = seconds
        except Exception:  # noqa: BLE001 - CPU times are best effort
            pass
        return rss

    def _sample_once(self, process):
        total = self._account(process)
        for child in process.children(recursive=True):
            try:
                total += self._account(child)
            except Exception:  # noqa: BLE001 - a child may exit mid-walk
                pass
        return total

    @property
    def cpu_seconds(self):
        """CPU time across the whole tree, or None when nothing was sampled."""
        if not self._cpu_by_pid:
            return None
        return sum(self._cpu_by_pid.values())

    def _run(self):
        try:
            process = psutil.Process(self.pid)
        except Exception:  # noqa: BLE001
            return
        while not self._stop.is_set():
            try:
                self.peak_bytes = max(self.peak_bytes, self._sample_once(process))
            except Exception:  # noqa: BLE001 - the tree exits under us
                break
            self._stop.wait(self.INTERVAL_S)

    def start(self):
        if psutil is None:
            return self
        self._thread = threading.Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        return self.peak_bytes or None


def _execute(cmd, output_dir, env, timeout, announce_verdict=True):
    """Run a vignette, tee its streams to disk, and report the outcome."""
    print("Executing: {0}".format(" ".join(str(part) for part in cmd)))
    sys.stdout.flush()

    stdout_path = os.path.join(output_dir, "output.log")
    stderr_path = os.path.join(output_dir, "error.log")

    started = time.time()
    timed_out = False
    returncode = None

    peak_rss_bytes = None
    tree_cpu_seconds = None
    try:
        with open(stdout_path, "w") as stdout_file, open(
            stderr_path, "w"
        ) as stderr_file:
            process = subprocess.Popen(
                cmd,
                stdout=stdout_file,
                stderr=stderr_file,
                env=env,
            )
            sampler = _PeakRssSampler(process.pid).start()
            try:
                returncode = process.wait(timeout=timeout)
            finally:
                peak_rss_bytes = sampler.stop()
                tree_cpu_seconds = sampler.cpu_seconds
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        peak_rss_bytes = sampler.stop()
        tree_cpu_seconds = sampler.cpu_seconds
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
    if peak_rss_bytes:
        payload["peak_rss_bytes"] = int(peak_rss_bytes)
        payload["peak_rss_mb"] = round(peak_rss_bytes / (1024.0 * 1024.0), 3)
    if tree_cpu_seconds:
        payload["tree_cpu_seconds"] = round(tree_cpu_seconds, 3)
        if duration > 0:
            payload["tree_cpu_percent"] = round(100.0 * tree_cpu_seconds / duration, 1)
    write_run_result(output_dir, payload)

    # VisIt's launcher always exits 250, so for that path the exit code says
    # nothing and announcing it as a failure here would print "FAILED" on
    # every line of a perfectly green run, immediately above the real
    # verdict. The caller that knows better asks for silence and reports the
    # verdict it derives itself.
    if not announce_verdict:
        pass
    elif returncode == 0:
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
# VisIt's CLI launcher does not propagate a script's exit status. Measured on
# 3.4.2: exit(0), exit(1), exit(13), sys.exit(0) and falling off the end of the
# script all produce process exit code 250, with and without -noconfig, with
# and without -quiet, and the launcher is a shell script wrapping `cli` so
# there is nothing to pass through. The code is not merely wrong, it carries
# no information at all.
VISIT_LAUNCHER_EXIT_CODE = 250


def _fresh_results_document(output_dir, started_at):
    """The results JSON a vignette wrote during THIS run, or None.

    Freshness is what makes this a gate rather than a rubber stamp: a run that
    crashed, hung or was killed leaves the previous run's file sitting there,
    and reading it would report the previous run's verdict.
    """
    newest = None
    for name in sorted(os.listdir(output_dir)):
        if not name.endswith("_results.json"):
            continue
        path = os.path.join(output_dir, name)
        try:
            if os.path.getmtime(path) + 1.0 < started_at:
                continue  # left over from an earlier run
            with open(path, "r") as handle:
                document = json.load(handle)
        except (OSError, ValueError):
            continue
        newest = document
    return newest


def _apply_visit_verdict(payload, output_dir, started_at):
    """Decide whether a VisIt vignette passed, without using its exit code.

    The vignette's own results JSON is the verdict. It is written by
    VignetteContext.finish() as the last thing before the process ends, so its
    presence with a fresh mtime means the vignette reached the end, and its
    `status` field says what it concluded.

    This is strictly stronger than what the exit code gave us, which was 250
    for everything -- every VisIt vignette failed gate 1 permanently, pass or
    fail. It is also stronger than trusting the code even if it worked: a
    vignette that dies before writing results is caught here by the absence of
    a fresh file, and one that finishes with failed assertions is caught by
    its status.
    """
    payload["exit_code_is_authoritative"] = False
    payload["visit_launcher_exit_code"] = payload.get("returncode")

    if payload.get("timed_out"):
        payload["verdict_source"] = "timeout"
        payload["succeeded"] = False
        return payload

    document = _fresh_results_document(output_dir, started_at)
    if document is None:
        payload["succeeded"] = False
        payload["verdict_source"] = "missing results JSON"
        payload["error"] = (
            "The vignette wrote no results JSON during this run. VisIt's CLI "
            "always exits {0}, so the exit code cannot be used; the results "
            "file is the verdict, and its absence means the vignette did not "
            "reach the end. See {1}.".format(
                VISIT_LAUNCHER_EXIT_CODE, payload.get("stderr_log")
            )
        )
        return payload

    status = document.get("status", "unknown")
    payload["verdict_source"] = "results JSON status={0}".format(status)
    payload["vignette_status"] = status
    payload["succeeded"] = status == "ok"
    if not payload["succeeded"]:
        payload["error"] = document.get("message") or "vignette reported {0}".format(
            status
        )
    return payload


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

    # -noconfig is not optional for a regression suite. Without it VisIt
    # reads ~/.visit/config on startup, which carries that user's saved
    # annotation, save-window, window-size and colour-table state -- so a
    # blessed baseline becomes partly a function of whose home directory ran
    # it, and ex10 in particular stops measuring colour-map fidelity and
    # starts measuring the developer's preferences. The user running this
    # suite here has a populated ~/.visit with nine custom colour tables in
    # it, so this is not hypothetical.
    cmd = [visit_exec, "-cli", "-nowin", "-noconfig", "-s", script_path]
    cmd.extend(vignette_args)

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(args.threads)
    pin_render_device(env, args.ranks)
    if not args.write_metrics:
        env["VV_NO_METRICS"] = "1"

    started_at = time.time()
    payload = _execute(cmd, output_dir, env, args.timeout, announce_verdict=False)

    # VisIt's exit code is meaningless (see above), so the verdict comes from
    # what the vignette wrote. Re-record it so test_suite.py, which gates on
    # run_result.json, sees the real answer.
    payload = _apply_visit_verdict(payload, output_dir, started_at)
    write_run_result(output_dir, payload)
    if payload["succeeded"]:
        print("Vignette passed ({0}).".format(payload["verdict_source"]))
    else:
        print(
            "Vignette FAILED ({0}) -- VisIt's launcher exit code {1} is not "
            "meaningful and was ignored.".format(
                payload["verdict_source"], payload.get("visit_launcher_exit_code")
            )
        )
    return payload


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
        cmd = (
            [
                srun_exec,
                "--hint=nomultithread",
                "--nodes={0}".format(args.nodes),
                "--ntasks={0}".format(args.ranks),
                "--cpus-per-task={0}".format(args.threads),
                "--mem-bind=v,none",
                "--cpu-bind=v,cores",
                pvbatch_exec,
            ]
            + pv_flags
            + [script_path]
        )

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
    pin_render_device(env, args.ranks)
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
        raise FileNotFoundError("No vignette script found in {0}".format(test_dir))
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
    parser.add_argument("test_dir", type=str, help="The vignette directory to run.")
    parser.add_argument(
        "--tool",
        choices=("auto", "ParaView", "VisIt"),
        default="auto",
        help="Which application drives the vignette.",
    )
    parser.add_argument("--ranks", type=int, default=1, help="MPI ranks to launch.")
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
