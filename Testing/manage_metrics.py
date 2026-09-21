#!/usr/bin/env python3
#
# Visualization Vignettes
#
# manage_metrics.py
#
# Inspect and prune the performance metric history files that test_suite.py
# appends to.
#
# WHY THIS EXISTS
#
#   The history is committed to git. Every local run -- including the ad-hoc
#   ones done while debugging a pipeline, on a laptop, or against a
#   half-built ParaView -- used to land in it permanently, and the only way
#   to undo that was to hand-edit a JSON file or throw away the whole file
#   with `git checkout`. Both are worse than they sound: the files are large,
#   several vignettes share a filename pattern, and a partial hand-edit that
#   drops a brace corrupts a history going back to 2024.
#
#   Two things fix that. `test_suite.py --no-metrics` keeps a run out of the
#   history in the first place, and this tool removes records that are
#   already in it.
#
# THE FILE FORMAT, AND WHY IT IS PRESERVED EXACTLY
#
#   A history file is a JSON object whose keys are ISO-8601 timestamps and
#   whose values are metric records:
#
#       {
#           "2024-10-17T16:43:22.668914": {
#               "test_name": "ex00_pvQuery",
#               "execution_time": 1.6044044494628906,
#               ...
#           },
#           ...
#       }
#
#   There is one file per vignette per machine name:
#
#       <suite>/<vignette>/Testing/performance_metrics_<machine>.json
#
#   Every write here goes through a temporary file and os.replace(), is
#   dumped with indent=4, and ends with a trailing newline -- byte-for-byte
#   the shape of the 112 files already committed. Nothing is reordered and no
#   key is rewritten, so a pruned file diffs as deleted lines and nothing
#   else.
#
# THE UNIT OF REMOVAL
#
#   One record is one vignette's result from one run. A single
#   `test_suite.py` invocation writes one record into each vignette's file,
#   so removing "the last record" from every selected file is what undoes one
#   suite run. That is why --remove-latest and --rollback act per file: with
#   no filters, `--rollback 3` removes the last three suite runs.
#
#   Records written from this point on also carry a `run_id` shared by every
#   vignette in one invocation, so --list-runs can group them and
#   --remove-run can delete exactly one suite run even when later runs have
#   been recorded on top of it. Older records have no run_id; they are listed
#   and removed by timestamp as before.
#
# USAGE
#
#   Look before you delete:
#     python3 Testing/manage_metrics.py --list-runs
#     python3 Testing/manage_metrics.py --list-runs --machine-name ibex-cpu
#     python3 Testing/manage_metrics.py --list-runs --vignette ex07_pvScaling
#
#   Then prune:
#     python3 Testing/manage_metrics.py --remove-latest --machine-name my-laptop
#     python3 Testing/manage_metrics.py --rollback 3 --test-type ParaView
#     python3 Testing/manage_metrics.py --remove-run 20260906T101500-3f9c1a
#
#   Add --dry-run to see the exact records that would go, and -y to skip the
#   confirmation prompt in a script.
#
# Author: James Kress, <james@jameskress.com>
#
from __future__ import print_function

import argparse
import json
import os
import re
import sys


HISTORY_GLOB_PREFIX = "performance_metrics_"
HISTORY_SUFFIX = ".json"
HISTORY_RE = re.compile(
    r"^" + re.escape(HISTORY_GLOB_PREFIX) + r"(?P<machine>.+)" + r"\.json$"
)

# Mirrors test_suite.VIGNETTE_DIR_RE. Duplicated rather than imported so this
# tool stays runnable on a login node where pandas -- which test_suite.py
# imports at module scope -- is not installed.
VIGNETTE_DIR_RE = re.compile(r"^ex(\d+)_")

SUITE_DIRS = ("ParaView_Vignettes", "VisIt_Vignettes")

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NOTHING_MATCHED = 3
EXIT_ABORTED = 4


class HistoryFile(object):
    """One performance_metrics_<machine>.json, and the records inside it."""

    def __init__(self, path, suite, vignette, machine):
        self.path = path
        self.suite = suite
        self.vignette = vignette
        self.machine = machine
        self.records = {}
        self.error = None
        self.load()

    # -- io ----------------------------------------------------------------
    def load(self):
        try:
            with open(self.path, "r") as handle:
                data = json.load(handle)
        except ValueError as exc:
            self.error = "not valid JSON ({0})".format(exc)
            self.records = {}
            return
        except (OSError, IOError) as exc:
            self.error = "unreadable ({0})".format(exc)
            self.records = {}
            return

        if not isinstance(data, dict):
            self.error = "top level is {0}, expected an object".format(
                type(data).__name__
            )
            self.records = {}
            return

        self.records = data

    def save(self):
        """Rewrite the file in the committed format: indent=4, trailing \\n.

        Written to a temporary file and renamed, so an interrupted run leaves
        the original history intact rather than a truncated one.
        """
        temp_path = self.path + ".tmp"
        with open(temp_path, "w") as handle:
            json.dump(self.records, handle, indent=4)
            handle.write("\n")
        os.replace(temp_path, self.path)

    # -- ordering ----------------------------------------------------------
    def ordered_keys(self):
        """Timestamps oldest first.

        ISO-8601 timestamps sort correctly as strings, which is why sorting
        does not need to parse them -- and why it still works for the handful
        of historical keys that carry no microseconds.
        """
        return sorted(self.records.keys())

    def newest_keys(self, count):
        keys = self.ordered_keys()
        if count <= 0:
            return []
        return keys[-count:]

    def keys_for_run(self, run_id):
        return [
            key
            for key in self.ordered_keys()
            if _record_run_id(self.records[key]) == run_id
        ]

    # -- description -------------------------------------------------------
    def label(self):
        if self.vignette:
            return "{0}/{1} [{2}]".format(self.suite, self.vignette, self.machine)
        return "{0} [{1}]".format(self.suite or "Testing", self.machine)

    def relative_path(self, root):
        """A short path for display, or the absolute one if that is shorter.

        --file can name a history outside the repository, where a relative
        path is a chain of '..' segments that is longer and harder to read
        than the absolute path it stands for.
        """
        try:
            relative = os.path.relpath(self.path, root)
        except ValueError:  # pragma: no cover - different drives on Windows
            return self.path
        if relative.startswith(".." + os.sep) or relative == "..":
            return self.path
        return relative


# ---------------------------------------------------------------------------
# Record accessors
#
# Records from before the metrics rewrite are missing most of these keys. Each
# accessor degrades to a placeholder rather than raising, because a tool whose
# job is to clean up a messy history must be able to read a messy history.
# ---------------------------------------------------------------------------
def _record_run_id(record):
    if isinstance(record, dict):
        value = record.get("run_id")
        if value:
            return str(value)
    return None


def _record_test_name(record):
    if isinstance(record, dict):
        return str(record.get("test_name") or "-")
    return "-"


def _record_status(record):
    """A short verdict for the listing.

    'ok'/'FAILED' come from the recorded subprocess exit status, which older
    records do not carry -- those show 'unknown', not a guess.
    """
    if not isinstance(record, dict):
        return "unknown"
    if record.get("timed_out"):
        return "TIMEOUT"
    if "run_succeeded" in record:
        return "ok" if record["run_succeeded"] else "FAILED"
    if "returncode" in record and record["returncode"] is not None:
        return "ok" if record["returncode"] == 0 else "FAILED"
    return "unknown"


def _record_seconds(record):
    if not isinstance(record, dict):
        return None
    value = record.get("execution_time")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _record_schema(record):
    if isinstance(record, dict):
        value = record.get("metrics_schema")
        if value is not None:
            return str(value)
    return "1(pre)"


def _format_seconds(seconds):
    if seconds is None:
        return "     -"
    return "{0:6.2f}".format(seconds)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
def repo_root_default():
    """The repository root, inferred from this file's location."""
    return os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )


def _classify(path, root):
    """Return (suite, vignette, machine) for a history file path."""
    name = os.path.basename(path)
    match = HISTORY_RE.match(name)
    machine = match.group("machine") if match else name

    parts = os.path.normpath(os.path.abspath(path)).split(os.sep)
    suite = None
    vignette = None
    for index, part in enumerate(parts):
        if part in SUITE_DIRS:
            suite = part
            if index + 1 < len(parts) and VIGNETTE_DIR_RE.match(parts[index + 1]):
                vignette = parts[index + 1]
            break
    return suite, vignette, machine


def discover_history_files(root, explicit_files=None):
    """Find every history file under `root`, or use the explicit list."""
    paths = []

    if explicit_files:
        for candidate in explicit_files:
            path = os.path.abspath(candidate)
            if not os.path.isfile(path):
                print("Warning: no such history file: {0}".format(candidate))
                continue
            paths.append(path)
    else:
        search_roots = [os.path.join(root, suite) for suite in SUITE_DIRS]
        search_roots.append(os.path.join(root, "Testing"))
        for search_root in search_roots:
            if not os.path.isdir(search_root):
                continue
            for dirpath, _dirnames, filenames in os.walk(search_root):
                for filename in sorted(filenames):
                    if filename.startswith(HISTORY_GLOB_PREFIX) and filename.endswith(
                        HISTORY_SUFFIX
                    ):
                        paths.append(os.path.join(dirpath, filename))

    files = []
    for path in sorted(set(paths)):
        suite, vignette, machine = _classify(path, root)
        files.append(HistoryFile(path, suite, vignette, machine))
    return files


def filter_history_files(files, args):
    """Apply the --machine-name / --test-type / --vignette filters."""
    selected = []
    for history in files:
        if args.machine_name and history.machine != args.machine_name:
            continue
        if args.test_type:
            wanted = args.test_type + "_Vignettes"
            if history.suite != wanted:
                continue
        if args.vignette and history.vignette != args.vignette:
            continue
        selected.append(history)
    return selected


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------
def list_detail(history, root, limit=None):
    """Per-record table for one history file, oldest first."""
    keys = history.ordered_keys()
    total = len(keys)
    shown = keys if not limit or limit >= total else keys[-limit:]
    skipped = total - len(shown)

    print("\n{0}".format(history.label()))
    print("  {0}".format(history.relative_path(root)))
    if history.error:
        print("  !! {0}".format(history.error))
        return
    if not total:
        print("  (no records)")
        return
    if skipped:
        print(
            "  ... {0} older record(s) not shown; raise --limit to see them".format(
                skipped
            )
        )

    print(
        "  {0:>4}  {1:<26}  {2:<8}  {3:>6}  {4:<7}  {5}".format(
            "#", "timestamp", "status", "sec", "schema", "run_id"
        )
    )
    for offset, key in enumerate(shown):
        record = history.records[key]
        index = total - len(shown) + offset + 1
        marker = "  <- most recent" if index == total else ""
        print(
            "  {0:>4}  {1:<26}  {2:<8}  {3}  {4:<7}  {5}{6}".format(
                index,
                key[:26],
                _record_status(record),
                _format_seconds(_record_seconds(record)),
                _record_schema(record),
                _record_run_id(record) or "-",
                marker,
            )
        )
    print("  {0} record(s). --remove-latest deletes #{1}.".format(total, total))


def list_summary(files, root):
    """One row per history file: how many records, and how recent."""
    print(
        "\n{0:<44}  {1:<20}  {2:>5}  {3:<26}".format(
            "vignette", "machine", "runs", "most recent"
        )
    )
    print("-" * 100)
    total_records = 0
    for history in files:
        keys = history.ordered_keys()
        total_records += len(keys)
        newest = keys[-1][:26] if keys else "-"
        name = history.vignette or (history.suite or "Testing")
        if history.suite and history.vignette:
            name = "{0}/{1}".format(
                history.suite.replace("_Vignettes", ""), history.vignette
            )
        note = ""
        if history.error:
            note = "  !! {0}".format(history.error)
        print(
            "{0:<44}  {1:<20}  {2:>5}  {3:<26}{4}".format(
                name[:44], history.machine[:20], len(keys), newest, note
            )
        )
    print("-" * 100)
    print("{0} file(s), {1} record(s) total.".format(len(files), total_records))


def list_runs_rollup(files, limit):
    """Group records across files by run_id, newest run first.

    This is the view that answers "what did my last three suite runs look
    like", which is the question that precedes every --rollback.
    """
    runs = {}
    undated = 0
    for history in files:
        for key, record in history.records.items():
            run_id = _record_run_id(record)
            if run_id is None:
                undated += 1
                continue
            entry = runs.setdefault(
                run_id,
                {"first": key, "last": key, "count": 0, "failed": 0, "machines": set()},
            )
            entry["count"] += 1
            entry["machines"].add(history.machine)
            if key < entry["first"]:
                entry["first"] = key
            if key > entry["last"]:
                entry["last"] = key
            if _record_status(record) == "FAILED":
                entry["failed"] += 1

    if not runs:
        if undated:
            print(
                "\nNo run_id-tagged records among the {0} selected. Records "
                "written before this tool existed carry only a timestamp -- "
                "use --list-runs --detail to see them.".format(undated)
            )
        return

    ordered = sorted(runs.items(), key=lambda item: item[1]["last"])
    if limit and len(ordered) > limit:
        ordered = ordered[-limit:]

    print("\nSuite runs (newest last):")
    print(
        "  {0:<26}  {1:<26}  {2:>7}  {3:>7}  {4}".format(
            "run_id", "finished", "records", "failed", "machine(s)"
        )
    )
    for run_id, entry in ordered:
        print(
            "  {0:<26}  {1:<26}  {2:>7}  {3:>7}  {4}".format(
                run_id[:26],
                entry["last"][:26],
                entry["count"],
                entry["failed"],
                ",".join(sorted(entry["machines"]))[:40],
            )
        )
    if undated:
        print(
            "  ({0} older record(s) carry no run_id and are not grouped "
            "here.)".format(undated)
        )


def emit_json(files, root):
    """Machine-readable listing, for scripts and for CI summaries."""
    payload = []
    for history in files:
        payload.append(
            {
                "path": history.relative_path(root),
                "suite": history.suite,
                "vignette": history.vignette,
                "machine": history.machine,
                "error": history.error,
                "records": [
                    {
                        "timestamp": key,
                        "test_name": _record_test_name(history.records[key]),
                        "status": _record_status(history.records[key]),
                        "execution_time": _record_seconds(history.records[key]),
                        "metrics_schema": _record_schema(history.records[key]),
                        "run_id": _record_run_id(history.records[key]),
                    }
                    for key in history.ordered_keys()
                ],
            }
        )
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Removal
# ---------------------------------------------------------------------------
def plan_removals(files, args):
    """Decide which keys go from which file. Returns [(HistoryFile, [keys])]."""
    plan = []
    for history in files:
        if history.error:
            print(
                "Skipping {0}: {1}".format(
                    history.relative_path(args.root_directory), history.error
                )
            )
            continue

        if args.remove_run:
            keys = history.keys_for_run(args.remove_run)
        elif args.rollback:
            keys = history.newest_keys(args.rollback)
        else:  # --remove-latest / --pop
            keys = history.newest_keys(1)

        if keys:
            plan.append((history, keys))
    return plan


def describe_plan(plan, root):
    """Print exactly what will be deleted, before anything is."""
    total = 0
    print("\nRecords to remove:")
    for history, keys in plan:
        print("\n  {0}".format(history.relative_path(root)))
        for key in keys:
            record = history.records[key]
            total += 1
            print(
                "    - {0}  {1:<8}  {2}s  run_id={3}".format(
                    key,
                    _record_status(record),
                    _format_seconds(_record_seconds(record)).strip(),
                    _record_run_id(record) or "-",
                )
            )
        remaining = len(history.records) - len(keys)
        print("    ({0} record(s) would remain)".format(remaining))
    print("\n{0} record(s) across {1} file(s).".format(total, len(plan)))
    return total


def confirm(total, files_touched):
    """Ask before deleting, unless stdout is not a terminal."""
    prompt = "\nRemove {0} record(s) from {1} history file(s)? " "[y/N] ".format(
        total, files_touched
    )
    try:
        answer = input(prompt)
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def apply_plan(plan, root):
    """Delete the planned keys and rewrite each file."""
    removed = 0
    for history, keys in plan:
        for key in keys:
            del history.records[key]
            removed += 1
        history.save()
        print(
            "  updated {0} ({1} record(s) left)".format(
                history.relative_path(root), len(history.records)
            )
        )
    return removed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        prog="manage_metrics.py",
        description=(
            "Inspect and prune the committed performance metric history. "
            "One record is one vignette's result from one run; a suite run "
            "writes one record per vignette, so removing the newest record "
            "from every file undoes one suite run."
        ),
        epilog=(
            "Examples:\n"
            "  manage_metrics.py --list-runs\n"
            "  manage_metrics.py --list-runs --detail --vignette ex07_pvScaling\n"
            "  manage_metrics.py --remove-latest --machine-name my-laptop\n"
            "  manage_metrics.py --rollback 3 --test-type ParaView --dry-run\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "root_directory",
        nargs="?",
        default=None,
        help="Repository root. Defaults to the parent of this script's "
        "directory, so the tool works from anywhere.",
    )

    action = parser.add_argument_group("actions (choose exactly one)")
    action.add_argument(
        "--list-runs",
        action="store_true",
        help="Show the recorded runs without changing anything.",
    )
    action.add_argument(
        "--remove-latest",
        "--pop",
        dest="remove_latest",
        action="store_true",
        help="Remove the single most recent record from each selected file.",
    )
    action.add_argument(
        "--rollback",
        type=int,
        metavar="N",
        default=None,
        help="Remove the most recent N records from each selected file.",
    )
    action.add_argument(
        "--remove-run",
        metavar="RUN_ID",
        default=None,
        help="Remove every record tagged with this run_id, wherever it "
        "appears. Precise even when newer runs were recorded on top.",
    )

    selection = parser.add_argument_group("selection")
    selection.add_argument(
        "--machine-name",
        "--machine_name",
        dest="machine_name",
        default=None,
        help="Only touch histories recorded under this machine name -- the "
        "value passed to test_suite.py --machine_name.",
    )
    selection.add_argument(
        "--test-type",
        "--test_type",
        dest="test_type",
        choices=("ParaView", "VisIt"),
        default=None,
        help="Only touch one suite's histories.",
    )
    selection.add_argument(
        "--vignette",
        default=None,
        help="Only touch one vignette's history, e.g. ex07_pvScaling.",
    )
    selection.add_argument(
        "--file",
        action="append",
        default=[],
        metavar="PATH",
        help="Operate on this history file explicitly. Repeatable, and "
        "bypasses discovery entirely.",
    )

    output = parser.add_argument_group("output and safety")
    output.add_argument(
        "--detail",
        action="store_true",
        help="With --list-runs, print every record rather than a per-file "
        "summary. Implied when a single file is selected.",
    )
    output.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum records shown per file by --list-runs --detail.",
    )
    output.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="With --list-runs, emit JSON instead of a table.",
    )
    output.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed and exit without writing.",
    )
    output.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt. Required when stdin is not a "
        "terminal, so an unattended script cannot delete history by accident.",
    )
    return parser


def validate(args, parser):
    """Reject argument combinations that have no single meaning."""
    chosen = [
        bool(args.list_runs),
        bool(args.remove_latest),
        args.rollback is not None,
        bool(args.remove_run),
    ]
    if sum(1 for flag in chosen if flag) != 1:
        parser.error(
            "choose exactly one of --list-runs, --remove-latest/--pop, "
            "--rollback N, --remove-run RUN_ID"
        )

    if args.rollback is not None and args.rollback < 1:
        parser.error("--rollback needs a positive count")

    if args.limit < 1:
        parser.error("--limit needs a positive count")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    validate(args, parser)

    args.root_directory = os.path.abspath(args.root_directory or repo_root_default())

    files = discover_history_files(args.root_directory, args.file)
    if not files:
        print(
            "No performance history files found under {0}.".format(args.root_directory)
        )
        return EXIT_NOTHING_MATCHED

    files = filter_history_files(files, args)
    if not files:
        print("No history files matched the given filters.")
        return EXIT_NOTHING_MATCHED

    # -- listing -----------------------------------------------------------
    if args.list_runs:
        if args.as_json:
            emit_json(files, args.root_directory)
            return EXIT_OK
        if args.detail or len(files) == 1:
            for history in files:
                list_detail(history, args.root_directory, limit=args.limit)
        else:
            list_summary(files, args.root_directory)
            list_runs_rollup(files, limit=args.limit)
            print(
                "\nAdd --detail (optionally with --vignette or --machine-name) "
                "to see individual record indices."
            )
        return EXIT_OK

    # -- removal -----------------------------------------------------------
    plan = plan_removals(files, args)
    if not plan:
        if args.remove_run:
            print(
                "No records carry run_id {0} in the selected files.".format(
                    args.remove_run
                )
            )
        else:
            print("Nothing to remove: the selected history files are empty.")
        return EXIT_NOTHING_MATCHED

    total = describe_plan(plan, args.root_directory)

    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return EXIT_OK

    if not args.yes:
        if not sys.stdin.isatty():
            print(
                "\nRefusing to delete without confirmation. Re-run with --yes, "
                "or with --dry-run to inspect the plan."
            )
            return EXIT_ABORTED
        if not confirm(total, len(plan)):
            print("Aborted. Nothing was written.")
            return EXIT_ABORTED

    print("")
    removed = apply_plan(plan, args.root_directory)
    print(
        "\nRemoved {0} record(s). The history files are tracked in git -- "
        "`git diff` shows exactly what went, and `git checkout -- <path>` "
        "puts it back.".format(removed)
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
