#
# Visualization Vignettes
#
# vignette_common.py
#
# Shared, stdlib-only support library for every ParaView and VisIt vignette.
#
# This module is imported by scripts running under three different Python
# interpreters -- pvbatch's, VisIt's CLI, and the plain system python3 that
# drives the harness -- so it uses nothing outside the standard library and
# targets Python 3.6+. It must never import paraview or visit modules at
# import time.
#
# WHAT IT PROVIDES
#
#   parse_args()        One CLI contract shared by all vignettes, so the
#                       harness can drive any of them the same way and a
#                       developer can run any of them by hand the same way.
#
#   VignetteContext     Output directories, dataset resolution, logging,
#                       timing, deterministic metrics, and assertions --
#                       written out as a structured results JSON that the
#                       harness compares numerically against a baseline.
#
#   visit_engine_args() Correct compute-engine launch arguments for VisIt,
#                       derived from named CLI flags rather than positional
#                       sys.argv indices.
#
# WHY THE COMPUTE-ENGINE HELPER EXISTS
#
# The original VisIt vignettes selected a machine with `sys.argv[4]`, but the
# Shaheen submission scripts pass five positional arguments, so argv[4] held
# the walltime string and neither branch ever matched. OpenComputeEngine was
# silently skipped and every Shaheen run executed serially on one core while
# reporting success. Named flags remove the whole class of bug.
#
# Author: James Kress, <james@jameskress.com>
#
from __future__ import print_function

import argparse
import errno
import json
import os
import platform
import socket
import sys
import time


SCHEMA_VERSION = 1

# Datasets shipped in the repository, plus the ones produced by
# data/make_topology_datasets.py. Keyed by a short logical name so a vignette
# never hard-codes a relative path.
DATASET_KEYS = {
    "varying_series": "varying_data",
    "varying_first": os.path.join("varying_data", "varying00.vtk"),
    "noise_silo": "noise.silo",
    "topology_dir": "topologies",
    "tetra": os.path.join("topologies", "tetra_unstructured.vtu"),
    "amr": os.path.join("topologies", "amr_hierarchy.vth"),
    "polydata": os.path.join("topologies", "surface_polydata.vtp"),
    "ragged": os.path.join("topologies", "ragged_multiblock.vtm"),
    "ragged_visit": os.path.join("topologies", "ragged_multidomain.visit"),
    "uniform": os.path.join("topologies", "scalar_field.vti"),
    "topology_manifest": os.path.join("topologies", "topologies_manifest.json"),
}

# The scalar carried by the shipped varying*.vtk series, and by every dataset
# that make_topology_datasets.py writes. Vignettes contour on this name.
SHARED_SCALAR = "temp"
TOPOLOGY_SCALAR = "scalar"


class VignetteError(RuntimeError):
    """Raised for any condition that must fail the vignette."""


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------
def _makedirs(path):
    """mkdir -p that is safe on Python 3.6 and against concurrent ranks."""
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno != errno.EEXIST or not os.path.isdir(path):
            raise
    return path


def png_size(path):
    """(width, height) of a PNG, read from its IHDR chunk.

    Implemented against the file format rather than through Pillow, because
    VisIt's bundled Python does not always ship Pillow and a vignette must be
    able to assert its own output resolution without an optional dependency.

    Returns (0, 0) when the file is missing or is not a PNG.
    """
    try:
        with open(path, "rb") as handle:
            header = handle.read(24)
    except (OSError, IOError):
        return (0, 0)

    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    if header[12:16] != b"IHDR":
        return (0, 0)

    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return (width, height)


def script_directory(script_path=None):
    """Absolute directory holding the running vignette script.

    VisIt's CLI does not always populate __file__ in the way CPython does,
    so callers pass their own __file__ when they have one and this falls
    back to sys.argv[0] when they do not.
    """
    if script_path:
        return os.path.abspath(os.path.dirname(script_path))
    if sys.argv and sys.argv[0]:
        return os.path.abspath(os.path.dirname(sys.argv[0]))
    return os.path.abspath(os.getcwd())


def find_repo_root(start):
    """Walk upward from `start` looking for the repository root.

    Identified by the two vignette suites sitting side by side. Falls back to
    two levels up, which is where a vignette directory sits relative to the
    root, so this still returns something sensible in a partial checkout.
    """
    current = os.path.abspath(start)
    for _ in range(8):
        if os.path.isdir(os.path.join(current, "ParaView_Vignettes")) and os.path.isdir(
            os.path.join(current, "VisIt_Vignettes")
        ):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.path.abspath(os.path.join(start, "..", ".."))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser(name, tool, description=None):
    """The CLI contract every vignette shares.

    Kept deliberately small: anything a vignette needs beyond this is added
    by the caller through the returned parser before parse_args() runs.
    """
    parser = argparse.ArgumentParser(
        prog=name,
        description=description or "{0} vignette: {1}".format(tool, name),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    io_group = parser.add_argument_group("input and output")
    io_group.add_argument(
        "--data-dir",
        default=None,
        help="Directory holding the static datasets. Defaults to $VV_DATA_DIR, "
        "then <repo>/data.",
    )
    io_group.add_argument(
        "--output-dir",
        default=None,
        help="Where rendered images and extracts are written. "
        "Defaults to <script-dir>/output.",
    )
    io_group.add_argument(
        "--testing-dir",
        default=None,
        help="Where the structured results JSON is written. "
        "Defaults to <script-dir>/Testing.",
    )

    run_group = parser.add_argument_group("execution")
    run_group.add_argument(
        "--machine",
        choices=("local", "ibex", "shaheen"),
        default="local",
        help="Execution site. Selects the VisIt compute-engine launch profile; "
        "'local' runs in-process and never launches an engine.",
    )
    run_group.add_argument(
        "--ranks", type=int, default=1, help="MPI ranks the vignette should use."
    )
    run_group.add_argument(
        "--nodes", type=int, default=1, help="Compute nodes the vignette should use."
    )
    run_group.add_argument(
        "--partition", default="batch", help="Scheduler partition or queue name."
    )
    run_group.add_argument(
        "--account", default=None, help="Scheduler account to charge, when required."
    )
    run_group.add_argument(
        "--walltime", default="00:20:00", help="Walltime for a launched compute engine."
    )

    img_group = parser.add_argument_group("rendering")
    img_group.add_argument(
        "--image-width", type=int, default=1024, help="Rendered image width in pixels."
    )
    img_group.add_argument(
        "--image-height", type=int, default=1024, help="Rendered image height in pixels."
    )
    img_group.add_argument(
        "--timesteps",
        type=int,
        default=0,
        help="Number of timesteps to process. 0 means every timestep available.",
    )

    parser.add_argument(
        "--verbose", action="store_true", help="Emit per-step progress logging."
    )
    parser.add_argument(
        "--no-metrics",
        "--ephemeral",
        dest="write_metrics",
        action="store_false",
        default=(os.environ.get("VV_NO_METRICS", "") not in ("1", "true", "TRUE", "yes")),
        help="Mark this as a throwaway run. A vignette writes no permanent "
        "history of its own -- its results JSON is a comparison input, not a "
        "history -- so this only records the intent in the log. The harness "
        "flag of the same name is what keeps the run out of "
        "performance_metrics_<machine>.json. Defaults from $VV_NO_METRICS.",
    )
    return parser


def parse_args(name, tool, description=None, extend=None, argv=None):
    """Parse the shared CLI, tolerating host-injected arguments.

    pvbatch and VisIt both forward their own flags into sys.argv, so unknown
    arguments are collected rather than treated as an error. They are logged
    once by VignetteContext so a genuine typo is still visible.
    """
    parser = build_parser(name, tool, description)
    if extend is not None:
        extend(parser)
    args, unknown = parser.parse_known_args(argv)
    args.unknown_args = unknown
    return args


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------
class _Phase(object):
    """Context manager returned by VignetteContext.phase()."""

    def __init__(self, ctx, label, accumulate=False):
        self._ctx = ctx
        self._label = label
        self._accumulate = accumulate
        self._start = 0.0

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        elapsed = time.time() - self._start
        self._ctx.add_timing(self._label, elapsed, accumulate=self._accumulate)
        if exc_type is None:
            self._ctx.debug("{0}: {1:.4f} s".format(self._label, elapsed))
        return False


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------
class VignetteContext(object):
    """Everything a vignette needs that is not ParaView or VisIt itself.

    Metrics and timings are kept apart on purpose. `metrics` holds
    deterministic quantities -- point counts, cell counts, scalar ranges --
    which the harness compares numerically against a baseline with a
    tolerance. `timings` holds wall-clock durations, which are recorded for
    the scaling CSV and never regression-compared, because comparing a wall
    time against a stored baseline produces a test that fails whenever the
    machine is busy.
    """

    def __init__(self, name, tool, args, script_path=None, script_dir=None):
        self.name = name
        self.tool = tool
        self.args = args

        # `script_dir` is the directory itself; `script_path` is a file within
        # it. Vignettes normally pass script_dir, because VisIt's CLI does not
        # reliably populate __file__ and the bootstrap has already resolved
        # the directory by the time the context is built.
        if script_dir:
            self.script_dir = os.path.abspath(script_dir)
        else:
            self.script_dir = script_directory(script_path)
        self.repo_root = find_repo_root(self.script_dir)

        self.data_dir = os.path.abspath(
            args.data_dir
            or os.environ.get("VV_DATA_DIR")
            or os.path.join(self.repo_root, "data")
        )
        self.output_dir = _makedirs(
            os.path.abspath(args.output_dir or os.path.join(self.script_dir, "output"))
        )
        self.testing_dir = _makedirs(
            os.path.abspath(args.testing_dir or os.path.join(self.script_dir, "Testing"))
        )

        # Whether this run is meant to be recorded. Nothing in a vignette
        # appends to the committed performance history, so this changes no
        # behaviour here; it is carried and logged so the whole chain --
        # test_suite.py, run_tests.py, the vignette -- agrees about what kind
        # of run this is when somebody reads the log afterwards.
        self.write_metrics = getattr(args, "write_metrics", True)

        self.metrics = {}
        self.timings = {}
        self.assertions = []
        self.images = []
        self.extracts = []
        # CSVs the vignette wants regression-compared numerically rather than
        # eyeballed. Declared explicitly, and deliberately NOT inferred from
        # self.extracts: write_timing_csv() also lands there, and a wall-clock
        # file compared against a baseline is a test that fails whenever the
        # machine is busy.
        self.numeric_extracts = []
        self.notes = []
        self._start = time.time()

        self.log("=" * 68)
        self.log("{0} vignette: {1}".format(tool, name))
        self.log("=" * 68)
        self.log("script dir : {0}".format(self.script_dir))
        self.log("repo root  : {0}".format(self.repo_root))
        self.log("data dir   : {0}".format(self.data_dir))
        self.log("output dir : {0}".format(self.output_dir))
        self.log("testing dir: {0}".format(self.testing_dir))
        self.log(
            "machine    : {0}  nodes={1} ranks={2}".format(
                args.machine, args.nodes, args.ranks
            )
        )
        self.log("host       : {0} ({1})".format(socket.gethostname(), platform.system()))
        if not self.write_metrics:
            self.log("history    : suppressed (--no-metrics)")
        if getattr(args, "unknown_args", None):
            self.log("passthrough args ignored: {0}".format(" ".join(args.unknown_args)))
        self.log("-" * 68)

    # -- logging ---------------------------------------------------------
    def log(self, message):
        print("[{0}] {1}".format(self.name, message))
        sys.stdout.flush()

    def debug(self, message):
        if self.args.verbose:
            self.log(message)

    def warn(self, message):
        print("[{0}] WARNING: {1}".format(self.name, message))
        sys.stdout.flush()
        self.notes.append(message)

    def error(self, message):
        """Report a problem loudly without deciding the exit code here.

        The verdict belongs to an assertion -- assert_true or assert_close --
        so that it lands in the results JSON and is compared like any other.
        This only makes sure the reason is legible in the log next to the
        failure, and is kept in the notes for whoever reads the JSON instead.
        """
        print("[{0}] ERROR: {1}".format(self.name, message))
        sys.stdout.flush()
        self.notes.append("ERROR: " + message)

    # -- datasets --------------------------------------------------------
    def dataset(self, key_or_relpath, required=True):
        """Resolve a dataset path and confirm it exists.

        Accepts either a logical key from DATASET_KEYS or a path relative to
        the data directory. A missing dataset raises with the command that
        produces it, rather than failing later inside a reader with a message
        about a null pointer.
        """
        relative = DATASET_KEYS.get(key_or_relpath, key_or_relpath)
        path = os.path.join(self.data_dir, relative)
        if os.path.exists(path):
            return path
        if not required:
            return None

        hint = "Run data/fetchData.sh to download the shipped datasets."
        if "topologies" in relative:
            hint = (
                "Run:  pvbatch data/make_topology_datasets.py --output-dir "
                "{0}".format(os.path.join(self.data_dir, "topologies"))
            )
        raise VignetteError(
            "Required dataset not found: {0}\n  {1}".format(path, hint)
        )

    def timestep_files(self, limit=None):
        """Sorted absolute paths of the varying*.vtk time series.

        Built by listing the directory rather than by reading varying.visit,
        whose entries are relative to a working directory the harness does not
        guarantee.
        """
        series_dir = self.dataset("varying_series")
        names = sorted(
            f for f in os.listdir(series_dir) if f.lower().endswith(".vtk")
        )
        if not names:
            raise VignetteError("No .vtk timesteps found in {0}".format(series_dir))
        paths = [os.path.join(series_dir, f) for f in names]

        if limit is None:
            limit = getattr(self.args, "timesteps", 0)
        if limit and limit > 0:
            paths = paths[:limit]
        return paths

    def topology_manifest(self):
        """Load the manifest written by data/make_topology_datasets.py.

        The manifest, not the vignette, is the authority on which scalar each
        topology carries and at what value it should be contoured. That keeps
        the vignettes correct even when a source refuses to rename its array
        -- the AMR pulse being the case that actually happens.
        """
        path = self.dataset("topology_manifest")
        with open(path, "r") as handle:
            manifest = json.load(handle)
        self.debug("loaded topology manifest: {0}".format(path))
        return manifest

    # -- output paths ----------------------------------------------------
    def image_path(self, filename):
        path = os.path.join(self.output_dir, filename)
        if filename not in self.images:
            self.images.append(filename)
        return path

    def extract_path(self, filename):
        path = os.path.join(self.output_dir, filename)
        if filename not in self.extracts:
            self.extracts.append(filename)
        return path

    def add_numeric_extract(
        self,
        filename,
        key_columns=None,
        ignore_columns=None,
        rtol=None,
        atol=None,
    ):
        """Declare a CSV in output/ as a numeric regression artifact.

        The harness compares every declared file against the copy in
        Testing/Baseline/ with verify.compare_csv, cell by cell and with a
        tolerance -- not by diffing pixels, and not by requiring bit-identical
        floats. --bless copies the declared files into the baseline directory.

        `key_columns` names the columns that identify a row, so rows are
        matched by identity rather than by position; that matters the moment a
        vignette emits its rows in a different order. `ignore_columns` skips
        columns that legitimately move between runs -- a hostname, a wall
        time -- which is what makes it safe to put timings in the same file as
        the measurements. `rtol`/`atol` override the harness defaults for this
        file, because the right tolerance is a property of the quantity, and
        only the vignette knows what it computed.
        """
        record = {"file": filename}
        if key_columns:
            record["key_columns"] = list(key_columns)
        if ignore_columns:
            record["ignore_columns"] = list(ignore_columns)
        if rtol is not None:
            record["rtol"] = float(rtol)
        if atol is not None:
            record["atol"] = float(atol)

        for existing in self.numeric_extracts:
            if existing.get("file") == filename:
                existing.update(record)
                break
        else:
            self.numeric_extracts.append(record)

        if filename not in self.extracts:
            self.extracts.append(filename)
        self.log("numeric extract declared: {0}".format(filename))
        return os.path.join(self.output_dir, filename)

    # -- results ---------------------------------------------------------
    def phase(self, label, accumulate=False):
        """`with ctx.phase("render"):` records a wall time under that label.

        Pass accumulate=True inside a loop -- over timesteps, say -- to sum
        every iteration into one total rather than keeping only the last.
        """
        return _Phase(self, label, accumulate=accumulate)

    def add_timing(self, label, seconds, accumulate=False):
        value = float(seconds)
        if accumulate:
            value += float(self.timings.get(label, 0.0))
        self.timings[label] = round(value, 6)

    def add_metric(self, key, value):
        """Record a deterministic quantity for numeric baseline comparison."""
        if isinstance(value, bool):
            self.metrics[key] = value
        elif isinstance(value, (int, float)):
            self.metrics[key] = value
        elif isinstance(value, (list, tuple)):
            self.metrics[key] = [
                v if isinstance(v, (int, float, bool)) else str(v) for v in value
            ]
        else:
            self.metrics[key] = str(value)
        self.debug("metric {0} = {1}".format(key, self.metrics[key]))

    def assert_true(self, name, condition, detail=""):
        """Record an assertion. Returns the condition so callers can branch."""
        passed = bool(condition)
        self.assertions.append(
            {"name": name, "passed": passed, "detail": str(detail)}
        )
        self.log(
            "  [{0}] {1}{2}".format(
                "PASS" if passed else "FAIL", name, "  " + str(detail) if detail else ""
            )
        )
        return passed

    def assert_close(self, name, actual, expected, tolerance, detail=""):
        """Assert a float lands within an absolute tolerance."""
        try:
            ok = abs(float(actual) - float(expected)) <= float(tolerance)
        except (TypeError, ValueError):
            ok = False
        note = "actual={0} expected={1} tol={2}".format(actual, expected, tolerance)
        return self.assert_true(name, ok, (detail + " " + note).strip())

    @property
    def failed_assertions(self):
        return [a for a in self.assertions if not a["passed"]]

    # -- serialization ---------------------------------------------------
    def results_filename(self):
        return "{0}_results.json".format(self.name)

    def write_results(self, status="ok", message=""):
        """Write the structured results JSON the harness compares against.

        Written to the Testing/ directory alongside the legacy output.log so
        it sits next to the existing text and image artifacts rather than
        replacing them.
        """
        payload = {
            "schema_version": SCHEMA_VERSION,
            "vignette": self.name,
            "tool": self.tool,
            "status": status,
            "message": message,
            "hostname": socket.gethostname(),
            "platform": platform.system(),
            "machine": self.args.machine,
            "nodes": self.args.nodes,
            "ranks": self.args.ranks,
            "image_size": [self.args.image_width, self.args.image_height],
            "wall_time_s": round(time.time() - self._start, 6),
            "metrics": self.metrics,
            "timings": self.timings,
            "assertions": self.assertions,
            "images": self.images,
            "extracts": self.extracts,
            "numeric_extracts": self.numeric_extracts,
            "notes": self.notes,
        }
        path = os.path.join(self.testing_dir, self.results_filename())
        with open(path, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        self.log("wrote results: {0}".format(path))
        return path

    def write_timing_csv(self, filename=None, rows=None):
        """Write a scaling/timing CSV next to the images.

        `rows` is a list of dicts; when omitted the recorded timings are
        written as a single row. Kept as plain csv text so the file is
        readable without pandas on a login node.
        """
        filename = filename or "{0}_timings.csv".format(self.name)
        path = os.path.join(self.output_dir, filename)

        if rows is None:
            row = {
                "vignette": self.name,
                "tool": self.tool,
                "machine": self.args.machine,
                "nodes": self.args.nodes,
                "ranks": self.args.ranks,
                "hostname": socket.gethostname(),
            }
            row.update(self.timings)
            rows = [row]

        if not rows:
            return None

        columns = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)

        with open(path, "w") as handle:
            handle.write(",".join(columns) + "\n")
            for row in rows:
                handle.write(
                    ",".join(_csv_cell(row.get(col, "")) for col in columns) + "\n"
                )
        self.log("wrote timings: {0}".format(path))
        if filename not in self.extracts:
            self.extracts.append(filename)
        return path

    def assert_baselined_images_present(self, baseline_dir=None):
        """Assert every baselined image was produced by this run.

        Driven from the blessed baseline rather than from whatever the run
        happened to emit, so a vignette that quietly stops writing one of its
        frames fails here instead of passing with fewer images than before.

        A vignette with no image baselines yet -- ex00, or one not yet
        blessed -- records the fact and asserts nothing, which keeps this
        safe to add to existing vignettes.
        """
        baseline_dir = baseline_dir or os.path.join(self.testing_dir, "Baseline")
        if not os.path.isdir(baseline_dir):
            self.log("no baseline directory at {0}; image check skipped".format(
                baseline_dir))
            return True

        suffixes = (".png", ".jpg", ".jpeg")
        baselined = sorted(
            name
            for name in os.listdir(baseline_dir)
            if name.lower().endswith(suffixes)
        )
        if not baselined:
            self.log("no baselined images; image presence check skipped")
            self.add_metric("baselined_images", 0)
            return True

        missing = [
            name
            for name in baselined
            if not os.path.exists(os.path.join(self.output_dir, name))
        ]

        self.add_metric("baselined_images", len(baselined))
        self.add_metric("missing_images", len(missing))

        for name in baselined:
            if name not in self.images:
                self.images.append(name)

        return self.assert_true(
            "every baselined image was produced",
            not missing,
            "missing from {0}: {1}".format(self.output_dir, missing)
            if missing
            else "{0} image(s) present".format(len(baselined)),
        )

    def finish(self):
        """Write results and return the process exit code.

        Any failed assertion makes the whole vignette fail. The harness relies
        on this return value, so a vignette must always end with
        `sys.exit(ctx.finish())` rather than falling off the end.
        """
        failures = self.failed_assertions
        status = "ok" if not failures else "failed"
        message = (
            "" if not failures else "{0} assertion(s) failed".format(len(failures))
        )
        self.write_results(status=status, message=message)

        self.log("-" * 68)
        if failures:
            self.log("RESULT: FAILED ({0} assertion(s))".format(len(failures)))
            for item in failures:
                self.log("  - {0}: {1}".format(item["name"], item["detail"]))
        else:
            self.log(
                "RESULT: PASSED ({0} assertion(s), {1} image(s))".format(
                    len(self.assertions), len(self.images)
                )
            )
        self.log("=" * 68)
        return 1 if failures else 0

    def abort(self, exc):
        """Record a fatal error, write results, and return the exit code."""
        message = "{0}: {1}".format(type(exc).__name__, exc)
        print("[{0}] FATAL: {1}".format(self.name, message), file=sys.stderr)
        sys.stderr.flush()
        self.assertions.append(
            {"name": "vignette completed", "passed": False, "detail": message}
        )
        try:
            self.write_results(status="error", message=message)
        except Exception as write_error:  # pragma: no cover - last-resort path
            print(
                "[{0}] could not write results: {1}".format(self.name, write_error),
                file=sys.stderr,
            )
        return 2


def _csv_cell(value):
    text = str(value)
    if any(ch in text for ch in (",", '"', "\n")):
        return '"' + text.replace('"', '""') + '"'
    return text


# ---------------------------------------------------------------------------
# VisIt compute-engine launch
# ---------------------------------------------------------------------------
def in_slurm_allocation():
    """True when this process is already inside a Slurm allocation.

    Set by Slurm for every job step, so it is true inside a job launched with
    sbatch and inside an salloc shell, and false on a login node.
    """
    return bool(os.environ.get("SLURM_JOB_ID") or os.environ.get("SLURM_JOBID"))


def _slurm_allocation_shape():
    """(nodes, tasks) of the current allocation, or (None, None)."""

    def _as_int(name):
        value = os.environ.get(name)
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    return _as_int("SLURM_NNODES") or _as_int("SLURM_JOB_NUM_NODES"), _as_int(
        "SLURM_NTASKS"
    )


def visit_engine_args(args, extra=None, inside_allocation=None):
    """Build OpenComputeEngine arguments, or None to stay in-process.

    Returns a tuple suitable for `OpenComputeEngine("localhost", <tuple>)`.
    `--machine local` returns None: a local run must not try to reach a
    scheduler, and a serial engine is what a workstation wants anyway.

    `extra` appends site-independent engine flags, such as -hw-accel to ask
    for a hardware-accelerated offscreen context on the engine.

    WHY THERE ARE TWO PROFILES
    --------------------------
    The site's VisIt customlauncher decides whether to take over by asking
    three questions at once::

        def IsRunningOnIbex(self):
            if self.parallelArgs.parallel and \
               self.sectorname().startswith("login") and \
               self.domainname() == "ibex.kaust.edu.sa":

    All three must hold, and the middle one is the decisive one here: the
    KAUST job submitters engage only when VisIt is started **on a login
    node**. That single condition splits every launch this repository makes
    into two cases that need different arguments.

    *Inside an allocation* -- which is where every .sbat script runs, because
    sbatch put us on a compute node -- the custom submitter does not engage.
    Asking for an sbatch launcher there would submit a second job from inside
    the first and wait for it to schedule. The engine must instead be started
    as a job **step** of the allocation we already hold, which is what
    ``-l srun`` does. Partition, account and walltime are deliberately
    omitted: a step inherits all three, and passing them turns into
    ``srun --partition=... --time=...``, which is redundant at best and
    rejected outright when it disagrees with the allocation.

    *On a login node* the custom submitter does engage, and it is an sbatch
    submitter with an srun sublauncher::

        def Executable(self):
            return ["sbatch"]
        ...
        sbatch, sublauncher = self.LauncherAndSubLauncher()
        if sublauncher == "srun":
            mpicmd = self.srun_args(args)

    ``LauncherAndSubLauncher()`` splits the launcher name on "/", so the
    launcher string has to be ``sbatch/srun`` for that branch to be taken --
    a bare ``-l srun`` would run the engine on the login node itself. Here
    partition, account and walltime are what the submitter turns into
    ``--partition=``, ``--account=`` and ``--time=`` on the sbatch line, so
    they are all passed. The account goes through ``-b``, VisIt's bank flag,
    because that is the field the submitter reads::

        if self.parallel.bank != None:
            parcmd = parcmd + ["--account=%s" % self.parallel.bank]

    `inside_allocation` overrides the detection, for testing.
    """
    if args.machine == "local":
        return tuple(extra) if extra else None

    if inside_allocation is None:
        inside_allocation = in_slurm_allocation()

    nodes = max(1, int(args.nodes))
    ranks = max(1, int(args.ranks))

    if inside_allocation:
        # A job step of the allocation we are already holding.
        launch = ["-l", "srun", "-nn", str(nodes), "-np", str(ranks)]
    else:
        # A fresh job, submitted through the site's customlauncher.
        launch = ["-l", "sbatch/srun", "-nn", str(nodes), "-np", str(ranks)]
        default_partition = "workq" if args.machine == "shaheen" else "batch"
        launch += ["-p", args.partition or default_partition]
        if getattr(args, "account", None):
            launch += ["-b", args.account]
        launch += ["-t", args.walltime]

    if extra:
        launch += list(extra)
    return tuple(launch)


def describe_visit_engine_launch(args, inside_allocation=None):
    """One line explaining which engine profile was chosen, and why.

    Written to the log because the two profiles fail in ways that look
    identical from the outside -- a hung OpenComputeEngine -- and knowing
    which one was attempted is most of the diagnosis.
    """
    if args.machine == "local":
        return "machine=local: in-process engine, nothing submitted"

    if inside_allocation is None:
        inside_allocation = in_slurm_allocation()

    if not inside_allocation:
        return (
            "no Slurm allocation detected: submitting the engine with "
            "sbatch/srun, which is the launcher the site customlauncher "
            "expects from a login node"
        )

    job_id = os.environ.get("SLURM_JOB_ID") or os.environ.get("SLURM_JOBID")
    alloc_nodes, alloc_tasks = _slurm_allocation_shape()
    detail = "inside Slurm allocation {0}".format(job_id)
    if alloc_nodes or alloc_tasks:
        detail += " ({0} node(s), {1} task(s))".format(
            alloc_nodes if alloc_nodes is not None else "?",
            alloc_tasks if alloc_tasks is not None else "?",
        )
    return detail + ": starting the engine as a job step with srun"


def check_engine_fits_allocation(args):
    """Warnings for an engine request larger than the allocation holding it.

    srun rejects an oversubscribed step with a message about resources that
    reads like a queue problem rather than a configuration one, so the
    mismatch is worth naming before it happens. Returns a list of strings;
    an empty list means the request fits or there is nothing to compare to.
    """
    if not in_slurm_allocation():
        return []

    alloc_nodes, alloc_tasks = _slurm_allocation_shape()
    warnings = []
    if alloc_nodes is not None and int(args.nodes) > alloc_nodes:
        warnings.append(
            "--nodes {0} exceeds the {1} node(s) in this allocation; raise "
            "#SBATCH --nodes or lower VV_NODES".format(args.nodes, alloc_nodes)
        )
    if alloc_tasks is not None and int(args.ranks) > alloc_tasks:
        warnings.append(
            "--ranks {0} exceeds the {1} task(s) in this allocation; raise "
            "#SBATCH --ntasks-per-node or lower VV_RANKS".format(
                args.ranks, alloc_tasks
            )
        )
    return warnings


def finish_visit_session(ctx, code, close_compute_engine=None, exit_func=None):
    """Shut down a VisIt CLI script with a real process exit status.

    VisIt's CLI does not terminate when a script falls off the end, and a
    lingering client keeps the compute engine -- and therefore its Slurm
    allocation -- alive. Both shutdown paths are attempted and neither is
    allowed to mask the exit code:

      close_compute_engine  VisIt's CloseComputeEngine, passed in so this
                            module never imports the visit package.
      exit_func             VisIt's own exit(), which tears the viewer down
                            cleanly. Falls through to sys.exit if unavailable.
    """
    if close_compute_engine is not None:
        try:
            close_compute_engine()
        except Exception as exc:  # noqa: BLE001 - shutdown must not mask code
            ctx.warn("CloseComputeEngine failed: {0}".format(exc))

    if exit_func is not None:
        try:
            exit_func(code)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            ctx.warn("VisIt exit() failed: {0}".format(exc))

    sys.exit(code)


def open_visit_engine(ctx, open_compute_engine, extra=None):
    """Launch a VisIt compute engine when the site calls for one.

    `open_compute_engine` is VisIt's OpenComputeEngine, passed in so this
    module never imports the visit package. Returns True when an engine was
    launched. `extra` forwards additional engine flags such as -hw-accel.
    """
    engine_args = visit_engine_args(ctx.args, extra=extra)
    if engine_args is None:
        ctx.log("machine=local: running in-process, no compute engine launched")
        return False

    ctx.log(describe_visit_engine_launch(ctx.args))
    for warning in check_engine_fits_allocation(ctx.args):
        ctx.warn(warning)
    ctx.log("launching compute engine: {0}".format(" ".join(engine_args)))
    if not open_compute_engine("localhost", engine_args):
        raise VignetteError(
            "OpenComputeEngine failed for machine={0} nodes={1} ranks={2}".format(
                ctx.args.machine, ctx.args.nodes, ctx.args.ranks
            )
        )
    ctx.log("compute engine running")
    return True
