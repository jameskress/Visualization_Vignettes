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
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

try:
    import psutil  # pyright: ignore[reportMissingModuleSource]
except ImportError:  # pragma: no cover - psutil is in the documented venv
    psutil = None

from node_telemetry import NodeTelemetry  # noqa: E402 - beside this file


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
    # Presence, not truthiness. CUDA_VISIBLE_DEVICES="" is the conventional
    # way to hide every device, and an empty string is falsy, so testing the
    # value overrode exactly the caller who was being most explicit.
    if "CUDA_VISIBLE_DEVICES" in env:
        print(
            "Honouring CUDA_VISIBLE_DEVICES={0!r} from the environment.".format(
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

    Process CPU time is cumulative, so summing the last value seen for each
    pid recovers the tree's CPU even for processes that exited between
    samples. What a process uses after its last sample is lost, and so is a
    process that starts and ends inside one 0.25s interval. Measured against
    the cgroup's own cpu.stat on a workstation (LOCAL_VALIDATION 4b.15), the
    sum came within 1% on every vignette tried, serial and 4-rank, ParaView
    and VisIt.

    MEMORY IS PSS, NOT RSS

    RSS counts a shared page once per process that maps it, so summing RSS
    over a tree counts the shared libraries once per rank: 3350 MB for a
    4-rank ParaView ex03 whose cgroup held 1878 MB. PSS divides each shared
    page among the processes that share it, so the sum is the tree's real
    footprint (2191 MB there). RSS is still recorded for comparison with
    history, and used when PSS cannot be read.

    I/O, FOR EXPLAINING A SWING (schema 6)

    The same walk reads each process's /proc/<pid>/io, cumulative like CPU
    time. read_bytes and write_bytes are what reached storage, so a run that
    found its input in the page cache reads far less than one that did not,
    and that difference is often the whole of a time swing on the
    workstation. rchar and wchar count every read and write call, cached or
    not. One more /proc read per process per sample.

    Unlike CPU time, the kernel adds a reaped child's I/O into its parent's
    counters (wait_task_zombie), so summing the last reading of every pid
    counts a child twice: a test that wrote 100 MB and ran a child writing
    50 MB summed to 200 MB. Each sample therefore sums the readings it took
    in one walk, root first and every parent before its children: the root
    already holds every descendant it has reaped, and a live descendant
    holds what it has done so far. A descendant reaped after its parent was
    read and before its own read is missed by that sample, and none can be
    counted twice, so each sample's sum is a lower bound of the true total.
    The run's figure is the largest sum any sample saw. It misses what the
    tree did after the last sample, as CPU time does, and an orphan's I/O
    after it left the tree.

    Context switches are not recorded: /proc/<pid>/status counts only the
    main thread's, so they undercount every multithreaded renderer. The
    largest number of processes and threads seen at once is recorded.
    """

    INTERVAL_S = 0.25

    def __init__(self, pid):
        self.pid = pid
        self.peak_bytes = 0
        self.peak_pss_bytes = 0
        self._pss_ok = True
        self._cpu_by_pid = {}
        # The largest one-walk I/O sum seen, and this walk's running sum.
        self._io_best = None
        self._io_now = None
        # Set when a live process's I/O could not be read (permissions,
        # platform): the total would then be missing a part, so it is None.
        self._io_unreadable = False
        self.peak_processes = 0
        self.peak_threads = 0
        self._threads_now = 0
        self._stop = threading.Event()
        self._thread = None

    def _account(self, process):
        """Record one process's CPU time and return its (RSS, PSS)."""
        rss = process.memory_info().rss
        pss = None
        if self._pss_ok:
            try:
                pss = process.memory_full_info().pss
            except psutil.NoSuchProcess:
                raise
            except Exception:  # noqa: BLE001 - no PSS on this platform
                self._pss_ok = False
        try:
            times = process.cpu_times()
            user, system = float(times.user), float(times.system)
            key = (process.pid, process.create_time())
            # Store the first reading even when it is zero: a process seen at
            # 0.00 s (a short-lived srun client) was measured, and leaving it
            # out made its tree look unsampled.
            if key not in self._cpu_by_pid or user + system > sum(
                self._cpu_by_pid[key]
            ):
                self._cpu_by_pid[key] = (user, system)
        except Exception:  # noqa: BLE001 - CPU times are best effort
            pass
        self._account_io(process)
        return rss, pss

    def _account_io(self, process):
        """Add one process's cumulative I/O to this walk's sum; count threads."""
        try:
            io = process.io_counters()
            reading = (
                int(io.read_bytes),
                int(io.write_bytes),
                int(getattr(io, "read_chars", 0)),
                int(getattr(io, "write_chars", 0)),
            )
        except psutil.NoSuchProcess:
            reading = None  # reaped since the walk listed it: in its parent
        except psutil.AccessDenied:
            reading = None
            # An exiting process of our own user refuses /proc/<pid>/io
            # (EACCES) once its memory is gone; it is, or is about to be, a
            # zombie its parent has not reaped, its I/O is in neither, and
            # this sample is simply low. Any other refusal (another user's
            # process, or a live non-dumpable one) is I/O this harness
            # cannot see, and the total is withheld. See _is_own_exiting.
            if not self._is_own_exiting(process):
                self._io_unreadable = True
        except Exception:  # noqa: BLE001 - no io_counters (macOS) or other
            reading = None
            self._io_unreadable = True
        if reading is not None and self._io_now is not None:
            self._io_now = [a + b for a, b in zip(self._io_now, reading)]
        try:
            self._threads_now += int(process.num_threads())
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _is_own_exiting(process, patience_s=0.05):
        """True when a process that refused /proc/<pid>/io is exiting.

        A process of this user refuses it while it exits (its memory is
        gone), and becomes a zombie or disappears within moments. A live
        process of this user also refuses it when it has made itself
        non-dumpable (PR_SET_DUMPABLE 0), and stays alive. So the refusal
        counts as an exit only for this user's process, and only once it is
        seen to be a zombie or gone within `patience_s`. Only reached on a
        refusal, which is rare, so the wait costs nothing in the usual run.
        """
        try:
            if process.uids().real != os.getuid():
                return False
        except psutil.NoSuchProcess:
            return True
        except Exception:  # noqa: BLE001
            return False
        deadline = time.time() + patience_s
        while True:
            try:
                if process.status() in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
                    return True
            except psutil.NoSuchProcess:
                return True
            except Exception:  # noqa: BLE001
                return False
            if time.time() >= deadline:
                return False
            time.sleep(0.005)

    def _sample_once(self, process):
        self._threads_now = 0
        self._io_now = [0, 0, 0, 0]
        # The root first, then children(recursive=True), which lists every
        # parent before its children: the order the lower bound relies on.
        rss, pss = self._account(process)
        processes = 1
        for child in process.children(recursive=True):
            try:
                child_rss, child_pss = self._account(child)
            except Exception:  # noqa: BLE001 - a child may exit mid-walk
                continue
            processes += 1
            rss += child_rss
            if pss is not None and child_pss is not None:
                pss += child_pss
        self.peak_processes = max(self.peak_processes, processes)
        self.peak_threads = max(self.peak_threads, self._threads_now)
        if self._io_best is None:
            self._io_best = self._io_now
        else:
            self._io_best = [max(a, b) for a, b in zip(self._io_best, self._io_now)]
        return rss, pss

    @property
    def io_totals(self):
        """(read_bytes, write_bytes, rchar, wchar) over the tree, or None.

        None when nothing was sampled, or when a live process's I/O was
        unreadable: a total missing a process would look complete and small.
        """
        if self._io_best is None or self._io_unreadable:
            return None
        return tuple(self._io_best)

    @property
    def cpu_seconds(self):
        """CPU time across the whole tree, or None when nothing was sampled."""
        if not self._cpu_by_pid:
            return None
        return sum(sum(pair) for pair in self._cpu_by_pid.values())

    @property
    def cpu_split(self):
        """(user, system) seconds across the tree, or None."""
        if not self._cpu_by_pid:
            return None
        return (
            sum(pair[0] for pair in self._cpu_by_pid.values()),
            sum(pair[1] for pair in self._cpu_by_pid.values()),
        )

    @property
    def peak_pss(self):
        """Peak summed PSS in bytes, or None when PSS was not readable."""
        if not self._pss_ok or not self.peak_pss_bytes:
            return None
        return self.peak_pss_bytes

    def _run(self):
        try:
            process = psutil.Process(self.pid)
        except Exception:  # noqa: BLE001
            return
        while not self._stop.is_set():
            try:
                rss, pss = self._sample_once(process)
            except Exception:  # noqa: BLE001 - the tree exits under us
                break
            self.peak_bytes = max(self.peak_bytes, rss)
            if pss is not None:
                self.peak_pss_bytes = max(self.peak_pss_bytes, pss)
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


# ---------------------------------------------------------------------------
# Node energy (schema 6)
#
# HPE Cray EX nodes expose cumulative node, CPU and memory energy in
# /sys/cray/pm_counters, readable without privilege and updated about ten
# times a second. The counters cover the whole node, so they describe one
# run only when nothing else can be running there: the job must own every
# CPU of every node it holds. Shaheen's shared and ppn partitions place
# several jobs on one node, and a figure read there would include theirs, so
# none is recorded. The workstation's RAPL counters are root-only and the
# machine is shared, so it records none either.
# ---------------------------------------------------------------------------
PM_COUNTERS_DIR = "/sys/cray/pm_counters"
PM_COUNTER_FILES = {
    "node_joules": "energy",
    "cpu_joules": "cpu_energy",
    "memory_joules": "memory_energy",
}


_SITE_ENERGY = []


def site_energy_interval(config_text=None):
    """The site's JobAcctGatherFrequency energy interval in seconds, or None.

    Read once from `scontrol show config` (or config_text, for tests). None
    when scontrol is missing or the site samples no energy.
    """
    if config_text is None and _SITE_ENERGY:
        return _SITE_ENERGY[0]
    text = config_text
    if text is None:
        scontrol = shutil.which("scontrol")
        try:
            text = (
                subprocess.run(
                    [scontrol, "show", "config"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    universal_newlines=True,
                    timeout=20,
                ).stdout
                if scontrol
                else ""
            )
        except (OSError, subprocess.SubprocessError):
            text = ""
    value = None
    for line in text.splitlines():
        if line.strip().startswith("JobAcctGatherFrequency"):
            match = re.search(r"energy=(\d+)", line)
            if match and int(match.group(1)) > 0:
                value = int(match.group(1))
    if config_text is None:
        _SITE_ENERGY.append(value)
    return value


def job_owns_its_nodes(environ=None, cpus_on_node=None):
    """True when this Slurm job holds every CPU of every node it was given.

    SLURM_JOB_CPUS_PER_NODE reads like "384(x2),192"; each count must equal
    this node's CPU count (the job's nodes are assumed alike, which they are
    within a partition). Outside an allocation the answer is False: an
    unallocated node can be running anything.
    """
    environ = os.environ if environ is None else environ
    cpus_on_node = cpus_on_node or os.cpu_count()
    text = environ.get("SLURM_JOB_CPUS_PER_NODE")
    if not environ.get("SLURM_JOB_ID") or not text or not cpus_on_node:
        return False
    for item in text.split(","):
        count = item.split("(", 1)[0].strip()
        if not count.isdigit() or int(count) != int(cpus_on_node):
            return False
    return True


def read_pm_counters(directory=PM_COUNTERS_DIR):
    """{node_joules, cpu_joules, memory_joules, generation} or None.

    Each file reads "<value> J <timestamp> us". The generation changes when
    the counters are reset, so two readings are subtracted only when their
    generations match.
    """
    if not os.path.isdir(directory):
        return None
    reading = {}
    try:
        for key, name in PM_COUNTER_FILES.items():
            with open(os.path.join(directory, name), "r") as handle:
                reading[key] = int(handle.read().split()[0])
        with open(os.path.join(directory, "generation"), "r") as handle:
            reading["generation"] = handle.read().strip()
    except (OSError, ValueError, IndexError):
        return None
    return reading


def pm_energy(before, after):
    """Energy used between two pm_counters readings, or None."""
    if not before or not after or before["generation"] != after["generation"]:
        return None
    used = {key: after[key] - before[key] for key in PM_COUNTER_FILES}
    if any(value < 0 for value in used.values()):
        return None
    # The node counter unchanged: it was not updated during the run (seen on
    # Shaheen for a 1.8 s vignette, every counter at zero), not a run that
    # used nothing. Without the node figure the parts mean nothing either.
    if not used["node_joules"]:
        return None
    # The CPU and memory counters are parts of the node's. A part larger
    # than the whole is a bad read of that part (Shaheen, 23 and 24 Nov
    # 2026: CPU 6 and 35 times the node); keep the node figure, drop the
    # split.
    # The counters are read one after another, so on a short run the parts
    # may run a little past the node: 2% or 5 J is allowed for that.
    parts = used["cpu_joules"] + used["memory_joules"]
    if parts > used["node_joules"] * 1.02 + 5:
        used["cpu_joules"] = None
        used["memory_joules"] = None
    return used


def _execute(cmd, output_dir, env, timeout, announce_verdict=True):
    """Run a vignette, tee its streams to disk, and report the outcome."""

    stdout_path = os.path.join(output_dir, "output.log")
    stderr_path = os.path.join(output_dir, "error.log")

    # Inside an allocation, ask Slurm to sample every task once a second.
    # Shaheen's default is every 600 s, so a step shorter than ten minutes
    # recorded no memory at all. srun reads this from the environment, which
    # also reaches the srun VisIt runs for its compute engine.
    # Setting it replaces the site's whole JobAcctGatherFrequency, and every
    # interval it leaves out drops to 0 (srun(1)), so the site's energy
    # interval is carried over: a sampled energy plugin would otherwise be
    # switched off for every vignette.
    if os.environ.get("SLURM_JOB_ID") and not env.get("SLURM_ACCTG_FREQ"):
        env = dict(env)
        energy = site_energy_interval()
        env["SLURM_ACCTG_FREQ"] = "task=1" + (
            ",energy={0}".format(energy) if energy else ""
        )

    # Name this run's job steps, so its Slurm accounting can be told from any
    # other step in the allocation by name, not only by time and count.
    # Inside an allocation srun ignores SLURM_JOB_NAME (measured on Shaheen:
    # steps were named after the executable), so the name goes on the
    # command line: on the harness's own srun here, and through
    # VV_SLURM_STEP_NAME to vignette_common, which passes it to VisIt as
    # `-n`, which VisIt's srun launcher turns into `-J`.
    step_name = None
    if os.environ.get("SLURM_JOB_ID"):
        step_name = "vv-" + uuid.uuid4().hex[:12]
        env = dict(env)
        env["VV_SLURM_STEP_NAME"] = step_name
        if os.path.basename(str(cmd[0])) == "srun":
            cmd = [cmd[0], "--job-name=" + step_name] + list(cmd[1:])

    print("Executing: {0}".format(" ".join(str(part) for part in cmd)))
    sys.stdout.flush()

    # Context, not a measurement of the run: how busy the host already was
    # when the vignette started. On the shared workstation this is the first
    # thing to look at when a time swings.
    try:
        load_at_start = round(os.getloadavg()[0], 2)
    except (AttributeError, OSError):
        load_at_start = None
    owns_nodes = job_owns_its_nodes()
    pm_before = read_pm_counters() if owns_nodes else None

    started = time.time()
    timed_out = False
    returncode = None

    sampler = None
    telemetry = None
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
            # VV_NO_NODE_TELEMETRY=1 leaves the node telemetry out, to measure
            # what it costs or to rule it out.
            try:
                if os.environ.get("VV_NO_NODE_TELEMETRY") != "1":
                    telemetry = NodeTelemetry(
                        step_name=step_name,
                        power=owns_nodes,
                        # RAPL covers the whole CPU package: only when this
                        # run has the machine (outside Slurm, or a whole node).
                        rapl=owns_nodes or not os.environ.get("SLURM_JOB_ID"),
                    )
                    try:
                        telemetry.start()
                    except RuntimeError as exc:  # no thread to be had
                        # Optional: the vignette runs and is recorded without
                        # it; the finally below stops whatever did start.
                        print("Node telemetry not started: {0}".format(exc))
                returncode = process.wait(timeout=timeout)
            finally:
                sampler.stop()
                if telemetry is not None:
                    telemetry.stop()
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        sampler.stop()
        if telemetry is not None:
            telemetry.stop()
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

    ended = time.time()
    duration = ended - started
    # And how busy it was by the end: the 1-minute average then covers most
    # of a short vignette's run (its own processes included), so a start and
    # end both far above the vignette's own ranks say the host was shared.
    try:
        load_at_end = round(os.getloadavg()[0], 2)
    except (AttributeError, OSError):
        load_at_end = None
    pm_after = read_pm_counters() if pm_before else None

    payload = {
        "command": [str(part) for part in cmd],
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_s": round(duration, 6),
        "stdout_log": stdout_path,
        "stderr_log": stderr_path,
        "succeeded": (returncode == 0),
        "job_owns_its_nodes": owns_nodes,
    }
    # How many nodes the job has: with one, every srun rank ran here, where
    # node_telemetry.py read the ranks' memory (metrics.STEP_PSS_SCOPE).
    nodes = os.environ.get("SLURM_JOB_NUM_NODES") or os.environ.get("SLURM_NNODES")
    if nodes and nodes.isdigit():
        payload["job_nodes"] = int(nodes)
    if load_at_start is not None:
        payload["load_1m_at_start"] = load_at_start
    if load_at_end is not None:
        payload["load_1m_at_end"] = load_at_end
    if env.get("VTK_DEFAULT_OPENGL_WINDOW"):
        payload["opengl_window"] = env["VTK_DEFAULT_OPENGL_WINDOW"]
    energy = pm_energy(pm_before, pm_after)
    if energy is not None:
        payload["pm_energy"] = energy
    if telemetry is not None:
        payload.update(telemetry.figures())
    # srun hands the ranks to slurmstepd, so they are not in the tree the
    # sampler walked: what it measured was the srun client. VisIt does the
    # same off a workstation, starting its compute engine with srun, and says
    # so in its results JSON. Record that instead of the client's CPU and
    # memory as the vignette's.
    ranks_outside_tree = os.path.basename(str(cmd[0])) == "srun"
    # How many job steps the run made, when that is known: one srun, or one
    # per compute engine the VisIt vignette opened.
    expected_steps = 1 if ranks_outside_tree else None
    if not ranks_outside_tree:
        document = _fresh_results_document(output_dir, started)
        if document is not None:
            ranks_outside_tree = bool(document.get("engine_outside_tree"))
            if document.get("engines_launched"):
                expected_steps = int(document["engines_launched"])
        else:
            # No results JSON (a crash or a timeout), so the vignette never
            # said. Judge from the command: VisIt off a workstation may have
            # had its engine running when it died.
            ranks_outside_tree = _visit_engine_may_be_remote(cmd)
    tree = _tree_sample(sampler)
    if ranks_outside_tree:
        # The local tree is only the launcher side (the srun client, or
        # VisIt's CLI, viewer and mdserver). Keep it under its own name and
        # take the ranks from Slurm's accounting of the steps this run made.
        payload["ranks_outside_tree"] = True
        if tree:
            payload["local_tree"] = tree
        if expected_steps is None:
            # No results JSON, so nobody said how many engines started. sacct
            # can show that an answer is stable but not that it is complete,
            # and a partial list would total to a small number that looks
            # real. Record no figures instead.
            print("Step count unknown (no results JSON); no step accounting")
        else:
            # How many srun steps the vignette says it started: the PSS
            # figure covers the run only if it sampled every one of them.
            payload["srun_steps_expected"] = expected_steps
            asked = time.time()
            steps = slurm_step_usage(
                started, ended, expected=expected_steps, step_name=step_name
            )
            # Waiting for the accounting database is not the vignette's time;
            # metrics.py takes this back out of the execution time.
            payload["accounting_wait_s"] = round(time.time() - asked, 3)
            if steps is not None:
                payload["slurm_steps"] = steps
    elif tree:
        payload.update(tree)
        if duration > 0 and tree.get("tree_cpu_seconds") is not None:
            payload["tree_cpu_percent"] = round(
                100.0 * tree["tree_cpu_seconds"] / duration, 1
            )

    # A vignette that found its input missing declares itself skipped and
    # exits cleanly, so the exit code alone cannot tell the two apart. The
    # VisIt path reads the same field later for its own reasons; doing it
    # here as well means ParaView gets it too, from one place.
    if returncode == 0 and not timed_out:
        document = _fresh_results_document(output_dir, started)
        if document is not None and document.get("status") == "skipped":
            payload["skipped"] = True
            payload["vignette_status"] = "skipped"
            payload["skip_reason"] = document.get("message") or "no reason given"

    write_run_result(output_dir, payload)

    # VisIt's launcher exits 250 (0 on Ibex) pass or fail, so for that path
    # the exit code says nothing and announcing it as a failure here would
    # print "FAILED" on every line of a perfectly green run, immediately
    # above the real verdict. The caller that knows better asks for silence
    # and reports the verdict it derives itself.
    if not announce_verdict:
        pass
    elif payload.get("skipped"):
        print("Vignette SKIPPED: {0}".format(payload["skip_reason"]))
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


def _tree_sample(sampler):
    """What the process-tree sampler measured, as payload fields, or {}."""
    if sampler is None:
        return {}
    sample = {}
    if sampler.peak_bytes:
        sample["peak_rss_bytes"] = int(sampler.peak_bytes)
        sample["peak_rss_mb"] = round(sampler.peak_bytes / 2.0**20, 3)
    if sampler.peak_pss is not None:
        sample["peak_pss_bytes"] = int(sampler.peak_pss)
        sample["peak_pss_mb"] = round(sampler.peak_pss / 2.0**20, 3)
    if sampler.cpu_seconds is not None:
        user, system = sampler.cpu_split
        sample["tree_cpu_seconds"] = round(sampler.cpu_seconds, 3)
        sample["tree_cpu_user_seconds"] = round(user, 3)
        sample["tree_cpu_system_seconds"] = round(system, 3)
    io = sampler.io_totals
    if io is not None:
        for name, value in zip(
            ("io_read_bytes", "io_write_bytes", "io_rchar_bytes", "io_wchar_bytes"),
            io,
        ):
            sample[name] = value
    if sampler.peak_processes:
        sample["peak_processes"] = sampler.peak_processes
        sample["peak_threads"] = sampler.peak_threads
    return sample


# ---------------------------------------------------------------------------
# Slurm step accounting
# ---------------------------------------------------------------------------
# A rank started by srun is a Slurm job step, run by slurmstepd, so nothing
# this harness launched is its parent. Slurm accounts for each step itself:
# TotalCPU is summed from each task's rusage when it exits, so it is exact,
# and TRESUsageInTot mem is the sum over tasks of each task's peak memory.
# Measured on Shaheen ex06 (LOCAL_VALIDATION 4b.15): 4804 CPU seconds and
# 56.9 GiB, where the process tree had seen the srun client's 0.01 s and 19 MB.

# JobIDRaw, not JobID: an array element whose SLURM_JOB_ID is 37 is shown
# by JobID as 36_1, and its steps would never match.
SACCT_FIELDS = (
    "JobIDRaw,Start,End,State,NTasks,TotalCPU,UserCPU,SystemCPU,MaxRSS,"
    "TRESUsageInTot,TRESUsageOutTot,JobName,ConsumedEnergyRaw"
)
_MEMORY_UNITS = {
    "": 1,
    "K": 2**10,
    "M": 2**20,
    "G": 2**30,
    "T": 2**40,
    "P": 2**50,
}


def parse_slurm_duration(text):
    """Seconds in a sacct duration: [DD-][HH:]MM:SS[.mmm]. None if blank."""
    text = (text or "").strip()
    if not text or text in ("INVALID", "Unknown"):
        return None
    # Anything else sacct prints is unreadable, not fatal: one odd value
    # must not lose the run's result, as parse_slurm_size() also treats it.
    try:
        days = 0
        if "-" in text:
            day_text, text = text.split("-", 1)
            days = int(day_text)
        parts = [float(part) for part in text.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        hours, minutes, seconds = parts
    except ValueError:
        return None
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def parse_slurm_size(text):
    """Bytes in a sacct size such as 59617968K or 5.5G. None if blank."""
    text = (text or "").strip()
    if not text:
        return None
    unit = text[-1].upper() if text[-1].isalpha() else ""
    number = text[:-1] if unit else text
    if unit not in _MEMORY_UNITS:
        return None
    try:
        return int(float(number) * _MEMORY_UNITS[unit])
    except ValueError:
        return None


def parse_tres(text):
    """{'cpu': '00:08:06', 'mem': '39022448K', 'fs/disk': '29785...'}."""
    fields = {}
    for item in (text or "").split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            fields[key.strip()] = value.strip()
    return fields


def _energy_field(fields):
    """ConsumedEnergyRaw (added in schema 6) in joules, or None.

    Found by name in SACCT_FIELDS rather than by position, so a field added
    to the list later does not shift it.
    """
    index = SACCT_FIELDS.split(",").index("ConsumedEnergyRaw")
    if len(fields) <= index:
        return None
    text = fields[index].strip()
    if not text.isdigit() or int(text) == 0:
        return None
    return int(text)


def _slurm_time(text):
    try:
        return time.mktime(time.strptime(text, "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return None


# Steps already attributed to an earlier run of this harness process. Slurm
# numbers a job's steps in order and never reuses a number, so a step listed
# here can never belong to a later run.
_CLAIMED_STEPS = set()


def parse_sacct_steps(
    text, job_id, started, ended, slack=2.0, claimed=None, step_name=None
):
    """The numbered steps of `job_id` that ran inside [started, ended].

    Returns (steps, pending, ambiguous). pending is True when a matching step
    has not been finalised in the accounting database yet, so the caller
    should ask again. ambiguous is True when an unclaimed step ended in the
    second this run started: sacct prints whole seconds, so it could be this
    run's or the previous one's, and the caller should not guess. With
    `step_name`, only steps with that name (the JobName column) count: the
    harness names every step a run makes, so another operation's step in
    the same allocation and time window is never taken for this run's.
    """
    claimed = _CLAIMED_STEPS if claimed is None else claimed
    steps = []
    pending = False
    ambiguous = False
    for line in text.splitlines():
        fields = line.split("|")
        if len(fields) < 11:
            continue
        step_id, start, end, state = fields[0], fields[1], fields[2], fields[3]
        prefix, _, number = step_id.partition(".")
        if prefix != str(job_id) or not number.isdigit():
            continue  # the job itself, .batch, .extern
        if step_id in claimed:
            continue  # an earlier run's
        if step_name is not None and (len(fields) < 12 or fields[11] != step_name):
            continue  # another operation's step
        start_s = _slurm_time(start)
        # The slack lets in a step whose start sacct rounded down to just
        # before this run's; nothing lets in one that started after the run
        # ended, which can only be a later operation's.
        if start_s is None or start_s < started - slack or start_s > math.floor(ended):
            continue
        end_s = _slurm_time(end)
        if end_s is None or state.startswith("RUNNING"):
            pending = True
            continue
        # A step that ended before this run started belongs to the run
        # before it (the start slack could otherwise let it in). sacct
        # prints whole seconds, so compare with the start rounded down. A
        # step that started earlier and ended in that very second is not
        # ours; one that started and ended in it could be either.
        started_s = math.floor(started)
        if end_s < started_s or (end_s == started_s and start_s < started_s):
            continue
        if end_s == started_s and step_name is None:
            # Without a name it could be the previous run's; with one, the
            # name already says it is this run's.
            ambiguous = True
            continue
        tres_in = parse_tres(fields[9])
        tres_out = parse_tres(fields[10])
        steps.append(
            {
                "step": step_id,
                "state": state,
                "ntasks": int(fields[4]) if fields[4].isdigit() else None,
                "elapsed_s": end_s - start_s,
                "cpu_seconds": parse_slurm_duration(fields[5]),
                "cpu_user_seconds": parse_slurm_duration(fields[6]),
                "cpu_system_seconds": parse_slurm_duration(fields[7]),
                "max_task_mem_bytes": parse_slurm_size(fields[8]),
                "total_mem_bytes": parse_slurm_size(tres_in.get("mem")),
                "disk_read_bytes": parse_slurm_size(tres_in.get("fs/disk")),
                "disk_write_bytes": parse_slurm_size(tres_out.get("fs/disk")),
                # Joules over the step's nodes, from Slurm's energy plugin
                # (pm_counters on Shaheen). Blank or 0 where no plugin is
                # configured, which is recorded as unknown. Whole-node, so
                # metrics.py uses it only when the job owns its nodes.
                "energy_joules": _energy_field(fields),
            }
        )
    return steps, pending, ambiguous


def slurm_step_usage(
    started,
    ended,
    job_id=None,
    expected=None,
    patience_s=120.0,
    wait_s=5.0,
    step_name=None,
):
    """Accounting for the job steps this run made, or None if unavailable.

    The database lags the step: on Shaheen a finished step showed as still
    running for up to 57 s (it is flushed about once a minute). A step can
    also be missing from one answer and present in the next. When the
    caller knows how many steps the run made (`expected`), this asks until
    exactly that many are finalised, and gives up at once if there are more; otherwise until two answers in a row list the
    same finalised steps, which shows the answer is stable but cannot show
    it is complete. Either way, for up to `patience_s`. None means there is no
    allocation, no sacct, sacct failed, a step whose owner cannot be told
    from its whole-second times, or no stable answer within `patience_s`.
    With `step_name`, only steps of that name count (see parse_sacct_steps).
    With `expected` unset, an empty list means sacct answered twice that no
    step matched. The harness itself always passes `expected`, and records
    nothing when it cannot.
    """
    job_id = job_id or os.environ.get("SLURM_JOB_ID")
    sacct = shutil.which("sacct")
    if not job_id or not sacct:
        return None
    # SLURM_TIME_FORMAT changes how sacct prints Start and End, and a format
    # _slurm_time() cannot read would silently match no step at all.
    env = dict(os.environ)
    env.pop("SLURM_TIME_FORMAT", None)
    steps = []
    previous = None
    deadline = time.time() + patience_s
    while True:
        try:
            text = subprocess.run(
                [sacct, "-j", str(job_id), "-n", "-P", "-o", SACCT_FIELDS],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=60,
                env=env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            print("sacct could not be run ({0}); no step accounting".format(exc))
            return None
        if text.returncode != 0:
            print(
                "sacct exited {0}: {1}; no step accounting".format(
                    text.returncode, text.stderr.strip()[:200]
                )
            )
            return None
        steps, pending, ambiguous = parse_sacct_steps(
            text.stdout, job_id, started, ended, step_name=step_name
        )
        if ambiguous:
            print(
                "a step ended in the second this run started, so it could be "
                "the previous run's; no step accounting"
            )
            return None
        current = [step["step"] for step in steps]
        if expected is not None and len(current) > expected:
            # More steps in the run's window than it made: another step ran
            # in the same allocation, and which rows are this run's cannot
            # be told apart. Totalling them all would over-count.
            print(
                "{0} steps in this run's window but it made {1}; "
                "no step accounting".format(len(current), expected)
            )
            return None
        if not pending and (
            (expected is not None and len(current) == expected)
            or (expected is None and current == previous)
        ):
            _CLAIMED_STEPS.update(current)
            return steps
        previous = None if pending else current
        if time.time() + wait_s > deadline:
            # A step still pending, or two answers that never agreed: what
            # is known is a subset, and a subset totals to a smaller number
            # that looks complete. Report nothing instead.
            print("sacct never gave a stable, finalised answer; no step accounting")
            return None
        time.sleep(wait_s)


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


def _visit_engine_may_be_remote(cmd):
    """True for a VisIt command whose --machine is not local, the case where
    open_visit_engine() starts the engine through Slurm."""
    parts = [str(part) for part in cmd]
    if not parts or not os.path.basename(parts[0]).startswith("visit"):
        return False
    if "--machine" not in parts:
        return False
    index = parts.index("--machine") + 1
    return index < len(parts) and parts[index] != "local"


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
    payload["succeeded"] = status in ("ok", "skipped")
    if status == "skipped":
        payload["skipped"] = True
        payload["skip_reason"] = document.get("message") or "no reason given"
    elif not payload["succeeded"]:
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
    if payload.get("skipped"):
        print("Vignette SKIPPED: {0}".format(payload["skip_reason"]))
    elif payload["succeeded"]:
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

    # One rank never needs a launcher, and under mpirun it is actively harmful: a
    # single-rank vignette ends with os._exit() (exit_vignette, 25 Oct 2026), which
    # skips MPI_Finalize, and OpenMPI's mpirun then reports "exiting improperly" and
    # exit 1 over a vignette that passed. srun does not care, mpirun does. Only a
    # multi-rank run is wrapped.
    if launcher == "mpirun" and args.ranks == 1:
        print("One rank requested: running pvbatch directly rather than under mpirun.")
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
                # a failing rank 0 exits via os._exit() and would otherwise leave
                # the satellite ranks waiting until the walltime
                "--kill-on-bad-exit=1",
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
