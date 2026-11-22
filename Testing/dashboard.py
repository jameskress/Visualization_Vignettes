#!/usr/bin/env python3
#
# Visualization Vignettes
#
# dashboard.py -- a static results dashboard from the committed history
#
# Reads every ParaView_Vignettes/*/Testing/performance_metrics_<config>.json
# and VisIt_Vignettes/*/Testing/performance_metrics_<config>.json and writes
# a small static site:
#
#   index.html        the whole suite at a glance: what an upgrade changed
#                     (one version pair for every machine, coloured only
#                     where Welch's t-test and a 10% floor say the change is
#                     real) and the biggest changes, each machine's speed by
#                     tool version, a status heatmap, system changes, each
#                     vignette's time across machines, and tables of the
#                     active and the retired configurations
#   v-<vignette>.html one vignette on every machine: latest results and run
#                     histories
#   <config>.html     per vignette: run history, a chart per metric, drift,
#                     builds and baselines, every run
#   records.json      every record, flattened, for analysis elsewhere
#
# Run histories put the machine's own run number on the x axis, as
# plot_metrics.py does, not the date: a configuration runs on a handful of
# days a year, and a date axis left most of each chart blank. Dates are in
# the tooltips and the tables.
#
# Times are compared only between runs of the same revision of a vignette,
# read from git (see VignetteRevisions): the vignettes changed over the
# years too, so an old run of an old version may have measured another test.
#
# Testing/retired_configurations.json lists configurations whose hardware
# left the suite. They keep their pages, but drop out of the summary charts
# and are never reported stale.
#
# .github/workflows/dashboard.yml publishes it to GitHub Pages.
#
#   python3 Testing/dashboard.py --out _site
#
# Standard library only, so it runs on a bare GitHub runner. Charts are
# inline SVG with a few lines of script for tooltips; without the script
# every page still reads, and every mark keeps an SVG title.
#
# What it deliberately leaves out: the host name each record carries
# (machine_info.node) and executable paths. On the clusters those name
# compute nodes and module paths that stay out of anything public; the
# records name a build by a hash instead. Configuration names are the
# history files' names, already public in the repository.
#
# Author: James Kress, <james@jameskress.com>
#
import argparse
import ast
import datetime
import glob
import hashlib
import html
import json
import math
import os
import re
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drift  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITES = (("ParaView", "ParaView_Vignettes"), ("VisIt", "VisIt_Vignettes"))
TOOLS = ("ParaView", "VisIt")
VIGNETTE_RE = re.compile(r"^ex(\d+)_")
SITES = ("Workstation", "Ibex", "Shaheen", "Other")

# The builds the suite currently tests (AGENTS.md, Testing/README.md). A
# configuration whose last run used an older version is marked stale. Move
# these when the pinned builds move.
CURRENT_PINS = {"ParaView": "6.2.1", "VisIt": "3.5.0"}
# A configuration with no run for this long is marked stale too.
STALE_DAYS = 30
# Record timestamps are the sites' local clock, all in Saudi Arabia; commit
# times are compared on the same clock, so a build anywhere agrees.
SITE_TZ = datetime.timezone(datetime.timedelta(hours=3))
# Configurations whose hardware left the suite (see load_retired).
RETIRED_FILE = os.path.join("Testing", "retired_configurations.json")

# Charted metrics, in display order. Each chart holds one metric (one axis).
# floor: a chart whose largest value is below it shows noise, not a quantity
# (Slurm reports a few bytes of disk write for a vignette that writes none),
# so it is left out and the value stays in the run table.
CHARTS = [
    # metric, title, unit, floor
    ("execution_time", "Execution time", "s", 0.0),
    ("cpu_seconds", "CPU time", "s", 0.0),
    ("memory_usage_mb", "Peak memory", "MB", 0.0),
    ("disk_read_mb", "Disk read (Slurm)", "MB", 1.0),
    ("disk_write_mb", "Disk write (Slurm)", "MB", 1.0),
    ("io_read_mb", "Storage read (process tree)", "MB", 1.0),
    ("io_write_mb", "Storage write (process tree)", "MB", 1.0),
    ("energy_joules", "Energy", "J", 1.0),
]
SCOPE_FIELD = {metric: drift.scope_of(metric) for metric in drift.METRICS}

# Categorical slots in fixed order (dataviz reference palette). A tool
# version, a site or a configuration keeps its slot on every page: colour
# follows the entity. Sites take the first three slots, which stay
# distinguishable in any pairing.
SLOTS_LIGHT = [
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#6250d6",
    "#e34948",
]
SLOTS_DARK = [
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
]
SITE_SLOT = {"Workstation": 0, "Ibex": 1, "Shaheen": 2, "Other": 3}


# Configurations whose history file is named after a host, and the name the
# public site uses instead. Host names stay out of anything published: a
# dotted configuration name with no entry here stops the build (see
# public_name), so a new one cannot reach the site by accident.
PUBLIC_NAMES = {"KW61316.kaust.edu.sa": "workstation"}


def public_name(config):
    """The name the site publishes for a configuration."""
    if config in PUBLIC_NAMES:
        return PUBLIC_NAMES[config]
    if "." in config:
        raise SystemExit(
            "configuration '{0}' looks like a host name: give it a public name "
            "in PUBLIC_NAMES (Testing/dashboard.py) before it is published".format(
                config
            )
        )
    # A dotless name that is a listed host's short name (KW61316) too.
    return public_text(config)


def public_text(text):
    """`text` with every private configuration name, and its short host name
    (the part before the first dot), replaced by the public name. Whole
    tokens only: a longer word that merely contains the short name stays."""
    text = str(text)
    for private, public in PUBLIC_NAMES.items():
        for form in (private, private.split(".", 1)[0]):
            text = re.sub(
                r"(?<![A-Za-z0-9]){0}(?![A-Za-z0-9])".format(re.escape(form)),
                public,
                text,
                flags=re.IGNORECASE,
            )
    return text


def scrub(value):
    """`value` with public_text applied to every string in it, keys too."""
    if isinstance(value, str):
        return public_text(value)
    if isinstance(value, dict):
        return {scrub(k): scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def publish_names(histories):
    """Histories keyed by public names, every record scrubbed of host names.

    Runs after the vignette revisions are read, which need the history
    files' real names. Two configurations with one public name stop the
    build rather than one silently replacing the other.
    """
    out, origin = {}, {}
    for (config, tool), vignettes in histories.items():
        key = (public_name(config), tool)
        if key in out:
            raise SystemExit(
                "configurations '{0}' and '{1}' would both be published as "
                "'{2}'".format(origin[key], config, key[0])
            )
        origin[key] = config
        out[key] = {
            vignette: [(ts, scrub(record)) for ts, record in rows]
            for vignette, rows in vignettes.items()
        }
    return out


def site_of(config):
    lowered = config.lower()
    if lowered.startswith("shaheen"):
        return "Shaheen"
    if lowered.startswith("ibex"):
        return "Ibex"
    if lowered.startswith(("kw61316", "workstation")):
        return "Workstation"
    return "Other"


def site_order(config):
    return (SITES.index(site_of(config)), config)


def version_key(text):
    parts = []
    for item in re.split(r"[.\-]", str(text or "")):
        parts.append((0, int(item)) if item.isdigit() else (1, item))
    return parts


def vignette_number(name):
    match = VIGNETTE_RE.match(name)
    return int(match.group(1)) if match else 999


def parse_ts(timestamp):
    try:
        return datetime.datetime.fromisoformat(str(timestamp)[:26])
    except ValueError:
        return datetime.datetime(1970, 1, 1)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_histories(repo_root=REPO_ROOT):
    """{(config, tool): {vignette: [(timestamp, record), ...]}} oldest first."""
    histories = {}
    for tool, suite_dir in SUITES:
        pattern = os.path.join(
            repo_root, suite_dir, "*", "Testing", "performance_metrics_*.json"
        )
        for path in sorted(glob.glob(pattern)):
            vignette = path.split(os.sep)[-3]
            if not VIGNETTE_RE.match(vignette):
                continue
            config = os.path.basename(path)[len("performance_metrics_") : -5]
            try:
                with open(path, "r") as handle:
                    document = json.load(handle)
            except (OSError, ValueError) as exc:
                print("skipping {0}: {1}".format(path, exc), file=sys.stderr)
                continue
            if not isinstance(document, dict):
                continue
            rows = sorted(
                (ts, rec) for ts, rec in document.items() if isinstance(rec, dict)
            )
            if rows:
                histories.setdefault((config, tool), {})[vignette] = rows
    return histories


def load_retired(repo_root=REPO_ROOT):
    """{configuration: {"since": date, "reason": text}} from RETIRED_FILE.

    Nodes and GPU types come and go while the vignettes stay. Retiring a
    configuration keeps its history and its page, takes it out of the
    summary charts and never reports it stale. Keys starting with "_" are
    notes. A file that does not parse stops the build: ignoring it would
    put every retired configuration back on the front page as stale.
    """
    path = os.path.join(repo_root, RETIRED_FILE)
    try:
        with open(path, "r") as handle:
            document = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise SystemExit("cannot read {0}: {1}".format(path, exc))
    if not isinstance(document, dict):
        raise SystemExit("{0}: expected an object of configurations".format(path))
    retired = {}
    for config, entry in document.items():
        if config.startswith("_"):
            continue
        if not isinstance(entry, dict) or not entry.get("since"):
            raise SystemExit(
                '{0}: "{1}" needs an object with "since" (and a "reason")'.format(
                    path, config
                )
            )
        retired[config] = entry
    return retired


# ---------------------------------------------------------------------------
# Which revision of a vignette each record ran
# ---------------------------------------------------------------------------
# A vignette's time across tool versions means something only when the
# vignette itself did not change in between: ex00 to ex06 were rewritten in
# September 2026, so every older run measured a different test. A revision
# is a change to the vignette's own Python files that changes their code:
# comments, docstrings and formatting are ignored (the files are compared as
# syntax trees). Generated data fixtures (data/*.py) are not followed.
def _git(repo_root, *args):
    try:
        result = subprocess.run(
            ["git", "-C", repo_root] + list(args),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def code_digest(sources):
    """A digest of Python sources that ignores comments, docstrings and layout."""
    digest = hashlib.sha256()
    for source in sources:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            digest.update(source.encode("utf-8"))
            continue
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if (
                isinstance(body, list)
                and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
        digest.update(ast.dump(tree).encode("utf-8"))
    return digest.hexdigest()


class VignetteRevisions(object):
    """The revision of each vignette a record ran, from the git history.

    A clean record carrying the commit it ran from (`repo.commit`, metrics
    schema 6) gets the revision at that commit: proven. Any other record (an
    older one, or one run from a dirty checkout, whose edits may have been
    to the vignette itself) is bounded instead: it ran no earlier code than
    the revision committed last before it ran (or before its `repo.commit`)
    and, its results being committed afterwards, no later code than the
    revision current when the record was committed (from `git blame` of its
    history file; a later reformat of the file only widens the bound). One
    revision inside those bounds is the record's revision. More than one
    means it may have run code committed after it: it gets a revision of its
    own, so it is never compared with anything. Without a git history (a
    bare copy of the files) every record is revision 0 and `available` is
    False, and build_site says so on stderr.
    """

    def __init__(self, repo_root):
        self.repo_root = repo_root
        self.available = _git(repo_root, "rev-parse", "--git-dir") is not None
        self._eras = {}
        self._at_commit = {}
        self._touched = {}
        self._added = {}
        self._uncertain = 0

    def eras(self, vignette_dir):
        """[(commit time, short sha)] where the vignette's code changed, oldest first."""
        if vignette_dir in self._eras:
            return self._eras[vignette_dir]
        eras, sha_era, last = [], {}, None
        pathspec = ":(glob){0}/*.py".format(vignette_dir)
        log = _git(
            self.repo_root, "log", "--reverse", "--format=%H %cI", "--", pathspec
        )
        for line in (log or "").splitlines():
            sha, when = line.split()
            names = _git(
                self.repo_root, "ls-tree", "--name-only", sha, vignette_dir + "/"
            )
            files = sorted(n for n in (names or "").split() if n.endswith(".py"))
            sources = [_git(self.repo_root, "show", sha + ":" + n) or "" for n in files]
            digest = code_digest(sources)
            if digest != last:
                when = datetime.datetime.fromisoformat(when)
                eras.append((when.astimezone(SITE_TZ).replace(tzinfo=None), sha[:7]))
                last = digest
            sha_era[sha] = len(eras) - 1
        self._eras[vignette_dir] = eras
        self._at_commit[vignette_dir] = sha_era
        return eras

    def added(self, history_path):
        """{timestamp key: when the line holding it was last committed}.

        From `git blame` of one history file. A line not committed yet maps
        to now.
        """
        if history_path in self._added:
            return self._added[history_path]
        out, when = {}, None
        blame = _git(self.repo_root, "blame", "--line-porcelain", "--", history_path)
        for line in (blame or "").splitlines():
            if line.startswith("committer-time "):
                when = datetime.datetime.fromtimestamp(int(line.split()[1]), SITE_TZ)
            elif line.startswith("\t") and when is not None:
                match = re.match(r'\s*"([^"]+)":\s*\{', line[1:])
                if match:
                    out[match.group(1)] = when.replace(tzinfo=None)
        self._added[history_path] = out
        return out

    def _era_at_commit(self, vignette_dir, commit):
        """The era index at `commit`, or None when git does not know it."""
        key = (commit, vignette_dir)
        if key not in self._touched:
            self._touched[key] = _git(
                self.repo_root,
                "log",
                "-1",
                "--format=%H",
                commit,
                "--",
                ":(glob){0}/*.py".format(vignette_dir),
            )
        touched = (self._touched[key] or "").strip()
        return self._at_commit[vignette_dir].get(touched) if touched else None

    def of(self, vignette_dir, history_path, timestamp, record):
        """(revision, label) this record ran; (0, "") when unknown.

        The revision is an era index, or a negative number of its own for a
        record whose revision cannot be pinned down.
        """
        if not self.available:
            return 0, ""
        eras = self.eras(vignette_dir)
        if not eras:
            return 0, ""
        repo = record.get("repo") or {}
        at_commit = (
            self._era_at_commit(vignette_dir, repo["commit"])
            if repo.get("commit")
            else None
        )
        if at_commit is not None and repo.get("dirty") is False:
            return at_commit, self.label(eras, at_commit)
        moment = parse_ts(timestamp)
        low = at_commit
        if low is None:
            before = [n for n, (when, _) in enumerate(eras) if when <= moment]
            if not before:
                # Run before the vignette's first commit: git has no
                # revision for the code it ran.
                self._uncertain += 1
                return (
                    -self._uncertain,
                    "uncertain: run before the vignette's first commit",
                )
            low = max(before)
        committed = self.added(history_path).get(timestamp, datetime.datetime.now())
        high = max(
            [n for n, (when, _) in enumerate(eras) if when <= committed] or [low]
        )
        if high <= low:
            return low, self.label(eras, low)
        self._uncertain += 1
        return (
            -self._uncertain,
            "uncertain: {0} or later, the vignette changed "
            "before this run was committed".format(self.label(eras, low)),
        )

    @staticmethod
    def label(eras, index):
        when, sha = eras[index]
        return "{0} ({1})".format(sha, when.strftime("%d %b %Y"))


def tag_revisions(histories, repo_root=REPO_ROOT):
    """Write each record's vignette revision into it as _rev and _rev_label.

    Returns the VignetteRevisions used, so callers can tell whether the
    history was available.
    """
    revisions = VignetteRevisions(repo_root)
    dirs = dict(SUITES)
    for (config, tool), vignettes in histories.items():
        for vignette, rows in vignettes.items():
            vignette_dir = "{0}/{1}".format(dirs[tool], vignette)
            history = "{0}/Testing/performance_metrics_{1}.json".format(
                vignette_dir, config
            )
            for ts, rec in rows:
                rec["_rev"], rec["_rev_label"] = revisions.of(
                    vignette_dir, history, ts, rec
                )
    return revisions


# ---------------------------------------------------------------------------
# What each record says
# ---------------------------------------------------------------------------
# pass / fail: schema 6 records every gate's verdict. ran_ok / run_failed:
# older records hold only whether the vignette's own run succeeded, which is
# shown as itself rather than as a pass. unknown: the oldest records hold
# neither.
STATUS = {
    "pass": ("&#10003;", "pass"),
    "fail": ("&#10007;", "fail"),
    "ran_ok": ("&#9679;", "ran OK"),
    "run_failed": ("&#9675;", "run failed"),
    "unknown": ("?", "unknown"),
}
STATUS_ORDER = ("pass", "fail", "ran_ok", "run_failed", "unknown")


def status_of(record):
    """(status key, explanation) for one record."""
    verdicts = record.get("verdicts")
    if isinstance(verdicts, dict):
        if verdicts.get("passed"):
            if verdicts.get("gpu_exempt"):
                return "pass", "exempt: needs a GPU, run on a non-GPU machine"
            return "pass", "all gates passed"
        failed = [
            name
            for name in ("image", "numeric", "csv")
            if verdicts.get(name) not in (None, "PASS")
        ]
        if not verdicts.get("run"):
            failed.insert(0, "run")
        if verdicts.get("text") is False:
            failed.append("text")
        return "fail", "failed: " + (", ".join(failed) or "unknown gate")
    if record.get("run_succeeded") is True:
        return "ran_ok", "the run succeeded (gate verdicts are recorded from schema 6)"
    if record.get("run_succeeded") is False:
        return "run_failed", "the run failed (gate verdicts are recorded from schema 6)"
    return "unknown", "this record predates outcome recording"


def comparable_rows(rows, metric):
    """[(ts, record, value, why)] for every row that has `metric`.

    why is "" for a row comparable with the latest run: the rule drift.py
    and plot_metrics.py use (a comparable schema, under the latest run's
    measurement scope), and the same vignette revision as the latest run.
    Otherwise it says why not. Rows that are not comparable are drawn faded,
    so a change in what a number means, or in the test itself, is never read
    as a change in the number.
    """
    scope_field = SCOPE_FIELD.get(metric)
    current = [(ts, rec) for ts, rec in rows if drift.comparable(metric, rec)]
    latest_scope = None
    if scope_field and current:
        # The latest run sets the scope even when it has no value.
        latest_scope = current[-1][1].get(scope_field)
    latest_rev = rows[-1][1].get("_rev", 0) if rows else 0
    out = []
    for ts, rec in rows:
        value = rec.get(metric)
        if not is_number(value):
            continue
        if rec.get("_rev", 0) != latest_rev:
            why = "an older revision of the vignette, {0}".format(
                rec.get("_rev_label") or "?"
            )
        elif not drift.comparable(metric, rec) or (
            scope_field and rec.get(scope_field) != latest_scope
        ):
            why = "measured differently (an older schema or scope)"
        else:
            why = ""
        out.append((ts, rec, float(value), why))
    return out


def run_ok(record):
    """False when the vignette's own run failed, whose time means nothing."""
    verdicts = record.get("verdicts")
    if isinstance(verdicts, dict):
        return bool(verdicts.get("run"))
    return record.get("run_succeeded") is not False


def version_times(rows):
    """{(version, revision): [seconds]} over one vignette's successful, timed runs."""
    out = {}
    for _, rec in rows:
        seconds = rec.get("execution_time")
        if run_ok(rec) and is_number(seconds) and seconds > 0:
            key = (drift.tool_version(rec) or "unknown", rec.get("_rev", 0))
            out.setdefault(key, []).append(float(seconds))
    return out


def versions_timed(rows):
    """The known versions one vignette has a successful timed run at.

    A record with no tool version is left out: "unknown" would sort after
    every release and be read as the newest.
    """
    return {version for version, _ in version_times(rows) if version != "unknown"}


def like_for_like(rows, new, old):
    """(old times, new times, revision label) of one vignette at two versions.

    Only runs of the same vignette revision are compared, the latest
    revision both versions ran. None when they share none: the test changed
    in between, so the two times measure different work.
    """
    times = version_times(rows)
    common = {r for v, r in times if v == new} & {r for v, r in times if v == old}
    if not common:
        return None
    rev = max(common)
    label = next(
        (rec.get("_rev_label") for _, rec in rows if rec.get("_rev", 0) == rev), ""
    )
    return times[(old, rev)], times[(new, rev)], label or ""


def drift_by_record(rows):
    """{timestamp: (drift results, judged)} for one vignette's history.

    judged is False when every metric lacked the history drift.py needs, so
    a reader can tell "no drift" from "too little history to say". Each vignette revision is judged against its own runs only: a run of a
    changed vignette is not drift.
    """
    by_rev = {}
    for ts, rec in rows:
        by_rev.setdefault(rec.get("_rev", 0), []).append((ts, rec))
    out = {}
    for group in by_rev.values():
        for ts, results in drift.check_history(group).items():
            drifted = [r for r in results if r["verdict"] == "drift"]
            judged = any(r["verdict"] != "insufficient" for r in results)
            out[ts] = (drifted, judged)
    return out


def newest_version(vignettes):
    """The highest known tool version any record of this configuration ran."""
    versions = {
        drift.tool_version(rec)
        for rows in vignettes.values()
        for _, rec in rows
        if drift.tool_version(rec)
    }
    return max(versions, key=version_key) if versions else None


def latest_at(rows, version):
    """The last (ts, record) of `version`, else the last of all.

    An older build run after the current one (a backfill of old versions on
    today's vignettes) must not become the configuration's latest result.
    """
    for ts, rec in reversed(rows):
        if drift.tool_version(rec) == version:
            return ts, rec
    return rows[-1]


def config_state(tool, vignettes, now, retired=None):
    """Everything the index says about one configuration and tool.

    The latest result of a vignette is its last run of the newest version
    the configuration has run, so runs of older builds recorded later do
    not replace it. retired: this configuration's RETIRED_FILE entry, or
    None. A retired configuration is never stale: no run is expected of it.
    """
    newest = newest_version(vignettes)
    latest = []
    for vignette in sorted(vignettes, key=vignette_number):
        rows = vignettes[vignette]
        ts, record = latest_at(rows, newest)
        drifted, judged = drift_by_record(rows).get(ts, ([], False))
        latest.append((vignette, ts, record, drifted, judged))
    counts = dict.fromkeys(STATUS_ORDER, 0)
    for entry in latest:
        counts[status_of(entry[2])[0]] += 1
    # Version and freshness come from runs of the newest version only: a
    # vignette that has run nothing newer than an old build keeps that run
    # as its result, but does not speak for the configuration.
    current = [e for e in latest if drift.tool_version(e[2]) == newest] or latest
    last_ts, last_version = max(
        (entry[1], drift.tool_version(entry[2]) or "") for entry in current
    )
    judged_any = any(entry[4] for entry in latest)
    drifting = sum(1 for entry in latest if entry[3]) if judged_any else None
    reasons = []
    age = (now - parse_ts(last_ts)).days
    if not retired and age > STALE_DAYS:
        reasons.append("last run {0} days ago".format(age))
    pin = CURRENT_PINS.get(tool)
    if (
        not retired
        and pin
        and last_version
        and version_key(last_version) < version_key(pin)
    ):
        reasons.append("last ran v{0}; the suite pins v{1}".format(last_version, pin))
    return {
        "latest": latest,
        "counts": counts,
        "last_ts": last_ts,
        "version": last_version,
        "drifting": drifting,
        "stale": reasons,
        "retired": retired,
        "versions": sorted(
            {
                drift.tool_version(rec) or "unknown"
                for rows in vignettes.values()
                for _, rec in rows
            },
            key=version_key,
        ),
    }


# ---------------------------------------------------------------------------
# Small rendering helpers
# ---------------------------------------------------------------------------
def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def fmt(value, digits=1):
    """A number for a table cell, escaped when it is not a number."""
    if value is None:
        return ""
    if isinstance(value, float):
        if abs(value) >= 1000:
            return "{0:,.0f}".format(value)
        if value and abs(value) < 0.05 and digits <= 1:
            return "&lt;0.1"
        return "{0:.{1}f}".format(value, digits)
    if is_number(value):
        return str(value)
    return esc(value)


def short_date(timestamp):
    return str(timestamp)[:10]


def long_date(timestamp):
    return parse_ts(timestamp).strftime("%d %b %Y")


def status_class(status):
    return status.replace("_", "-")


def status_chip(status, detail=""):
    glyph, label = STATUS[status]
    return '<span class="st st-{0}" title="{1}">{2} {3}</span>'.format(
        status_class(status), esc(detail), glyph, label
    )


def page_names(configs):
    """{configuration: page file}, distinct for distinct names, never index.html.

    A configuration keeps its own spelling when it is safe in a URL. One
    that had to be changed, or that would take a name already given out
    (index.html, or another configuration's page, compared without case),
    gets a digest of its original name, lengthened until it is free.
    """
    used = {"index.html", "records.json"}
    names = {}
    # Unchanged names first, so a safe name is never the one displaced.
    for config in sorted(configs, key=lambda c: (_safe(c) != c, c)):
        safe = _safe(config)
        digest = hashlib.sha256(config.encode("utf-8")).hexdigest()
        # "v-" names are the vignette pages' (vignette_page): a configuration
        # whose name starts so is given "config-" in front.
        vignette_like = safe.lower().startswith("v-")
        candidate = safe + ".html" if safe == config and not vignette_like else None
        length = 10
        while candidate is None or candidate.lower() in used:
            candidate = "{0}{1}-{2}.html".format(
                "config-" if vignette_like else "", safe, digest[:length]
            )
            length += 2
        used.add(candidate.lower())
        names[config] = candidate
    return names


# Filled by build_site() from every configuration it renders.
PAGE_NAMES = {}


def page_name(config):
    """The page build_site() gave this configuration."""
    if config not in PAGE_NAMES:
        PAGE_NAMES.update(page_names(set(PAGE_NAMES) | {config}))
    return PAGE_NAMES[config]


def _safe(config):
    return re.sub(r"[^A-Za-z0-9._-]", "_", config)


def nice_ticks(value, target=4):
    """Round tick values from 0 to at least `value`: 1, 2, 2.5 or 5 x 10^k."""
    if value <= 0:
        return [0.0, 1.0]
    raw = value / float(target)
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    count = int(math.ceil(value / step - 1e-9))
    return [step * k for k in range(count + 1)]


def tick_label(value):
    return esc("{0:,.6g}".format(value))


def display_unit(unit, values):
    """(unit, factor): memory in GB past 2 GB, energy in kJ past 10 kJ."""
    peak = max(values) if values else 0
    if unit == "MB" and peak >= 2048:
        return "GB", 1.0 / 1024
    if unit == "J" and peak >= 10000:
        return "kJ", 1.0 / 1000
    return unit, 1.0


def svg_open(width, height, label, cls="chart"):
    return '<svg class="{3}" viewBox="0 0 {0} {1}" role="img" aria-label="{2}">'.format(
        width, height, esc(label), cls
    )


def svg_y_grid(ticks, y_max, left, right, top, bottom_y):
    out = []
    for value in ticks:
        y = top + (bottom_y - top) * (1 - value / y_max)
        out.append(
            '<line class="grid" x1="{0}" x2="{1}" y1="{2:.1f}" y2="{2:.1f}"/>'
            '<text class="tick" x="{3}" y="{4:.1f}" text-anchor="end">{5}</text>'.format(
                left, right, y, left - 6, y + 3.5, tick_label(value)
            )
        )
    out.append(
        '<line class="axis" x1="{0}" x2="{1}" y1="{2}" y2="{2}"/>'.format(
            left, right, bottom_y
        )
    )
    return "".join(out)


def svg_dot(slot, x, y, tip, extra="", r=4):
    return (
        '<circle class="dot s{0}{1}" cx="{2:.1f}" cy="{3:.1f}" r="{4}" '
        'data-tip="{5}"><title>{5}</title></circle>'.format(
            slot, extra, x, y, r, esc(tip)
        )
    )


def legend(items):
    """[(slot, label)] -> a legend, only when there are two or more."""
    if len(items) < 2:
        return ""
    return '<div class="legend">{0}</div>'.format(
        "".join(
            '<span class="key"><span class="swatch s{0}"></span>{1}</span>'.format(
                slot, esc(label)
            )
            for slot, label in items
        )
    )


def status_legend():
    keys = "".join(
        '<span class="key"><span class="cell c-{0}">{1}</span>{2}</span>'.format(
            status_class(key), STATUS[key][0], STATUS[key][1]
        )
        for key in STATUS_ORDER
    )
    return (
        '<div class="legend">{0}<span class="key"><span class="cell c-unknown drift">'
        "</span>drift warning</span></div>".format(keys)
    )


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def relative_by_version(vignettes):
    """[(version, ratio, vignettes compared)] for one configuration.

    ratio: how long an earlier version took against the configuration's
    newest version, the geometric mean over vignettes of median time there
    over median time at the newest. Each vignette counts only through runs
    of one revision of it (like_for_like), so a version that ran only older
    revisions of the vignettes is absent rather than compared with a
    different test. The newest version is (newest, 1.0, vignettes timed).
    """
    versions = sorted(
        {v for rows in vignettes.values() for v in versions_timed(rows)},
        key=version_key,
    )
    if not versions:
        return []
    newest = versions[-1]
    out = []
    for version in versions[:-1]:
        logs = []
        for rows in vignettes.values():
            pair = like_for_like(rows, newest, version)
            if pair:
                old, new, _ = pair
                logs.append(math.log(statistics.median(old) / statistics.median(new)))
        if logs:
            out.append((version, math.exp(sum(logs) / len(logs)), len(logs)))
    timed = sum(1 for rows in vignettes.values() if newest in versions_timed(rows))
    out.append((newest, 1.0, timed))
    return out


def svg_dot_plot(tool, rows):
    """Each vignette's latest time per configuration, log x, dots by site.

    rows: [(vignette, [(config, seconds)])].
    """
    values = [s for _, dots in rows for _, s in dots if s > 0]
    if not values:
        return ""
    row_h = 22
    left, right, top, bottom = 178, 34, 10, 30
    width = 660
    height = top + bottom + row_h * len(rows)
    lo = 10 ** math.floor(math.log10(min(values)))
    hi = 10 ** math.ceil(math.log10(max(values)))
    if hi <= lo:
        hi = lo * 10

    def sx(seconds):
        frac = (math.log10(seconds) - math.log10(lo)) / (
            math.log10(hi) - math.log10(lo)
        )
        return left + frac * (width - left - right)

    out = [
        svg_open(
            width,
            height,
            "{0} time per vignette across machines".format(tool),
            "chart rows",
        )
    ]
    decade = lo
    while decade <= hi * 1.0001:
        x = sx(decade)
        out.append(
            '<line class="grid" x1="{0:.1f}" x2="{0:.1f}" y1="{1}" y2="{2}"/>'
            '<text class="tick" x="{0:.1f}" y="{3}" text-anchor="middle">{4} s</text>'.format(
                x, top, height - bottom, height - bottom + 14, tick_label(decade)
            )
        )
        decade *= 10
    for index, (vignette, dots) in enumerate(rows):
        y = top + row_h * index + row_h / 2.0
        out.append(
            '<line class="rowline" x1="{0}" x2="{1}" y1="{2:.1f}" y2="{2:.1f}"/>'
            '<text class="rowlabel" x="{3}" y="{4:.1f}" text-anchor="end">{5}</text>'.format(
                left, width - right, y, left - 8, y + 4, esc(vignette)
            )
        )
        for config, seconds in dots:
            if seconds > 0:
                tip = "{0} | {1} | {2:,.3g} s".format(vignette, config, seconds)
                out.append(
                    svg_dot(SITE_SLOT[site_of(config)], sx(seconds), y, tip, r=5)
                )
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------------------
# Page frame
# ---------------------------------------------------------------------------
CSS = """
:root{color-scheme:light;--page:#f6f7f8;--surface:#ffffff;--ink:#0e1214;
--ink2:#475057;--muted:#7b848a;--grid:#e1e4e6;--axis:#c2c8cc;
--ring:rgba(14,18,20,.10);--good:#0ca30c;--warn:#fab219;--bad:#d03b3b;
--good-soft:#d6f0d6;--bad-soft:#f7d9d9;--na:#eef1f3;--mid:#eef1f3;
--accent:#0b5f73;--accent-ink:#ffffff;
--fast2:#1c5cab;--fast1:#86b6ef;--slow1:#ec8584;--slow2:#b8302f;
--on-strong:#ffffff;--on-mild:#0e1214;
--v1:#86b6ef;--v2:#6da7ec;--v3:#5598e7;--v4:#3987e5;--v5:#2a78d6;--v6:#1c5cab;--v7:#0d366b;
--sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
--mono:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Menlo,monospace;
%(light)s}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){%(dark)s}}
:root[data-theme="dark"]{%(dark)s}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:14.5px/1.55 var(--sans)}
main{max-width:76rem;margin:0 auto;padding-block:24px 64px;
padding-left:max(16px,env(safe-area-inset-left,0px));
padding-right:max(16px,env(safe-area-inset-right,0px))}
h1,h2,h3{text-wrap:balance;line-height:1.2}
h1{font-size:clamp(1.6rem,1.3rem + 1.4vw,2.3rem);font-weight:700;margin:0 0 8px;
letter-spacing:-.01em}
h2{font-size:1.3rem;font-weight:600;margin:0 0 6px}
section{margin-top:40px}
h3{font-size:1rem;font-weight:600;margin:0 0 4px}
p.lede{font-size:1.05rem;color:var(--ink2);margin:4px 0 10px;max-width:68ch}
.note{color:var(--ink2);font-size:13.5px;margin:2px 0 10px;max-width:72ch}
h3 .unit,h4 .unit{color:var(--muted);font-weight:400;font-size:12px}
.banner{background:var(--na);border-radius:8px;padding:8px 12px;color:var(--ink2)}
.howto-box summary{color:var(--ink)}
.howto{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
gap:6px 24px;margin:8px 0 0;font-size:13px}
.howto div{display:flex;gap:10px}.howto dt{flex:0 0 96px;font-weight:600;color:var(--ink)}
.howto dd{margin:0;color:var(--ink2)}
.multiples{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));
gap:10px;margin-top:6px}
.panel h4{margin:0;font-size:13px;font-weight:600}.panel h4 a{text-decoration:none}
.muted{color:var(--muted)}
a{color:var(--ink)}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;
padding:12px 14px;margin:10px 0}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.tall{max-height:72vh;overflow:auto}
table{border-collapse:separate;border-spacing:0;width:100%%;
font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--grid);
white-space:nowrap;vertical-align:top}
thead th{position:sticky;top:0;background:var(--surface);z-index:2;
color:var(--ink2);font-weight:600;font-size:12px}
td.num,th.num{text-align:right}
tr.stale td{color:var(--muted)}
.badge{display:inline-block;font-size:11px;font-weight:400;border-radius:4px;
padding:0 6px;margin-left:8px;border:1px solid var(--axis);color:var(--ink2);
white-space:nowrap;vertical-align:middle}
.badge.stale{background:var(--na)}
.st{font-size:12px;white-space:nowrap}
.st-pass{color:var(--good)}.st-fail{color:var(--bad);font-weight:600}
.st-ran-ok{color:var(--ink2)}.st-run-failed{color:var(--bad)}.st-unknown{color:var(--muted)}
.drift-flag{color:var(--ink);background:color-mix(in srgb,var(--warn) 35%%,transparent);
border-radius:4px;padding:0 5px;font-size:12px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;
margin:14px 0}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:10px;
padding:10px 12px}
.tile .v{font-size:26px;font-weight:600;line-height:1.2}
.tile .k{font-size:12px;color:var(--ink2)}
.grid-charts{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));
gap:12px;margin-top:8px}
.chart-box h4{margin:0;font-size:13px;font-weight:600}
svg.chart{width:100%%;height:auto;display:block}
svg.chart.rows{max-width:860px}
svg .grid{stroke:var(--grid);stroke-width:1}
svg .axis{stroke:var(--axis);stroke-width:1}
svg .rowline{stroke:var(--grid);stroke-width:1;stroke-dasharray:2 3}
svg .tick{fill:var(--muted);font-size:10px}
svg .rowlabel{fill:var(--ink2);font-size:11px}
svg .ref{stroke:var(--ink2);stroke-width:1;stroke-dasharray:4 3}
svg .line{fill:none;stroke-width:2}
svg .dot{stroke:var(--surface);stroke-width:2}
svg .dot.drift{stroke:var(--ink);stroke-width:2}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--ink2);
margin:6px 0}
.key{display:inline-flex;align-items:center;gap:6px}
.swatch{width:10px;height:10px;border-radius:50%%;display:inline-block}
details{margin:8px 0}summary{cursor:pointer;color:var(--ink2)}
.strip{display:flex;gap:2px;flex-wrap:nowrap}
.cell{width:16px;height:16px;border-radius:3px;display:inline-block;
font-size:10px;line-height:16px;text-align:center}
.c-pass{background:var(--good);color:#fff}.c-fail{background:var(--bad);color:#fff}
.c-ran-ok{background:var(--good-soft);color:var(--ink2)}
.c-run-failed{background:var(--bad-soft);color:var(--bad)}
.c-unknown{background:var(--na);color:var(--muted)}
.cell.drift,td.hm.drift .cell{outline:2px solid var(--warn);outline-offset:-1px}
table.heat{width:auto}
table.heat td.hm{text-align:center;padding:2px;min-width:26px}
table.heat td.hm .cell{width:22px;height:20px;line-height:20px;font-size:11px}
table.heat th.col{text-align:center;vertical-align:bottom;padding:6px 2px;
font-weight:600;font-size:12px}
table.heat th.col span{display:inline-block;writing-mode:vertical-rl;
transform:rotate(180deg);white-space:nowrap;overflow:hidden;
text-overflow:ellipsis;max-height:210px}
table.heat th.col.stale,table.heat th.col.stale a{color:var(--muted);font-weight:400}
table.heat thead th{position:static}
table.heat th.site{text-align:center;font-size:11px;border-bottom:2px solid var(--axis)}
table.heat td.rowh{position:sticky;left:0;background:var(--surface);z-index:1;
font-size:12px}
.cell.none{background:transparent;color:var(--muted)}
.note.empty{margin:24px 8px;color:var(--muted)}
#tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);
border:1px solid var(--ring);border-radius:6px;padding:4px 8px;font-size:12px;
box-shadow:0 2px 8px rgba(0,0,0,.15);display:none;z-index:9;max-width:340px}
footer{color:var(--muted);font-size:12px;margin-top:40px}
@media (max-width:600px){h1{font-size:20px}.tile .v{font-size:22px}
table.heat th.col span{max-height:130px}.grid-charts{grid-template-columns:1fr}}
"""

DARK = (
    "color-scheme:dark;--page:#0c0f10;--surface:#15191b;--ink:#eef1f2;"
    "--ink2:#b9c1c6;--muted:#848d93;--grid:#262c2f;--axis:#384045;"
    "--ring:rgba(255,255,255,.10);--good-soft:#173d17;--bad-soft:#4a1d1d;"
    "--na:#1d2326;--mid:#1d2326;--accent:#5fb7c9;--accent-ink:#061417;"
    "--fast2:#5598e7;--fast1:#184f95;--slow1:#8f3534;--slow2:#e66767;"
    "--on-strong:#0e1214;--on-mild:#eef1f2;"
    "--v1:#184f95;--v2:#1c5cab;--v3:#256abf;--v4:#3987e5;--v5:#6da7ec;"
    "--v6:#9ec5f4;--v7:#cde2fb;"
)

# The redesign (#106): site header, upgrade table, run charts, vignette pages.
# Colours: the five-step change scale is two validated ordinal arms (blue
# faster, red slower) with no fill between; the version ramp is one validated
# ordinal blue, light old to dark new, backed by marker shapes.
CSS_REDESIGN = (
    """
[hidden]{display:none!important}
a{color:var(--accent)}
a:focus-visible,button:focus-visible,select:focus-visible{outline:2px solid var(--accent);
outline-offset:2px}
.sitebar{background:var(--surface);border-bottom:1px solid var(--ring)}
.sitebar .in{max-width:76rem;margin:0 auto;display:flex;flex-wrap:wrap;gap:8px 22px;
align-items:center;padding-block:12px;padding-left:max(16px,env(safe-area-inset-left,0px));
padding-right:max(16px,env(safe-area-inset-right,0px))}
.brand{font-weight:700;color:var(--ink);text-decoration:none;display:flex;gap:9px;
align-items:center}
.brand svg{width:22px;height:22px}
.sitebar nav{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:14px}
.sitebar nav a{color:var(--ink2);text-decoration:none}
.sitebar nav a.on{color:var(--ink);font-weight:600}
.eyebrow{font:500 11.5px/1.2 var(--mono);letter-spacing:.08em;text-transform:uppercase;
color:var(--muted);margin:0 0 8px}
.crumbs{font-size:13px;color:var(--muted);margin:0 0 10px}
.summary{display:flex;flex-wrap:wrap;gap:10px 24px;align-items:baseline;margin:6px 0 18px}
.summary .big{font:500 2rem/1 var(--mono)}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:13px;padding:3px 10px;
border-radius:999px;background:var(--na);color:var(--ink2)}
.pill .dot{width:8px;height:8px;border-radius:50%}
.dot.bad{background:var(--bad)}.dot.warn{background:var(--warn)}
.js-only{display:none}
.js .js-only{display:flex}
.controls{flex-wrap:wrap;gap:10px 16px;align-items:center;margin:14px 0 10px}
.seg{display:inline-flex;border:1px solid var(--ring);border-radius:8px;overflow:hidden}
.seg button{font:500 14px var(--sans);padding:7px 14px;border:0;background:var(--surface);
color:var(--ink2);cursor:pointer}
.seg button[aria-pressed="true"]{background:var(--ink);color:var(--surface)}
select{font:500 14px var(--sans);padding:7px 10px;border-radius:8px;
border:1px solid var(--ring);background:var(--surface);color:var(--ink)}
label.inline{display:inline-flex;gap:8px;align-items:center;font-size:14px;color:var(--ink2)}
.pairtitle{font-size:1.05rem;margin:4px 0 8px}
.pairview h3:not(.pairtitle){margin-top:22px}
table.matrix{font-size:13px}
table.matrix td.rowh{white-space:nowrap;padding:0 12px 0 0;position:sticky;left:0;
background:var(--surface);z-index:1}
table.matrix td.rowh a{color:var(--ink);text-decoration:none}
table.matrix td.rowh a:hover{text-decoration:underline}
.n{font-family:var(--mono);color:var(--muted);margin-right:6px}
td.c{text-align:center;padding:0}
td.c span{display:block;margin:2px;min-width:52px;height:30px;line-height:30px;
border-radius:4px;font:12.5px var(--mono);color:var(--ink2)}
td.c span.fast2,.key i.fast2,.bar b.fast2{background:var(--fast2);color:var(--on-strong)}
td.c span.fast1,.key i.fast1,.bar b.fast1{background:var(--fast1);color:var(--on-mild)}
td.c span.slow1,.key i.slow1,.bar b.slow1{background:var(--slow1);color:var(--on-mild)}
td.c span.slow2,.key i.slow2,.bar b.slow2{background:var(--slow2);color:var(--on-strong)}
td.c span.one,.key .one{text-decoration:underline dotted var(--muted);
text-underline-offset:3px}
td.c span.none{color:var(--axis)}
.key{display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center;font-size:13px;
color:var(--ink2);margin:10px 0 2px}
.key i{display:inline-block;width:26px;height:14px;border-radius:3px;vertical-align:-2px;
margin-right:6px}
.key i.plain{border:1px solid var(--axis)}
table.list{width:100%;font-size:13.5px}
table.list th{font-weight:500;color:var(--muted);font-size:12px;border-bottom:1px solid var(--axis)}
.bar{display:inline-block;position:relative;width:110px;height:12px;vertical-align:-1px}
.bar::before{content:"";position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;
background:var(--axis)}
.bar b{position:absolute;top:0;height:12px;border-radius:2px}
.panels{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(230px,100%),1fr));
gap:12px}
.panels.wide{grid-template-columns:repeat(auto-fill,minmax(min(320px,100%),1fr))}
.panel{background:var(--surface);border:1px solid var(--ring);border-radius:8px;
padding:10px 12px 6px;min-width:0}
.panel h4{display:flex;gap:6px;align-items:center}
.panel .sub{font-size:12px;color:var(--muted)}
.sub-h{font-size:14px;margin:18px 0 8px}
svg.chart.wide{min-width:640px}
svg .dlabel{fill:var(--ink2);font-size:11px}
.howto{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 28px;font-size:13.5px}
.howto div{display:grid;grid-template-columns:8.5rem minmax(0,1fr);gap:10px}
.howto dt{flex:none}
@media (max-width:760px){.howto{grid-template-columns:minmax(0,1fr)}}
@media (max-width:480px){.howto div{grid-template-columns:minmax(0,1fr);gap:2px}}
svg .leader{fill:none;stroke-width:1;opacity:.55}
svg .sys{stroke:var(--warn);stroke-width:1.5;stroke-dasharray:3 3}
svg .hit{fill:transparent}
svg .hollow{fill:none;stroke-width:1.4;stroke:var(--ink2)}
"""
    + "".join(
        ".vs{0}{{fill:var(--v{0});stroke:var(--surface);stroke-width:1}}"
        ".hollow.vh{0}{{stroke:var(--v{0})}}".format(i)
        for i in range(1, 8)  # VERSION_STEPS
    )
    + """
svg .drift{stroke:var(--ink);stroke-width:2}
svg.mk{width:14px;height:14px;display:inline-block;vertical-align:-2px;margin-right:4px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 14px}
.chip{font:12.5px var(--mono);padding:3px 8px;border-radius:5px;background:var(--na)}
.chip .sym{font-weight:600}.chip.pass .sym{color:var(--good)}
.chip.fail .sym,.chip.run-failed .sym{color:var(--bad)}
"""
)

SCRIPT = """
<div id="tip"></div>
<script>
document.documentElement.classList.add('js');
(function(){
// The tool switch shows one tool's blocks; each tool's selector shows one
// of that tool's version pairs.
var seg=document.getElementById('toolseg');
function showPair(sel){var tool=sel.value.split('|')[0];
 document.querySelectorAll('.pairview').forEach(function(v){
  if(v.dataset.tool===tool){v.hidden=v.dataset.pair!==sel.value;}});}
function pick(tool){
 document.querySelectorAll('[data-tool]').forEach(function(e){
  if(e.tagName==='BUTTON'){e.setAttribute('aria-pressed',e.dataset.tool===tool);return;}
  if(e.classList.contains('pairview')){if(e.dataset.tool!==tool){e.hidden=true;}return;}
  e.hidden=e.dataset.tool!==tool;});
 document.querySelectorAll('select.pairsel').forEach(function(s){
  if(s.value.split('|')[0]===tool){showPair(s);}});
}
document.querySelectorAll('select.pairsel').forEach(function(s){
 s.addEventListener('change',function(){showPair(s);});});
if(seg){seg.addEventListener('click',function(e){var b=e.target.closest('button');
 if(b){pick(b.dataset.tool);}});pick(seg.querySelector('button').dataset.tool);}
})();
(function(){var t=document.getElementById('tip');
document.addEventListener('mouseover',function(e){var d=e.target.closest('[data-tip]');
if(!d){t.style.display='none';return;}t.textContent=d.getAttribute('data-tip');
t.style.display='block';});
document.addEventListener('mousemove',function(e){var x=e.clientX+12;
if(x+t.offsetWidth>innerWidth-8){x=e.clientX-t.offsetWidth-12;}
t.style.left=x+'px';t.style.top=(e.clientY+12)+'px';});
})();
</script>
"""


def css():
    def slots(colors):
        return "".join("--s{0}:{1};".format(i, c) for i, c in enumerate(colors))

    base = CSS % {"light": slots(SLOTS_LIGHT), "dark": DARK + slots(SLOTS_DARK)}
    classes = "".join(
        ".s{0}{{stroke:var(--s{0})}}circle.s{0},rect.s{0}{{fill:var(--s{0})}}"
        ".swatch.s{0}{{background:var(--s{0})}}".format(i)
        for i in range(len(SLOTS_LIGHT))
    )
    return base + classes + CSS_REDESIGN


FONTS = (
    "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family="
    "IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700"
    "&display=swap'>"
)
BRAND_SVG = (
    "<svg viewBox='0 0 24 24' aria-hidden='true'><circle cx='12' cy='12' r='10' "
    "fill='none' stroke='currentColor' stroke-width='1.6'/><path d='M4 15c3-6 6 2 "
    "9-3s5-3 7-1' fill='none' stroke='var(--accent)' stroke-width='2' "
    "stroke-linecap='round'/></svg>"
)
REPO_URL = "https://github.com/jameskress/Visualization_Vignettes"


def site_header(here, root="../"):
    """The bar every Pages page shares. here: home, results or gallery."""
    links = (
        ("home", root, "Home"),
        ("results", root + "dashboard/", "Results"),
        ("gallery", root + "gallery/", "Gallery"),
        ("add", REPO_URL + "/blob/master/Testing/ADD_YOUR_SITE.md", "Add your site"),
        ("github", REPO_URL, "GitHub"),
    )
    return (
        "<header class='sitebar'><div class='in'><a class='brand' href='{0}'>{1}"
        "Visualization Vignettes</a><nav aria-label='Site'>{2}</nav></div></header>"
    ).format(
        esc(root),
        BRAND_SVG,
        "".join(
            "<a href='{0}'{1}>{2}</a>".format(
                esc(href),
                " class='on' aria-current='page'" if key == here else "",
                text,
            )
            for key, href, text in links
        ),
    )


def page(title, body, generated):
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>{0}</title>{5}<style>{1}</style></head><body>{6}<main>{2}"
        "<footer>Generated {3} from the performance_metrics records in "
        "jameskress/Visualization_Vignettes by Testing/dashboard.py. "
        "Drift rule and record fields: Testing/README.md.</footer>"
        "</main>{4}</body></html>"
    ).format(
        esc(title), css(), body, esc(generated), SCRIPT, FONTS, site_header("results")
    )


# ---------------------------------------------------------------------------
# What each vignette is, for headings and the landing page
# ---------------------------------------------------------------------------
# What each vignette number shows, in words that fit both tools. A vignette
# not listed here still appears, under its directory name.
ABOUT = {
    0: ("Query", "Loads a dataset and checks its mesh statistics and metadata."),
    1: ("Screenshot", "The basic rendering pipeline, saved as an image."),
    2: ("Camera animation", "A camera path around the data, frame by frame."),
    3: ("Isosurface animation", "An isovalue swept through the field."),
    4: ("Streamlines", "Flow visualization with seeded streamlines."),
    5: ("Time series", "One rendering per time step of a multi-step file."),
    6: ("Large data", "A large dataset rendered in parallel."),
    7: (
        "Scaling",
        "Isosurface extraction across rank counts; geometry must not change.",
    ),
    8: ("Backend check", "Fails when a job that asked for a GPU renders in software."),
    9: ("Mesh topologies", "One contour pipeline over several mesh types."),
    10: (
        "Colormap fidelity",
        "One field through four transfer functions, each with a legend.",
    ),
    11: ("State verification", "A saved session reloaded headlessly and stepped."),
    12: ("Extract regression", "Image, data and numeric extracts side by side."),
}


def vignette_title(vignette):
    """'ex03 Isosurface animation' for a vignette directory name."""
    n = vignette_number(vignette)
    if n is None or n not in ABOUT:
        return vignette
    return "ex{0:02d} {1}".format(n, ABOUT[n][0])


# ---------------------------------------------------------------------------
# Is a change real? Welch's t-test on the repeated runs
# ---------------------------------------------------------------------------
# A change is coloured only when it is at least MIN_CHANGE and Welch's t-test
# on the runs at the two versions gives p below SIG_P (Perfherder colours a
# comparison only when its t-test is confident; --repeat 3 gives each
# version the runs to test). With one run at either version there is no
# spread to test against: the change is printed, never coloured.
SIG_P = 0.05
MIN_CHANGE = 0.10


def _betacf(a, b, x):
    """The continued fraction of the regularised incomplete beta function."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        for aa in (
            m * (b - m) * x / ((qam + m2) * (a + m2)),
            -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2)),
        ):
            d = 1.0 + aa * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + aa / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 3e-12:
            break
    return h


def _ibeta(a, b, x):
    """The regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def welch_p(xs, ys):
    """Two-sided p of Welch's t-test; None with fewer than two runs a side."""
    if len(xs) < 2 or len(ys) < 2:
        return None
    sx = statistics.variance(xs) / len(xs)
    sy = statistics.variance(ys) / len(ys)
    diff = statistics.mean(xs) - statistics.mean(ys)
    if sx + sy == 0:
        return 0.0 if diff else 1.0
    t = diff / math.sqrt(sx + sy)
    df = (sx + sy) ** 2 / (sx**2 / (len(xs) - 1) + sy**2 / (len(ys) - 1))
    return _ibeta(df / 2.0, 0.5, df / (df + t * t))


def change_class(change, p, agree=True):
    """The five-step class of one comparison: blue faster, red slower.

    'one': a version has one run, so there is nothing to test. 'noise':
    under MIN_CHANGE, p at or above SIG_P, or (agree False) the mean the
    t-test compared moved the other way from the median shown, so the test
    does not speak for the number. Otherwise fast1/fast2 or slow1/slow2, the
    2 for more than 20%. A change exactly at MIN_CHANGE counts.
    """
    if p is None:
        return "one"
    if p >= SIG_P or abs(change) < MIN_CHANGE - 1e-9 or not agree:
        return "noise"
    if change < 0:
        return "fast2" if change <= -0.20 else "fast1"
    return "slow2" if change >= 0.20 else "slow1"


def pct(change):
    """'+12%' or '−15%' (a real minus sign)."""
    value = int(round(abs(change) * 100))
    sign = "+" if change > 0 and value else ("−" if change < 0 and value else "")
    return "{0}{1}%".format(sign, value)


# ---------------------------------------------------------------------------
# System changes: what a maintenance changed under the vignettes
# ---------------------------------------------------------------------------
# The machine fields a record carries that a system change moves. A step in
# a run history that lines up with one is a system change, not a tool one.
PLATFORM_FIELDS = (
    ("os_release", "OS"),
    ("release", "kernel"),
    ("gpu_drivers", "GPU driver"),
    ("cpu_governor", "CPU governor"),
)


def platform_of(record):
    """{field: value} of the platform settings one record carries."""
    info = record.get("machine_info") or {}
    out = {}
    for field, _ in PLATFORM_FIELDS:
        if field == "gpu_drivers":
            drivers = sorted(
                {g.get("driver") for g in info.get("gpus") or [] if g.get("driver")}
            )
            if drivers:
                out[field] = ", ".join(drivers)
        elif info.get(field) is not None:
            out[field] = str(info[field])
    return out


def platform_changes(rows_by_vignette):
    """[(timestamp, [(label, old, new)])]: every run in which a setting changed.

    rows_by_vignette: {key: [(ts, record)]}, one configuration; key a
    vignette or (tool, vignette). Every record is read in time order, so a
    change seen only in a later record of a run (the VisIt half of a run id
    shared with ParaView) still counts. A change is dated by its run's first
    record. A setting seen for the first time is not a change; a record that
    does not carry a setting (an older schema) neither.
    """
    # By time only: two records with one timestamp must not compare dicts.
    records = sorted(
        ((ts, record) for rows in rows_by_vignette.values() for ts, record in rows),
        key=lambda item: item[0],
    )
    run_start = {}
    for ts, record in records:
        run_start.setdefault(record.get("run_id") or ts, ts)
    known, by_run = {}, {}
    for ts, record in records:
        values = platform_of(record)
        for field, label in PLATFORM_FIELDS:
            value = values.get(field)
            if value is None:
                continue
            if field in known and known[field] != value:
                run = run_start[record.get("run_id") or ts]
                by_run.setdefault(run, []).append((label, known[field], value))
            known[field] = value
    return sorted(by_run.items())


def change_text(changes):
    return "; ".join(
        "{0} {1} \u2192 {2}".format(label, old, new) for label, old, new in changes
    )


# ---------------------------------------------------------------------------
# Run-number charts (the plot_metrics.py layout)
# ---------------------------------------------------------------------------
# A tool's versions take steps of one blue ramp, light (old) to dark (new),
# and a marker shape each, so they read in colour, in shape and in print.
VERSION_STEPS = 7
SHAPES = ("circle", "square", "triangle", "diamond", "down")


class VersionStyle(object):
    """The colour step and marker shape of each version of one tool."""

    def __init__(self, versions):
        self.versions = sorted(set(versions), key=version_key)

    def step(self, version):
        if version not in self.versions:
            return 1
        from_newest = len(self.versions) - 1 - self.versions.index(version)
        return max(1, VERSION_STEPS - from_newest)

    def shape(self, version):
        if version not in self.versions:
            return "circle"
        return SHAPES[self.versions.index(version) % len(SHAPES)]


def svg_marker(shape, x, y, r, cls, tip=""):
    """One marker; tip adds a tooltip and an SVG title."""
    title = ' data-tip="{0}"'.format(esc(tip)) if tip else ""
    inner = "<title>{0}</title>".format(esc(tip)) if tip else ""
    if shape == "square":
        s = r * 0.9
        return '<rect class="{0}" x="{1:.1f}" y="{2:.1f}" width="{3:.1f}" height="{3:.1f}"{4}>{5}</rect>'.format(
            cls, x - s, y - s, 2 * s, title, inner
        )
    if shape == "circle":
        return '<circle class="{0}" cx="{1:.1f}" cy="{2:.1f}" r="{3}"{4}>{5}</circle>'.format(
            cls, x, y, r, title, inner
        )
    if shape == "diamond":
        k = r * 1.25
        pts = [(x, y - k), (x + k, y), (x, y + k), (x - k, y)]
    elif shape == "down":
        pts = [
            (x - r * 1.15, y - r * 0.8),
            (x + r * 1.15, y - r * 0.8),
            (x, y + r * 1.2),
        ]
    else:
        pts = [
            (x, y - r * 1.2),
            (x + r * 1.15, y + r * 0.8),
            (x - r * 1.15, y + r * 0.8),
        ]
    return '<polygon class="{0}" points="{1}"{2}>{3}</polygon>'.format(
        cls, " ".join("{0:.1f},{1:.1f}".format(a, b) for a, b in pts), title, inner
    )


def version_legend(style, extra=True, versions=None):
    """The legend of a chart drawn with `style`; versions: the ones it shows.

    The encodings always come from the tool's whole style, so a chart that
    shows only some versions draws them exactly as its legend does.
    """
    shown = [v for v in style.versions if versions is None or v in versions]
    keys = []
    for version in shown:
        keys.append(
            '<span class="key"><svg class="mk" viewBox="0 0 14 14" aria-hidden="true">'
            "{0}</svg>v{1}</span>".format(
                svg_marker(
                    style.shape(version), 7, 7, 4.5, "vs{0}".format(style.step(version))
                ),
                esc(version),
            )
        )
    if extra:
        keys.append(
            '<span class="key"><svg class="mk" viewBox="0 0 14 14" aria-hidden="true">'
            '<circle class="hollow" cx="7" cy="7" r="4.5"/></svg>not comparable '
            "(older vignette code or measured differently)</span>"
            '<span class="key"><svg class="mk" viewBox="0 0 14 14" aria-hidden="true">'
            '<line class="sys" x1="7" x2="7" y1="0" y2="14"/></svg>system changed</span>'
        )
    return '<div class="legend">{0}</div>'.format("".join(keys))


def axis_range(values, min_half=0.12):
    """(low, high) around the values, at least +-min_half of their middle.

    A run history on its own scale, as plot_metrics.py drew it, but never so
    tight that run-to-run noise fills the panel.
    """
    lo, hi = min(values), max(values)
    mid = (lo + hi) / 2.0
    half = max((hi - lo) / 2.0, abs(mid) * min_half, 1e-9) * 1.15
    return max(0.0, mid - half), mid + half


def range_ticks(lo, hi, target=3):
    span = hi - lo
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    first = math.ceil(lo / step) * step
    out, value = [], first
    while value <= hi + 1e-9:
        out.append(round(value, 10))
        value += step
    return out


def svg_run_chart(title, unit, points, style, drifted, system, runs=None, width=340):
    """One metric over a machine's runs, x the run number (no date gaps).

    points: [(ts, version, value, why)] in run order, why as comparable_rows
    gives it (not comparable: hollow). drifted: {ts: description}.
    system: platform_changes() of the machine, [(ts, [(label, old, new)])]:
    a dashed line before the first of these runs after each change. The
    change is dated by its run's first record, usually another vignette's.
    runs: every run's timestamp, in order, metric or not, so a run keeps
    its number on every chart of the vignette (default: the points').
    """
    height = 172
    left, right, top, bottom = 46, 10, 14, 24
    runs = list(runs) if runs else [p[0] for p in points]
    number = {ts: i + 1 for i, ts in enumerate(runs)}
    unit_shown, factor = display_unit(unit, [p[2] for p in points])
    values = [p[2] * factor for p in points]
    lo, hi = axis_range(values)
    n = len(runs)
    bottom_y = height - bottom

    def sx(run):
        return left + (width - left - right) * ((run - 1) / float(max(1, n - 1)))

    def sy(value):
        return top + (bottom_y - top) * (1 - (value - lo) / (hi - lo))

    out = [svg_open(width, height, "{0} per run".format(title))]
    for value in range_ticks(lo, hi):
        y = sy(value)
        out.append(
            '<line class="grid" x1="{0}" x2="{1}" y1="{2:.1f}" y2="{2:.1f}"/>'
            '<text class="tick" x="{3}" y="{4:.1f}" text-anchor="end">{5}</text>'.format(
                left, width - right, y, left - 5, y + 3.5, tick_label(value)
            )
        )
    out.append(
        '<line class="axis" x1="{0}" x2="{1}" y1="{2}" y2="{2}"/>'.format(
            left, width - right, bottom_y
        )
    )
    for run in range_ticks(1, max(2, n), 4):
        if float(run).is_integer() and 1 <= run <= n:
            out.append(
                '<text class="tick" x="{0:.1f}" y="{1}" text-anchor="middle">run {2}'
                "</text>".format(sx(run), height - 7, int(run))
            )
    marks = {}
    for when, changes in system:
        run = next((i + 1 for i, ts in enumerate(runs) if ts >= when), None)
        if run is not None and run > 1:
            marks.setdefault(run, []).extend(changes)
    step = (sx(2) - sx(1)) / 2.0 if n > 1 else 4
    for run, changes in sorted(marks.items()):
        x = sx(run) - step
        tip = "System changed before run {0} ({1}): {2}".format(
            run, short_date(runs[run - 1]), change_text(changes)
        )
        out.append(
            '<g data-tip="{3}"><title>{3}</title><line class="sys" x1="{0:.1f}" '
            'x2="{0:.1f}" y1="{1}" y2="{2}"/><rect class="hit" x="{4:.1f}" y="{1}" '
            'width="10" height="{5}"/></g>'.format(
                x, top - 6, bottom_y, esc(tip), x - 5, bottom_y - top + 6
            )
        )
    for ts, version, value, why in points:
        run = number.get(ts)
        if run is None:
            continue
        note = drifted.get(ts)
        tip = "Run {0} | {1} | v{2} | {3:,.3g} {4}{5}{6}".format(
            run,
            long_date(ts),
            version,
            value * factor,
            unit_shown,
            " | not comparable: " + why if why else "",
            " | DRIFT: " + note if note else "",
        )
        cls = ("hollow vh{0}" if why else "vs{0}").format(style.step(version)) + (
            " drift" if note else ""
        )
        out.append(
            svg_marker(style.shape(version), sx(run), sy(value * factor), 4, cls, tip)
        )
    out.append("</svg>")
    return "".join(out), unit_shown


# ---------------------------------------------------------------------------
# The upgrade table and the biggest changes
# ---------------------------------------------------------------------------
def upgrade_cells(histories, states, tool, old, new):
    """[cell] comparing every active configuration's vignettes at old and new.

    Only like-for-like runs (the same vignette revision at both versions).
    cell: config, vignette, medians, run counts, change (new/old - 1), p.
    """
    cells = []
    for (config, t), vignettes in histories.items():
        if t != tool or states[(config, t)]["retired"]:
            continue
        for vignette, rows in vignettes.items():
            pair = like_for_like(rows, new, old)
            if not pair:
                continue
            before, after, _ = pair
            m_old, m_new = statistics.median(before), statistics.median(after)
            change = (m_new - m_old) / m_old
            p = welch_p(before, after)
            # The t-test compares means; it confirms the median's change only
            # when the mean moved the same way.
            mean_shift = statistics.mean(after) - statistics.mean(before)
            agree = mean_shift == 0 or (mean_shift < 0) == (change < 0)
            cells.append(
                {
                    "config": config,
                    "vignette": vignette,
                    "old_s": m_old,
                    "new_s": m_new,
                    "n_old": len(before),
                    "n_new": len(after),
                    "change": change,
                    "p": p,
                    "cls": change_class(change, p, agree),
                    "agree": agree,
                }
            )
    return cells


def upgrade_pairs(histories, states, tool):
    """{old version: cells} for every version before the pin with comparisons."""
    pin = CURRENT_PINS[tool]
    olds = sorted(
        {
            v
            for (c, t), vignettes in histories.items()
            if t == tool and not states[(c, t)]["retired"]
            for rows in vignettes.values()
            for v in versions_timed(rows)
            if version_key(v) < version_key(pin)
        },
        key=version_key,
        reverse=True,
    )
    out = {}
    for old in olds:
        cells = upgrade_cells(histories, states, tool, old, pin)
        if cells:
            out[old] = cells
    return out


def cell_tip(cell, old, new):
    cls = cell["cls"]
    if cls == "one":
        why = "one run at a version: no way to tell a change from noise yet"
    elif cls == "noise" and not cell.get("agree", True):
        why = "not confirmed: the mean moved the other way (p = {0:.3f})".format(
            cell["p"]
        )
    elif cls == "noise" and cell["p"] < SIG_P:
        why = "below the 10% threshold (p = {0:.3f})".format(cell["p"])
    elif cls == "noise":
        why = "within the noise (p = {0:.3f})".format(cell["p"])
    else:
        why = "beyond the noise (p = {0:.3f})".format(cell["p"])
    return "{0} | {1} | v{2}: {3:,.3g} s ({4} run{5}) | v{6}: {7:,.3g} s ({8} run{9}) | {10}, {11}".format(
        cell["config"],
        vignette_title(cell["vignette"]),
        old,
        cell["old_s"],
        cell["n_old"],
        "" if cell["n_old"] == 1 else "s",
        new,
        cell["new_s"],
        cell["n_new"],
        "" if cell["n_new"] == 1 else "s",
        pct(cell["change"]),
        why,
    )


CHANGE_KEY = (
    "<div class='key'>"
    "<span><i class='fast2'></i>more than 20% faster</span>"
    "<span><i class='fast1'></i>10 to 20% faster</span>"
    "<span><i class='plain'></i>within the noise</span>"
    "<span><i class='slow1'></i>10 to 20% slower</span>"
    "<span><i class='slow2'></i>more than 20% slower</span>"
    "<span class='one'>dotted: one run at a version</span>"
    "</div>"
)


def render_upgrade_table(tool, old, cells, states, configs):
    new = CURRENT_PINS[tool]
    cols = [
        c
        for c in heat_columns(tool, states, configs)
        if any(x["config"] == c for x in cells)
    ]
    missing = [c for c in heat_columns(tool, states, configs) if c not in cols]
    by_key = {(x["config"], x["vignette"]): x for x in cells}
    rows = sorted({x["vignette"] for x in cells}, key=vignette_number)
    out = ["<div class='card'><div class='scroll'><table class='heat matrix'>"]
    out.append(heat_head(cols, tool, states))
    out.append("<tbody>")
    for vignette in rows:
        out.append(
            "<tr><td class='rowh'><a href='{0}'>{1}</a></td>".format(
                esc(vignette_page(vignette)), vignette_label_html(vignette)
            )
        )
        for c in cols:
            cell = by_key.get((c, vignette))
            if not cell:
                out.append(
                    "<td class='c'><span class='none' data-tip='{0}' title='{0}'>"
                    "&middot;</span></td>".format(
                        esc(
                            "{0}: no runs of the same vignette code at both "
                            "versions".format(c)
                        )
                    )
                )
                continue
            tip = cell_tip(cell, old, new)
            out.append(
                "<td class='c'><span class='{0}' data-tip='{1}' title='{1}'>{2}"
                "</span></td>".format(cell["cls"], esc(tip), esc(pct(cell["change"])))
            )
        out.append("</tr>")
    out.append("</tbody></table></div>")
    out.append(CHANGE_KEY)
    if missing:
        out.append(
            "<p class='note'>Not run at v{0} with today's vignettes, so not in the "
            "table: {1}.</p>".format(esc(old), esc(", ".join(missing)))
        )
    out.append("</div>")
    return "".join(out)


def render_biggest(tool, old, cells, limit=12):
    new = CURRENT_PINS[tool]
    real = sorted(
        (c for c in cells if c["cls"] not in ("one", "noise")),
        key=lambda c: -abs(c["change"]),
    )[:limit]
    if not real:
        return (
            "<p class='note'>No change beyond the noise between v{0} and v{1}."
            "</p>".format(esc(old), esc(new))
        )
    top = max(max(abs(c["change"]) for c in real), 0.25)
    out = [
        "<div class='card scroll'><table class='list'><thead><tr><th>Change</th>"
        "<th>Vignette</th><th>Machine</th><th class='num'>v{0}</th>"
        "<th class='num'>v{1}</th><th class='num'>Runs</th><th class='num'>p</th>"
        "</tr></thead><tbody>".format(esc(old), esc(new))
    ]
    for c in real:
        width = abs(c["change"]) / top * 50
        side = "right" if c["change"] < 0 else "left"
        out.append(
            "<tr data-tip='{0}'><td><span class='bar'><b class='{1}' "
            "style='{2}:50%;width:{3:.1f}%'></b></span> <span class='num'>{4}</span>"
            "</td><td><a href='{5}'>{6}</a></td><td>{7}</td><td class='num'>{8:,.3g} s"
            "</td><td class='num'>{9:,.3g} s</td><td class='num'>{10} / {11}</td>"
            "<td class='num'>{12:.3f}</td></tr>".format(
                esc(cell_tip(c, old, new)),
                c["cls"],
                side,
                width,
                esc(pct(c["change"])),
                esc(vignette_page(c["vignette"])),
                esc(vignette_title(c["vignette"])),
                esc(c["config"]),
                c["old_s"],
                c["new_s"],
                c["n_old"],
                c["n_new"],
                c["p"],
            )
        )
    out.append("</tbody></table></div>")
    return "".join(out)


def render_upgrades(histories, states, configs):
    """Each tool's version-pair selector and every pair's views.

    Every pair is rendered; without script the default pair of each tool
    shows and the rest stay hidden, so the page still reads. One selector
    per tool, shown with the tool, so no option ever has to be hidden.
    """
    selects, views = [], []
    for tool in TOOLS:
        pairs = upgrade_pairs(histories, states, tool)
        if not pairs:
            continue
        # The default pair is the one most machines can be compared on.
        default = max(pairs, key=lambda old: (len(pairs[old]), version_key(old)))
        options = []
        for old, cells in pairs.items():
            key = "{0}|{1}".format(tool, old)
            options.append(
                "<option value='{0}'{1}>{2} \u2192 {3} ({4} comparisons)"
                "</option>".format(
                    esc(key),
                    " selected" if old == default else "",
                    esc(old),
                    esc(CURRENT_PINS[tool]),
                    len(cells),
                )
            )
            views.append(
                "<div class='pairview' data-tool='{0}' data-pair='{1}'{2}>"
                "<h3 class='pairtitle'>{0} {3} \u2192 {4}</h3>{5}"
                "<h3>Biggest changes</h3><p class='note'>Changes beyond the noise, "
                "largest first. Select a vignette for its history.</p>{6}</div>".format(
                    esc(tool),
                    esc(key),
                    "" if old == default else " hidden",
                    esc(old),
                    esc(CURRENT_PINS[tool]),
                    render_upgrade_table(tool, old, cells, states, configs),
                    render_biggest(tool, old, cells),
                )
            )
        selects.append(
            "<label class='inline' data-tool='{0}' for='pairsel-{1}'>Compare "
            "<select class='pairsel' id='pairsel-{1}'>{2}</select></label>".format(
                esc(tool), esc(tool.lower()), "".join(options)
            )
        )
    if not views:
        return ""
    return "<div class='controls js-only'>{0}</div>{1}".format(
        "".join(selects), "".join(views)
    )


# ---------------------------------------------------------------------------
# Speed by version: every machine together, then each on its own scale
# ---------------------------------------------------------------------------
def speed_series(histories, states, tool):
    out = []
    for (config, t), vignettes in sorted(
        histories.items(), key=lambda kv: site_order(kv[0][0])
    ):
        if t != tool or states[(config, t)]["retired"]:
            continue
        series = relative_by_version(vignettes)
        if len(series) > 1:
            out.append((config, series))
    return out


def svg_speed_combined(tool, series):
    """Every machine on one axis: x the version, y time against its newest."""
    versions = sorted({v for _, s in series for v, _, _ in s}, key=version_key)
    width, height = 1000, 380
    left, right, top, bottom = 190, 24, 16, 34
    ratios = [r for _, s in series for _, r, _ in s]
    lo = min([0.8] + ratios) - 0.05
    hi = max([1.25] + ratios) + 0.05
    bottom_y = height - bottom

    def sx(version):
        return left + (width - left - right) * (
            versions.index(version) / float(max(1, len(versions) - 1))
        )

    def sy(ratio):
        return top + (bottom_y - top) * (1 - (ratio - lo) / (hi - lo))

    out = [
        svg_open(
            width,
            height,
            "{0}: suite time by version, every machine".format(tool),
            "chart wide",
        )
    ]
    for value in range_ticks(lo, hi, 5):
        out.append(
            '<line class="grid" x1="{0}" x2="{1}" y1="{2:.1f}" y2="{2:.1f}"/>'
            '<text class="tick" x="{0}" y="{3:.1f}">{4}×</text>'.format(
                left + 4, width - right, sy(value), sy(value) - 4, tick_label(value)
            )
        )
    for version in versions:
        out.append(
            '<text class="tick" x="{0:.1f}" y="{1}" text-anchor="middle">v{2}</text>'.format(
                sx(version), height - 10, esc(version)
            )
        )
    out.append(
        '<line class="ref" x1="{0}" x2="{1}" y1="{2:.1f}" y2="{2:.1f}"/>'.format(
            left, width - right, sy(1.0)
        )
    )
    labels = []
    for config, s in series:
        slot = SITE_SLOT[site_of(config)]
        out.append(
            '<path class="line s{0}" d="{1}"/>'.format(
                slot,
                " ".join(
                    "{0}{1:.1f},{2:.1f}".format("M" if i == 0 else "L", sx(v), sy(r))
                    for i, (v, r, _) in enumerate(s)
                ),
            )
        )
        newest = s[-1][0]
        for v, r, count in s:
            tip = "{0} | v{1}: {2:.2f}x the time at v{3}, over {4} vignettes".format(
                config, v, r, newest, count
            )
            out.append(svg_dot(slot, sx(v), sy(r), tip))
        labels.append([sy(s[0][1]), sy(s[0][1]), sx(s[0][0]), config, slot])
    labels.sort()
    for i in range(1, len(labels)):
        labels[i][0] = max(labels[i][0], labels[i - 1][0] + 13)
    overflow = labels[-1][0] - bottom_y if labels else 0
    if overflow > 0:
        for label in labels:
            label[0] -= overflow
    for y, y0, x0, config, slot in labels:
        out.append(
            '<polyline class="leader s{0}" points="{1:.1f},{2:.1f} {3},{4:.1f} {5},{4:.1f}"/>'
            '<text class="dlabel" x="{6}" y="{7:.1f}" text-anchor="end">{8}</text>'.format(
                slot,
                x0 - 6,
                y0,
                left - 30,
                y,
                left - 40,
                left - 44,
                y + 3.5,
                esc(config),
            )
        )
    out.append("</svg>")
    return "".join(out)


def svg_speed_panel(config, series):
    """One machine on its own scale, never narrower than 0.8x to 1.25x."""
    width, height = 260, 140
    left, right, top, bottom = 36, 8, 8, 22
    ratios = [r for _, r, _ in series]
    lo, hi = min([0.8] + ratios), max([1.25] + ratios)
    pad = (hi - lo) * 0.06
    lo, hi = lo - pad, hi + pad
    bottom_y = height - bottom
    versions = [v for v, _, _ in series]

    def sx(version):
        return left + (width - left - right) * (
            versions.index(version) / float(max(1, len(versions) - 1))
        )

    def sy(ratio):
        return top + (bottom_y - top) * (1 - (ratio - lo) / (hi - lo))

    slot = SITE_SLOT[site_of(config)]
    out = [svg_open(width, height, "{0}: suite time by version".format(config))]
    for value in range_ticks(lo, hi):
        out.append(
            '<line class="grid" x1="{0}" x2="{1}" y1="{2:.1f}" y2="{2:.1f}"/>'
            '<text class="tick" x="{3}" y="{4:.1f}" text-anchor="end">{5}×</text>'.format(
                left,
                width - right,
                sy(value),
                left - 4,
                sy(value) + 3.5,
                tick_label(value),
            )
        )
    out.append(
        '<line class="ref" x1="{0}" x2="{1}" y1="{2:.1f}" y2="{2:.1f}"/>'.format(
            left, width - right, sy(1.0)
        )
    )
    for i, v in enumerate(versions):
        if len(versions) <= 5 or i % 2 == 0 or i == len(versions) - 1:
            out.append(
                '<text class="tick" x="{0:.1f}" y="{1}" text-anchor="middle">{2}</text>'.format(
                    sx(v), height - 6, esc(v)
                )
            )
    out.append(
        '<path class="line s{0}" d="{1}"/>'.format(
            slot,
            " ".join(
                "{0}{1:.1f},{2:.1f}".format("M" if i == 0 else "L", sx(v), sy(r))
                for i, (v, r, _) in enumerate(series)
            ),
        )
    )
    newest = series[-1][0]
    for v, r, count in series:
        tip = "{0} | v{1}: {2:.2f}x the time at v{3}, over {4} vignettes".format(
            config, v, r, newest, count
        )
        out.append(svg_dot(slot, sx(v), sy(r), tip))
    out.append("</svg>")
    return "".join(out)


def render_speed(histories, states):
    out = []
    for tool in TOOLS:
        series = speed_series(histories, states, tool)
        compared = {c for c, _ in series}
        without = sorted(
            (
                c
                for (c, t), st in histories.items()
                if t == tool and not states[(c, t)]["retired"] and c not in compared
            ),
            key=site_order,
        )
        note = (
            "<p class='note'>Not charted: {0}. Each has runs of today's vignettes "
            "at one version only, so there is nothing to compare yet.</p>".format(
                esc(", ".join(without))
            )
            if without
            else ""
        )
        if not series:
            if without:
                out.append(
                    "<div data-tool='{0}'><h3>{0}</h3>{1}</div>".format(esc(tool), note)
                )
            continue
        sites = sorted({site_of(c) for c, _ in series}, key=SITES.index)
        panels = "".join(
            "<div class='panel'><h4><span class='swatch s{0}'></span>{1}</h4>"
            "<div class='sub'>{2} &middot; now v{3}</div>{4}</div>".format(
                SITE_SLOT[site_of(c)],
                esc(c),
                esc(site_of(c)),
                esc(s[-1][0]),
                svg_speed_panel(c, s),
            )
            for c, s in series
        )
        out.append(
            "<div data-tool='{0}'><h3>{0}</h3>{1}<div class='card scroll'>{2}</div>"
            "{4}<h4 class='sub-h'>Each machine on its own scale</h4>"
            "<div class='panels'>{3}</div></div>".format(
                esc(tool),
                legend([(SITE_SLOT[s], s) for s in sites]),
                svg_speed_combined(tool, series),
                panels,
                note,
            )
        )
    return "".join(out)


# ---------------------------------------------------------------------------
# System changes on the index
# ---------------------------------------------------------------------------
def render_system_changes(histories, states, limit=20):
    rows = []
    by_config = {}
    for (config, tool), vignettes in histories.items():
        if states[(config, tool)]["retired"]:
            continue
        # (tool, vignette): one tool's history must not replace the other's.
        by_config.setdefault(config, {}).update(
            ((tool, v), rows) for v, rows in vignettes.items()
        )
    for config, vignettes in by_config.items():
        for ts, changes in platform_changes(vignettes):
            for label, old, new in changes:
                rows.append((ts, config, label, old, new))
    if not rows:
        return "<p class='note'>No system change recorded yet.</p>"
    rows.sort(key=lambda r: r[0], reverse=True)
    return (
        "<div class='card scroll'><table class='list'><thead><tr><th>Date</th>"
        "<th>Machine</th><th>Setting</th><th>Was</th><th>Now</th></tr></thead>"
        "<tbody>{0}</tbody></table></div>".format(
            "".join(
                "<tr><td class='num'>{0}</td><td><a href='{1}'>{2}</a></td><td>{3}</td>"
                "<td class='muted'>{4}</td><td>{5}</td></tr>".format(
                    esc(short_date(ts)),
                    esc(page_name(config)),
                    esc(config),
                    esc(label),
                    esc(old),
                    esc(new),
                )
                for ts, config, label, old, new in rows[:limit]
            )
        )
    )


# ---------------------------------------------------------------------------
# Per-vignette pages: one vignette on every machine
# ---------------------------------------------------------------------------
def vignette_page(vignette):
    return "v-{0}.html".format(_safe(vignette))


def vignette_label_html(vignette):
    n = vignette_number(vignette)
    if n is None or n not in ABOUT:
        return esc(vignette)
    return "<span class='n'>ex{0:02d}</span>{1}".format(n, esc(ABOUT[n][0]))


def render_vignette_page(tool, vignette, histories, states, generated, style=None):
    """One vignette on every active machine. style: the tool's VersionStyle
    (build_site's), so a version has the same marker on every page."""
    n = vignette_number(vignette)
    about = ABOUT.get(n, ("", ""))[1]
    configs = sorted(
        (
            c
            for (c, t), vs in histories.items()
            if t == tool and vignette in vs and not states[(c, t)]["retired"]
        ),
        key=site_order,
    )
    shown = {
        drift.tool_version(rec) or "unknown"
        for c in configs
        for _, rec in histories[(c, tool)][vignette]
    }
    style = style or VersionStyle(shown)
    latest = []
    for c in configs:
        for v, ts, record, _, _ in states[(c, tool)]["latest"]:
            if v == vignette:
                status, detail = status_of(record)
                latest.append(
                    "<span class='chip {0}' title='{1}'><span class='sym'>{2}</span> "
                    "{3} v{4}</span>".format(
                        status_class(status),
                        esc(detail),
                        STATUS[status][0],
                        esc(c),
                        esc(drift.tool_version(record)),
                    )
                )
    # Per machine once: its drift and its system changes.
    drifts = {c: drift_by_record(histories[(c, tool)][vignette]) for c in configs}
    # The machine's whole record, both tools: a change first seen in the
    # other tool's runs is still a change.
    systems = {
        c: platform_changes(
            {
                (t, v): rows
                for (cc, t), vs in histories.items()
                if cc == c
                for v, rows in vs.items()
            }
        )
        for c in configs
    }
    sections = []
    for metric, title, unit in (
        ("execution_time", "Execution time", "s"),
        ("memory_usage_mb", "Peak memory", "MB"),
    ):
        panels = []
        for c in configs:
            rows = histories[(c, tool)][vignette]
            series = comparable_rows(rows, metric)
            if not series:
                continue
            drifted = {
                ts: drift.describe(r)
                for ts, (results, _) in drifts[c].items()
                for r in results
                if r["metric"] == metric
            }
            system = systems[c]
            points = [
                (ts, drift.tool_version(rec) or "unknown", value, why)
                for ts, rec, value, why in series
            ]
            svg, unit_shown = svg_run_chart(
                title, unit, points, style, drifted, system, [ts for ts, _ in rows]
            )
            panels.append(
                "<div class='panel'><h4><span class='swatch s{0}'></span>"
                "<a href='{1}#{2}-{3}'>{4}</a></h4><div class='sub'>{5} runs &middot; "
                "{6} to {7} &middot; {8}</div>{9}</div>".format(
                    SITE_SLOT[site_of(c)],
                    esc(page_name(c)),
                    esc(tool),
                    esc(vignette),
                    esc(c),
                    len(points),
                    esc(short_date(points[0][0])),
                    esc(short_date(points[-1][0])),
                    esc(unit_shown),
                    svg,
                )
            )
        if panels:
            sections.append(
                "<h2>{0}</h2><div class='panels wide'>{1}</div>".format(
                    esc(title), "".join(panels)
                )
            )
    body = (
        "<p class='crumbs'><a href='index.html'>Results</a> &rsaquo; {0}</p>"
        "<h1>{0} {1}</h1><p class='lede'>{2}</p>"
        "<p><a href='../gallery/#{6}'>Baseline images in the gallery</a> &middot; "
        "source: <a href='{7}/tree/master/{8}/{9}'>{9}</a></p>"
        "<h2>Latest result on each machine</h2><div class='chips'>{3}</div>"
        "<p class='note'>One panel per machine, x its own run number, so months "
        "without runs leave no gaps. Colour and shape are the tool version. Hollow: "
        "not comparable with the latest run. A dashed amber line is a system change "
        "(OS, kernel, GPU driver); hover it for what changed.</p>{4}{5}".format(
            esc(tool),
            esc(vignette_title(vignette)),
            esc(about),
            "".join(latest),
            version_legend(style, versions=shown),
            "".join(sections),
            "{0}-ex{1:02d}".format(tool.lower(), n if n is not None else 0),
            "https://github.com/jameskress/Visualization_Vignettes",
            esc(dict(SUITES)[tool]),
            esc(vignette),
        )
    )
    return page("{0} {1}".format(tool, vignette_title(vignette)), body, generated)


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------
HOW_TO_READ = (
    (
        "Upgrade table",
        "how much each vignette's time changed between two tool versions on each "
        "machine, from runs of the same vignette code. Colour means the change is "
        "real: at least 10%, and a Welch t-test on the repeated runs says it is "
        "unlikely to be noise.",
    ),
    (
        "Blue, red",
        "blue is faster with the newer version, red is slower; darker is more "
        "than 20%. An uncoloured number is within the noise, and a dotted one had "
        "a single run at a version, so it cannot be told from noise yet.",
    ),
    (
        "Speed by version",
        "each machine's whole suite at a version against its current one (the 1x "
        "line). Above the line, that older version was slower.",
    ),
    (
        "Run history",
        "on vignette and machine pages, x is the machine's own run number, colour "
        "and shape the tool version. Hollow: not comparable with the latest run "
        "(older vignette code, or measured differently). A dashed amber line: the "
        "OS, kernel or GPU driver changed.",
    ),
    (
        "\u2713 \u2717",
        "pass / fail over every comparison gate (image, numbers, CSV); \u25cf \u25cb "
        "for older runs that only say whether the vignette finished. Stale: no run "
        "in {0} days, or not on the pinned build.",
    ),
)


def how_to_read(open_=True):
    return (
        "<details class='card howto-box'{1}><summary><strong>How to read this"
        "</strong></summary><dl class='howto'>{0}</dl></details>".format(
            "".join(
                "<div><dt>{0}</dt><dd>{1}</dd></div>".format(
                    key, esc(text.format(STALE_DAYS))
                )
                for key, text in HOW_TO_READ
            ),
            " open" if open_ else "",
        )
    )


def active_configs(states, configs, tool=None):
    """Configurations with a non-retired state (for `tool`, or any tool)."""
    tools = (tool,) if tool else TOOLS
    return [
        c
        for c in configs
        if any((c, t) in states and not states[(c, t)]["retired"] for t in tools)
    ]


def render_index(histories, states, generated):
    configs = sorted({config for config, _ in histories}, key=site_order)
    active = active_configs(states, configs)
    retired = [c for c in configs if c not in active]
    totals = dict.fromkeys(STATUS_ORDER, 0)
    drifting, last = 0, ""
    for (config, _), state in states.items():
        if state["retired"]:
            continue
        for key, count in state["counts"].items():
            totals[key] += count
        drifting += state["drifting"] or 0
        last = max(last, state["last_ts"])
    stale = [
        c
        for c in active
        if any((c, t) in states and states[(c, t)]["stale"] for t in TOOLS)
    ]
    vignette_count = {
        tool: len({v for (c, t), vs in histories.items() if t == tool for v in vs})
        for tool in TOOLS
    }
    pins = "ParaView {0}, VisIt {1}".format(
        CURRENT_PINS["ParaView"], CURRENT_PINS["VisIt"]
    )
    failing = [
        "{0} {1}".format(c, t)
        for (c, t), st in sorted(states.items())
        if not st["retired"] and (st["counts"]["fail"] or st["counts"]["run_failed"])
    ]
    body = [
        "<p class='eyebrow'>Regression suite results</p>",
        "<h1>Is every vignette still right, and still fast?</h1>",
        "<p class='lede'>{0} ParaView and {1} VisIt vignettes on {2} active "
        "configurations at {3} sites, last run {4}.</p>".format(
            vignette_count["ParaView"],
            vignette_count["VisIt"],
            len(active),
            len({site_of(c) for c in active}),
            esc(long_date(last)) if last else "never",
        ),
        "<div class='summary'><span><span class='big'>{0}</span><span class='muted'>"
        " / {1}</span> latest results pass</span>{2}{3}{4}<span class='pill'>Pinned: "
        "{5}</span></div>".format(
            totals["pass"],
            sum(totals.values()),
            "<span class='pill'><span class='dot bad'></span>{0}</span>".format(
                esc("failing: " + ", ".join(failing)) if failing else "no failures"
            ),
            "<span class='pill'><span class='dot warn'></span>{0} stale "
            "configuration{1}</span>".format(
                len(stale), "" if len(stale) == 1 else "s"
            ),
            "<span class='pill'>{0} drift warning{1}</span>".format(
                drifting, "" if drifting == 1 else "s"
            ),
            esc(pins),
        ),
        how_to_read(),
        "<div class='controls js-only'><div class='seg' role='group' aria-label='Tool'"
        " id='toolseg'>{0}</div></div>".format(
            "".join(
                "<button type='button' data-tool='{0}' aria-pressed='{1}'>{0}</button>".format(
                    t, "true" if t == TOOLS[0] else "false"
                )
                for t in TOOLS
            )
        ),
        "<section><h2>What the upgrade changed</h2>",
        render_upgrades(histories, states, configs),
        "</section>",
        "<section><h2>Speed by version</h2><p class='note'>The whole suite's time "
        "at each version against the same machine's current version (the 1&times; "
        "line), over the vignettes both versions ran unchanged. The combined chart "
        "puts every machine on one axis; the panels give each its own scale, never "
        "narrower than 0.8&times; to 1.25&times;.</p>",
        render_speed(histories, states),
        "</section>",
        "<section><h2>Did everything pass?</h2><p class='note'>The latest run of "
        "each vignette on each configuration. Select a configuration for its "
        "history.</p>",
    ]
    for tool in TOOLS:
        body.append(
            "<div data-tool='{0}'>{1}</div>".format(
                esc(tool), render_heatmap(tool, histories, states, configs)
            )
        )
    body.append("</section>")
    body.append(
        "<section><h2>System changes</h2><p class='note'>OS, kernel, GPU driver "
        "and CPU governor changes read from the records, newest first. They are "
        "marked on every run history, so a step there can be told from a tool "
        "change.</p>{0}</section>".format(render_system_changes(histories, states))
    )
    body.append(
        "<section><h2>Which machine is fastest?</h2><p class='note'>Each "
        "vignette's latest time on every active configuration at the pinned build, "
        "on a log scale, from runs of the same vignette code.</p>"
    )
    for tool in TOOLS:
        body.append(
            "<div data-tool='{0}'>{1}</div>".format(
                esc(tool), render_dot_plot(tool, histories, states)
            )
        )
    body.append("</section>")
    body.append(
        "<section><h2>Configurations</h2><p class='note'>Drift <em>n/a</em>: no "
        "vignette there has three earlier runs at the same version and measurement "
        "yet.</p>"
    )
    body.append(render_config_table(states, active))
    body.append("</section>")
    if retired:
        body.append(
            "<section><h2>Retired configurations</h2><p class='note'>Hardware that "
            "left the suite (<code>{0}</code>). Their history and pages stay; they "
            "are left out of the charts above.</p>".format(
                esc(RETIRED_FILE.replace(os.sep, "/"))
            )
        )
        body.append(render_retired_table(states, retired))
        body.append("</section>")
    return page("Vignette results", "".join(body), generated)


def heat_columns(tool, states, configs):
    return [
        c for c in configs if (c, tool) in states and not states[(c, tool)]["retired"]
    ]


def heat_head(cols, tool, states, extra_rows=""):
    """The site row and the rotated configuration row of a vignette table."""
    out = ["<thead><tr><th></th>"]
    for site in SITES:
        span = sum(1 for c in cols if site_of(c) == site)
        if span:
            # A one- or two-column site gets a short label so it does not
            # widen its columns; the full name is in the tooltip.
            short = site if span > 2 else site[:2] + "."
            out.append(
                "<th class='site' colspan='{0}' title='{1}'>{2}</th>".format(
                    span, esc(site), esc(short)
                )
            )
    out.append("</tr><tr><th>Vignette</th>")
    for c in cols:
        stale = states[(c, tool)]["stale"]
        out.append(
            "<th class='col{0}' title='{1}'><span><a href='{2}#{3}'>{4}</a></span></th>".format(
                " stale" if stale else "",
                esc("stale: " + "; ".join(stale) if stale else c),
                esc(page_name(c)),
                esc(tool),
                esc(c),
            )
        )
    out.append("</tr>{0}</thead>".format(extra_rows))
    return "".join(out)


def render_heatmap(tool, histories, states, configs):
    cols = heat_columns(tool, states, configs)
    if not cols:
        return ""
    vignettes = sorted(
        {v for c in cols for v in histories[(c, tool)]}, key=vignette_number
    )
    out = [
        "<div class='card'><h3>{0}</h3>{1}".format(esc(tool), status_legend()),
        "<div class='scroll tall'><table class='heat'>",
        heat_head(cols, tool, states),
        "<tbody>",
    ]
    for v in vignettes:
        out.append("<tr><td class='rowh'>{0}</td>".format(esc(v)))
        for c in cols:
            entry = next((e for e in states[(c, tool)]["latest"] if e[0] == v), None)
            if entry is None:
                out.append(
                    "<td class='hm' data-tip='{0}'><span class='cell none'>&middot;"
                    "</span></td>".format(
                        esc("{0} | {1} | never recorded".format(v, c))
                    )
                )
                continue
            _, ts, rec, drifted, _ = entry
            status, detail = status_of(rec)
            seconds = rec.get("execution_time")
            tip = "{0} | {1} | {2} | v{3} | {4}{5}{6}".format(
                v,
                c,
                long_date(ts),
                drift.tool_version(rec),
                detail,
                " | drift: " + ", ".join(d["label"] for d in drifted)
                if drifted
                else "",
                " | {0:.3g} s".format(seconds) if is_number(seconds) else "",
            )
            out.append(
                "<td class='hm{0}' data-tip='{1}'><span class='cell c-{2}'>{3}"
                "</span></td>".format(
                    " drift" if drifted else "",
                    esc(tip),
                    status_class(status),
                    STATUS[status][0],
                )
            )
        out.append("</tr>")
    out.append("</tbody></table></div></div>")
    return "".join(out)


def render_retired_table(states, configs):
    out = [
        "<div class='card scroll'><table><thead><tr><th>Configuration</th>"
        "<th>Tool</th><th>Retired</th><th>Why</th><th>Versions it ran</th>"
        "<th>Last run</th></tr></thead><tbody>"
    ]
    for c in configs:
        for tool in TOOLS:
            state = states.get((c, tool))
            if not state:
                continue
            versions = state["versions"]
            out.append(
                "<tr><td><a href='{0}#{1}'>{2}</a></td><td>{1}</td><td>{3}</td>"
                "<td>{4}</td><td>{5}</td><td>{6}</td></tr>".format(
                    esc(page_name(c)),
                    esc(tool),
                    esc(c),
                    esc(state["retired"].get("since")),
                    esc(state["retired"].get("reason") or ""),
                    esc(", ".join("v" + v for v in versions)),
                    esc(short_date(state["last_ts"])),
                )
            )
    out.append("</tbody></table></div>")
    return "".join(out)


def render_dot_plot(tool, histories, states):
    pin = CURRENT_PINS[tool]
    configs = sorted(
        (
            c
            for (c, t), s in states.items()
            if t == tool and not s["stale"] and not s["retired"]
        ),
        key=site_order,
    )
    vignettes = sorted(
        {v for c in configs for v in histories[(c, tool)]}, key=vignette_number
    )
    rows, table = [], []
    for v in vignettes:
        dots = []
        for c in configs:
            hist = histories[(c, tool)].get(v)
            if not hist:
                continue
            rec = latest_at(hist, pin)[1]
            if (
                drift.tool_version(rec) == pin
                and run_ok(rec)
                and is_number(rec.get("execution_time"))
            ):
                dots.append((c, float(rec["execution_time"]), rec.get("_rev", 0)))
        # One revision per vignette: machines that ran different code are
        # not set side by side. The newest known revision wins; uncertain
        # ones (negative) never take part.
        known = [r for _, _, r in dots if r >= 0]
        rev = max(known) if known else None
        dots = [(c, t) for c, t, r in dots if r == rev]
        table.extend((v, c, t) for c, t in dots)
        rows.append((v, dots))
    svg = svg_dot_plot(tool, rows)
    if not svg:
        return ""
    sites = sorted({site_of(c) for _, c, _ in table}, key=SITES.index)
    return (
        "<div class='card'><h3>{0} v{1}</h3>{2}<div class='scroll'>{3}</div>"
        "<details><summary>table</summary><div class='scroll tall'><table><thead><tr>"
        "<th>Vignette</th><th>Configuration</th><th class='num'>Seconds</th></tr>"
        "</thead><tbody>{4}</tbody></table></div></details></div>".format(
            esc(tool),
            esc(pin),
            legend([(SITE_SLOT[s], s) for s in sites]),
            svg,
            "".join(
                "<tr><td>{0}</td><td>{1}</td><td class='num'>{2}</td></tr>".format(
                    esc(v), esc(c), fmt(s)
                )
                for v, c, s in table
            ),
        )
    )


def render_config_table(states, configs):
    out = [
        "<div class='card scroll tall'><table><thead><tr><th>Site</th>"
        "<th>Configuration</th><th>Tool</th><th>Version of last run</th>"
        "<th>Last run</th><th>Latest run per vignette</th><th class='num'>Drift</th>"
        "</tr></thead><tbody>"
    ]
    for c in configs:
        for tool in TOOLS:
            state = states.get((c, tool))
            if not state:
                continue
            chips = " ".join(
                "{0} {1}".format(status_chip(k), state["counts"][k])
                for k in STATUS_ORDER
                if state["counts"][k]
            )
            stale = state["stale"]
            if state["drifting"] is None:
                drift_cell = "<span title='too few comparable runs to judge'>n/a</span>"
            elif state["drifting"]:
                drift_cell = "<span class='drift-flag'>{0}</span>".format(
                    state["drifting"]
                )
            else:
                drift_cell = "0"
            out.append(
                "<tr class='{0}'><td>{1}</td><td><a href='{2}#{3}'>{4}</a>{5}</td>"
                "<td>{3}</td><td>{6}</td><td>{7}</td><td>{8}</td>"
                "<td class='num'>{9}</td></tr>".format(
                    "stale" if stale else "",
                    esc(site_of(c)),
                    esc(page_name(c)),
                    esc(tool),
                    esc(c),
                    "<span class='badge stale' title='{0}'>stale</span>".format(
                        esc("; ".join(stale))
                    )
                    if stale
                    else "",
                    esc(state["version"] or ""),
                    esc(short_date(state["last_ts"])),
                    chips,
                    drift_cell,
                )
            )
    out.append("</tbody></table></div>")
    return "".join(out)


# ---------------------------------------------------------------------------
# Configuration pages
# ---------------------------------------------------------------------------
NOT_RECORDED = "<span class='muted' title='recorded from metrics schema 6'>-</span>"


def baseline_text(record):
    baseline = record.get("baseline")
    if not isinstance(baseline, dict):
        return NOT_RECORDED
    bits = []
    if baseline.get("commit"):
        bits.append(baseline["commit"])
    if baseline.get("ref"):
        bits.append("ref " + str(baseline["ref"]))
    sources = baseline.get("image_sources") or {}
    if sources:
        bits.append(
            ", ".join("{0}: {1}".format(k, v) for k, v in sorted(sources.items()))
        )
    return esc("; ".join(bits)) or NOT_RECORDED


def build_text(record):
    build = record.get("build")
    if not isinstance(build, dict):
        return NOT_RECORDED
    bits = [build.get("id") or ""]
    if build.get("opengl_window"):
        bits.append(
            str(build["opengl_window"]).replace("vtk", "").replace("RenderWindow", "")
        )
    if build.get("launcher"):
        bits.append(str(build["launcher"]))
    return esc(" ".join(b for b in bits if b)) or NOT_RECORDED


def verdict_text(verdicts, key):
    if not verdicts:
        return NOT_RECORDED
    return esc(verdicts.get(key) or "")


def render_vignette_card(tool, vignette, rows, style, system):
    """One vignette on one machine: its result strip, charts and every run.

    style: the tool's VersionStyle; system: this machine's
    platform_changes(), marked on every chart.
    """
    drifts = drift_by_record(rows)
    out = [
        "<div class='card' id='{0}-{1}'><h3><a href='{2}'>{3}</a> "
        "<span class='muted'>{1}</span></h3>".format(
            esc(tool),
            esc(vignette),
            esc(vignette_page(vignette)),
            esc(vignette_title(vignette)),
        )
    ]
    cells = []
    for ts, record in rows[-60:]:
        status, detail = status_of(record)
        drifted = drifts.get(ts, ([], False))[0]
        tip = "{0} | v{1} | {2}{3}".format(
            long_date(ts),
            drift.tool_version(record),
            detail,
            (" | drift: " + ", ".join(d["label"] for d in drifted)) if drifted else "",
        )
        cells.append(
            "<span class='cell c-{0}{1}' data-tip='{2}' title='{2}'>{3}</span>".format(
                status_class(status),
                " drift" if drifted else "",
                esc(tip),
                STATUS[status][0],
            )
        )
    out.append(
        "<div class='scroll'><div class='strip'>{0}</div></div>".format("".join(cells))
    )

    charts, versions_seen, hidden = [], set(), []
    for metric, title, unit, floor in CHARTS:
        series = comparable_rows(rows, metric)
        if not series:
            continue
        if max(value for _, _, value, _ in series) < floor:
            hidden.append(title)
            continue
        drifted = {
            ts: drift.describe(r)
            for ts, (results, _) in drifts.items()
            for r in results
            if r["metric"] == metric
        }
        points = [
            (ts, drift.tool_version(rec) or "unknown", value, why)
            for ts, rec, value, why in series
        ]
        versions_seen.update(p[1] for p in points)
        svg, unit_shown = svg_run_chart(
            title, unit, points, style, drifted, system, [ts for ts, _ in rows]
        )
        charts.append(
            "<div class='chart-box'><h4>{0} <span class='unit'>({1})</span></h4>"
            "{2}</div>".format(esc(title), esc(unit_shown), svg)
        )
    if charts:
        out.append(version_legend(style, versions=versions_seen))
        out.append("<div class='grid-charts'>{0}</div>".format("".join(charts)))
        out.append(
            "<div class='note'>x is this machine's run number, colour and shape the "
            "tool version. Hollow: not comparable with the latest run (older vignette "
            "code, or measured differently).{0}</div>".format(
                " Not charted, every value under 1 unit: {0}.".format(
                    esc(", ".join(hidden))
                )
                if hidden
                else ""
            )
        )

    out.append(
        "<details><summary>All {0} runs</summary><div class='scroll tall'><table>"
        "<thead><tr><th>Date</th><th>Run id</th><th>Version</th><th>Result</th>"
        "<th class='num'>Time (s)</th><th class='num'>CPU (s)</th>"
        "<th class='num'>Memory (MB)</th><th class='num'>Read (MB)</th>"
        "<th class='num'>Write (MB)</th><th class='num'>Energy (J)</th>"
        "<th class='num'>Load</th><th>Vignette revision</th><th>Build</th>"
        "<th>Baseline</th>"
        "<th>Schema</th><th>Scope (CPU / memory)</th></tr></thead><tbody>".format(
            len(rows)
        )
    )
    for ts, record in reversed(rows):
        status, detail = status_of(record)
        read = record.get("io_read_mb", record.get("disk_read_mb"))
        write = record.get("io_write_mb", record.get("disk_write_mb"))
        scope = (
            "{0} / {1}".format(
                record.get("cpu_measurement_scope") or "",
                record.get("memory_measurement_scope") or "",
            )
            if record.get("cpu_measurement_scope")
            else ""
        )
        out.append(
            "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td>"
            "<td class='num'>{4}</td><td class='num'>{5}</td><td class='num'>{6}</td>"
            "<td class='num'>{7}</td><td class='num'>{8}</td><td class='num'>{9}</td>"
            "<td class='num'>{10}</td><td>{11}</td><td>{12}</td><td>{13}</td>"
            "<td>{14}</td><td>{15}</td></tr>".format(
                esc(str(ts)[:19].replace("T", " ")),
                esc(record.get("run_id") or ""),
                esc(drift.tool_version(record)),
                status_chip(status, detail),
                fmt(record.get("execution_time")),
                fmt(record.get("cpu_seconds")),
                fmt(record.get("memory_usage_mb"), 0),
                fmt(read),
                fmt(write),
                fmt(record.get("energy_joules"), 0),
                fmt(record.get("load_1m_at_start")),
                esc(record.get("_rev_label") or ""),
                build_text(record),
                baseline_text(record),
                esc(record.get("metrics_schema") or ""),
                esc(scope),
            )
        )
    out.append("</tbody></table></div></details></div>")
    return "".join(out)


def render_tool_section(tool, vignettes, state, style, system):
    stale = state["stale"]
    out = [
        "<h2 id='{0}'>{0}{1}</h2>".format(
            esc(tool),
            "<span class='badge stale'>stale: {0}</span>".format(esc("; ".join(stale)))
            if stale
            else "",
        ),
        "<div class='card scroll tall'><h3>Latest run of each vignette</h3><table>"
        "<thead><tr><th>Vignette</th><th>Date</th><th>Version</th><th>Result</th>"
        "<th>Image</th><th>Numeric</th><th class='num'>Time (s)</th>"
        "<th class='num'>CPU (s)</th><th class='num'>Memory (MB)</th>"
        "<th>Build</th><th>Baseline</th><th>Drift</th></tr></thead><tbody>",
    ]
    for vignette, ts, record, drifted, judged in state["latest"]:
        status, detail = status_of(record)
        verdicts = record.get("verdicts")
        if drifted:
            drift_cell = " ".join(
                "<span class='drift-flag' title='{0}'>{1}</span>".format(
                    esc(drift.describe(d)), esc(d["label"])
                )
                for d in drifted
            )
        elif judged:
            drift_cell = "none"
        else:
            drift_cell = (
                "<span class='muted' title='too few comparable runs'>n/a</span>"
            )
        out.append(
            "<tr><td><a href='#{0}-{1}'>{13}</a></td><td>{2}</td><td>{3}</td>"
            "<td>{4}</td><td>{5}</td><td>{6}</td><td class='num'>{7}</td>"
            "<td class='num'>{8}</td><td class='num'>{9}</td><td>{10}</td>"
            "<td>{11}</td><td>{12}</td></tr>".format(
                esc(tool),
                esc(vignette),
                esc(short_date(ts)),
                esc(drift.tool_version(record)),
                status_chip(status, detail),
                verdict_text(verdicts, "image"),
                verdict_text(verdicts, "numeric"),
                fmt(record.get("execution_time")),
                fmt(record.get("cpu_seconds")),
                fmt(record.get("memory_usage_mb"), 0),
                build_text(record),
                baseline_text(record),
                drift_cell,
                esc(vignette_title(vignette)),
            )
        )
    out.append("</tbody></table></div>")
    for entry in state["latest"]:
        out.append(
            render_vignette_card(tool, entry[0], vignettes[entry[0]], style, system)
        )
    return "".join(out)


def render_config(config, tools, states, styles, generated):
    retired = next(
        (
            states[(config, t)]["retired"]
            for t in tools
            if states[(config, t)]["retired"]
        ),
        None,
    )
    system = platform_changes(
        {(t, v): r for t, vs in tools.items() for v, r in vs.items()}
    )
    body = [
        "<p class='crumbs'><a href='index.html'>Results</a> &rsaquo; {0}</p>".format(
            esc(config)
        ),
        "<h1>{0}</h1><p class='lede'>Site: {1}. Tools: {2}.</p>".format(
            esc(config),
            esc(site_of(config)),
            " ".join(
                "<a href='#{0}'>{0}</a>".format(esc(t)) for t in TOOLS if t in tools
            ),
        ),
        "<p class='banner'>Retired {0}{1}. Kept for its history; no runs are "
        "expected.</p>".format(
            esc(retired.get("since")),
            ": " + esc(retired["reason"]) if retired.get("reason") else "",
        )
        if retired
        else "",
        how_to_read(open_=False),
        status_legend(),
    ]
    for tool in TOOLS:
        if tool in tools:
            body.append(
                render_tool_section(
                    tool, tools[tool], states[(config, tool)], styles[tool], system
                )
            )
    return page("{0} results".format(config), "".join(body), generated)


def public_record(config, tool, vignette, timestamp, record):
    """A record as published in records.json: everything but the host name."""
    record = dict(record)
    record.pop("_rev", None)
    revision = record.pop("_rev_label", None)
    if revision:
        record["vignette_revision"] = revision
    info = dict(record.get("machine_info") or {})
    info.pop("node", None)
    record["machine_info"] = info
    record.update(
        configuration=config,
        site=site_of(config),
        tool=tool,
        vignette=vignette,
        timestamp=timestamp,
    )
    return record


def build_site(out_dir, repo_root=REPO_ROOT, generated=None, now=None):
    histories = load_histories(repo_root)
    revisions = tag_revisions(histories, repo_root)
    if not revisions.available:
        print(
            "no git history at {0}: vignette revisions unknown, every run is "
            "compared".format(repo_root),
            file=sys.stderr,
        )
    histories = publish_names(histories)
    now = now or datetime.datetime.now()
    generated = generated or now.strftime("%Y-%m-%d %H:%M")
    os.makedirs(out_dir, exist_ok=True)

    # PUBLIC_NAMES directly, not public_name: a retired host-named entry
    # whose history is gone publishes nothing and must not stop the build.
    retired = {
        public_text(config): scrub(entry)
        for config, entry in load_retired(repo_root).items()
    }
    states = {
        key: config_state(key[1], vs, now, retired.get(key[0]))
        for key, vs in histories.items()
    }
    styles = {
        tool: VersionStyle(
            drift.tool_version(rec) or "unknown"
            for (_, t), vignettes in histories.items()
            if t == tool
            for rows in vignettes.values()
            for _, rec in rows
        )
        for tool in TOOLS
    }

    PAGE_NAMES.clear()
    PAGE_NAMES.update(page_names({config for config, _ in histories}))
    with open(os.path.join(out_dir, "index.html"), "w") as handle:
        handle.write(render_index(histories, states, generated))

    by_config = {}
    for (config, tool), vignettes in histories.items():
        by_config.setdefault(config, {})[tool] = vignettes
    for config, tools in by_config.items():
        with open(os.path.join(out_dir, page_name(config)), "w") as handle:
            handle.write(render_config(config, tools, states, styles, generated))
    vignette_pages = 0
    for tool in TOOLS:
        names = {v for (c, t), vs in histories.items() if t == tool for v in vs}
        for vignette in sorted(names, key=vignette_number):
            if not VIGNETTE_RE.match(vignette):
                continue
            with open(os.path.join(out_dir, vignette_page(vignette)), "w") as handle:
                handle.write(
                    render_vignette_page(
                        tool, vignette, histories, states, generated, styles[tool]
                    )
                )
            vignette_pages += 1

    records = [
        public_record(config, tool, vignette, ts, rec)
        for (config, tool), vignettes in sorted(histories.items())
        for vignette, rows in sorted(vignettes.items())
        for ts, rec in rows
    ]
    with open(os.path.join(out_dir, "records.json"), "w") as handle:
        json.dump(records, handle, indent=1, sort_keys=True)
        handle.write("\n")
    # GitHub Pages runs Jekyll on an upload unless told not to.
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    return len(by_config), len(records)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write the static results dashboard.")
    parser.add_argument("--out", default="_site", help="Output directory.")
    parser.add_argument(
        "--repo", default=REPO_ROOT, help="Repository root to read records from."
    )
    args = parser.parse_args(argv)
    pages, records = build_site(args.out, args.repo)
    print(
        "wrote {0} configuration pages and {1} records to {2}".format(
            pages, records, args.out
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
