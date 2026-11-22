#!/usr/bin/env python3
#
# Visualization Vignettes
#
# check_submission.py -- the checks a pull request of results must pass
#
# A site contributes its results as history files,
# <suite>/<vignette>/Testing/performance_metrics_<configuration>.json, and
# optionally its own image baselines, <suite>/<vignette>/Testing/Baseline/
# <configuration>/. This checks them before they reach the dashboard, which
# would otherwise skip a file it cannot read and publish whatever name it is
# given.
#
# Every history file, always:
#   * it sits in a vignette's Testing/ directory and parses as one JSON
#     object of {ISO-8601 timestamp: record}
#   * every record names the vignette whose directory it is in
#   * its configuration name is a public one: letters, digits, '.', '_'
#     and '-', and not a host name (Testing/dashboard.py, PUBLIC_NAMES)
#
# Records that are new against --base (what a pull request adds):
#   * metrics_schema is at least MIN_COMPARABLE_SCHEMA (Testing/metrics.py)
#   * run_id is set, execution_time is a number, run_succeeded is a boolean
#   * the configuration is not the host name the record was taken on,
#     which is what test_suite.py falls back to without --machine_name
#   * the timestamp is not in the future
#
# Per-site baseline directories must carry public names as well.
#
#   python3 Testing/check_submission.py                       all files
#   python3 Testing/check_submission.py --base origin/master  and new records
#
# Exit 0 when everything passes, 1 with one line per problem otherwise.
# Standard library only.
#
# Author: James Kress, <james@jameskress.com>

import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dashboard import (  # noqa: E402
    PUBLIC_NAMES,
    REPO_ROOT,
    SUITES,
    VIGNETTE_RE,
    public_name,
)
from metrics import MIN_COMPARABLE_SCHEMA  # noqa: E402

PREFIX = "performance_metrics_"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?$")
IMAGE = re.compile(r"\.(png|jpe?g)$", re.IGNORECASE)


def valid_timestamp(text):
    """The record key's shape, and a real date and time (no 30 February)."""
    return parse_timestamp(text) is not None


def parse_timestamp(text):
    """The record key as a datetime, or None. Any number of fraction digits:
    Python before 3.11 parses only 3 or 6, so the fraction is padded to 6."""
    if not TIMESTAMP.match(text):
        return None
    whole, _, fraction = text.partition(".")
    if fraction:
        whole += "." + (fraction + "000000")[:6]
    try:
        return datetime.datetime.fromisoformat(whole)
    except ValueError:
        return None


def name_problem(name):
    """Why `name` cannot be published as a configuration, or None."""
    if not NAME.match(name):
        return "use only letters, digits, '.', '_' and '-'"
    try:
        public_name(name)
    except SystemExit as exc:
        return str(exc)
    return None


def history_files(repo):
    """Every history file in the tree, wherever it is, relative to `repo`.

    The whole tree, not just the vignettes' Testing/ directories: a file
    committed anywhere else is read by nothing, so it is a problem to report,
    not one to miss. Hidden directories and build output are skipped.
    """
    found = []
    for directory, subdirs, files in os.walk(repo):
        subdirs[:] = [
            d for d in subdirs if not d.startswith((".", "_site")) and d != "output"
        ]
        for name in files:
            if name.startswith(PREFIX) and name.endswith(".json"):
                found.append(os.path.relpath(os.path.join(directory, name), repo))
    return sorted(found)


def base_document(repo, base, path):
    """The file's JSON object at `base`; {} when it did not exist there."""
    try:
        text = subprocess.run(
            ["git", "-C", repo, "show", "{0}:{1}".format(base, path)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return {}
    try:
        document = json.loads(text)
    except ValueError:
        return {}
    return document if isinstance(document, dict) else {}


def check_new_record(config, timestamp, record, now):
    problems = []
    schema = record.get("metrics_schema")
    if not isinstance(schema, int) or schema < MIN_COMPARABLE_SCHEMA:
        problems.append(
            "metrics_schema {0!r}: record with the current test_suite.py "
            "(schema {1} or newer)".format(schema, MIN_COMPARABLE_SCHEMA)
        )
    if not isinstance(record.get("run_id"), str) or not record["run_id"]:
        problems.append("no run_id: record with the current test_suite.py")
    elapsed = record.get("execution_time")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)):
        problems.append("execution_time is not a number")
    if not isinstance(record.get("run_succeeded"), bool):
        problems.append("run_succeeded is not true or false")
    node = str((record.get("machine_info") or {}).get("node") or "")
    # A host listed in PUBLIC_NAMES is published under its public name.
    hosts = {node.lower(), node.split(".", 1)[0].lower()}
    if node and config not in PUBLIC_NAMES and config.lower() in hosts:
        problems.append(
            "the configuration is the host name '{0}': pass --machine_name "
            "with a public name".format(node)
        )
    when = parse_timestamp(timestamp)
    if when is not None and when > now + datetime.timedelta(days=1):
        problems.append("timestamp is in the future")
    return problems


def check_file(repo, path, base=None, now=None):
    """[problem, ...] for one history file, each prefixed with where."""
    now = now or datetime.datetime.now()
    parts = path.split(os.sep)
    vignette = parts[-3] if len(parts) >= 4 else ""
    config = os.path.basename(path)[len(PREFIX) : -len(".json")]
    problems = []
    suites = {suite for _tool, suite in SUITES}
    if (
        len(parts) != 4
        or parts[0] not in suites
        or parts[2] != "Testing"
        or not VIGNETTE_RE.match(vignette)
    ):
        problems.append(
            "not in a vignette's Testing/ directory "
            "(<suite>/<vignette>/Testing/), so nothing reads it"
        )
    reason = name_problem(config)
    if reason:
        problems.append("configuration name '{0}': {1}".format(config, reason))
    try:
        with open(os.path.join(repo, path), encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError) as exc:
        problems.append("does not parse: {0}".format(exc))
        return ["{0}: {1}".format(path, p) for p in problems]
    if not isinstance(document, dict):  # null, a list, a number...
        problems.append("not a JSON object of timestamped records")
        return ["{0}: {1}".format(path, p) for p in problems]
    old = base_document(repo, base, path) if base else None
    for timestamp, record in document.items():
        where = "{0} [{1}]".format(path, timestamp)
        if not valid_timestamp(timestamp):
            problems.append("{0}: key is not an ISO-8601 timestamp".format(where))
        if not isinstance(record, dict):
            problems.append("{0}: record is not an object".format(where))
            continue
        if record.get("test_name") != vignette:
            problems.append(
                "{0}: test_name {1!r} is not {2!r}".format(
                    where, record.get("test_name"), vignette
                )
            )
        if old is not None and timestamp not in old:
            for problem in check_new_record(config, timestamp, record, now):
                problems.append("{0}: {1}".format(where, problem))
    return [p if p.startswith(path) else "{0}: {1}".format(path, p) for p in problems]


def baseline_problems(repo):
    """Per-site baseline directories whose names cannot be published."""
    problems = []
    for _tool, suite in SUITES:
        pattern = os.path.join(repo, suite, "*", "Testing", "Baseline", "*")
        for directory in sorted(glob.glob(pattern)):
            if not os.path.isdir(directory):
                continue
            if not any(IMAGE.search(f) for f in os.listdir(directory)):
                continue
            reason = name_problem(os.path.basename(directory))
            if reason:
                problems.append(
                    "{0}: baseline directory name: {1}".format(
                        os.path.relpath(directory, repo), reason
                    )
                )
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check the history files and baselines a pull request adds."
    )
    parser.add_argument("--repo", default=REPO_ROOT, help="Repository root.")
    parser.add_argument(
        "--base",
        help="Git revision to compare against; records not in it get the "
        "new-record checks (a pull request's base, e.g. origin/master).",
    )
    args = parser.parse_args(argv)
    problems = []
    files = list(history_files(args.repo))
    for path in files:
        problems.extend(check_file(args.repo, path, args.base))
    problems.extend(baseline_problems(args.repo))
    for problem in problems:
        print(problem)
    print(
        "{0} history files checked{1}: {2}".format(
            len(files),
            " against {0}".format(args.base) if args.base else "",
            "{0} problem(s)".format(len(problems)) if problems else "all pass",
        ),
        file=sys.stderr,
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
