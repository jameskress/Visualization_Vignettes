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
#   index.html        the whole suite at a glance: a status heatmap of
#                     vignette by configuration, each machine's time across
#                     tool versions, every vignette's change in its machine's
#                     last upgrade, each vignette's time across machines on
#                     the current build, and tables of the active and the
#                     retired configurations
#   <config>.html     per vignette: run history, telemetry charts with the
#                     tool version as the x axis, drift, builds and
#                     baselines, every run
#   records.json      every record, flattened, for analysis elsewhere
#
# Charts put the tool version on the x axis, not the date: a configuration
# runs on a handful of days a year, and a date axis left most of each chart
# blank. Dates are in the tooltips and the tables.
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
SCOPE_FIELD = {metric: spec[4] for metric, spec in drift.METRICS.items()}

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

# Diverging steps for a vignette's median time at its machine's newest
# version over its median at the version before: blue faster, red slower,
# grey within about 10%. Upper edges of the ratio, symmetric in log terms.
CHANGE_BINS = [
    (0.5, "r-3", "2x faster or more"),
    (0.8, "r-2", "20 to 50% faster"),
    (0.91, "r-1", "10 to 20% faster"),
    (1.1, "r0", "within 10%"),
    (1.25, "r1", "10 to 25% slower"),
    (2.0, "r2", "25% to 2x slower"),
    (float("inf"), "r3", "2x slower or more"),
]


def site_of(config):
    lowered = config.lower()
    if lowered.startswith("shaheen"):
        return "Shaheen"
    if lowered.startswith("ibex"):
        return "Ibex"
    if lowered.startswith("kw61316"):
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

    A record carrying the commit it ran from (`repo.commit`, metrics schema
    6) gets the revision at that commit. An older record gets the revision
    committed last before its timestamp: runs made just before their
    script was committed can land one revision early, which only ever splits
    a comparison, never joins two different tests. Without a git history
    (a bare copy of the files) every record is revision 0 and `available`
    is False, and build_site says so on stderr.
    """

    def __init__(self, repo_root):
        self.repo_root = repo_root
        self.available = _git(repo_root, "rev-parse", "--git-dir") is not None
        self._eras = {}
        self._at_commit = {}
        self._touched = {}

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

    def of(self, vignette_dir, timestamp, record):
        """(index, label) of the revision this record ran, or (0, "") unknown."""
        if not self.available:
            return 0, ""
        eras = self.eras(vignette_dir)
        if not eras:
            return 0, ""
        index = None
        commit = (record.get("repo") or {}).get("commit")
        if commit and (commit, vignette_dir) in self._touched:
            touched = self._touched[(commit, vignette_dir)]
        elif commit:
            touched = _git(
                self.repo_root,
                "log",
                "-1",
                "--format=%H",
                commit,
                "--",
                ":(glob){0}/*.py".format(vignette_dir),
            )
            self._touched[(commit, vignette_dir)] = touched
        if commit:
            if touched and touched.strip():
                index = self._at_commit[vignette_dir].get(touched.strip())
        if index is None:
            moment = parse_ts(timestamp)
            index = 0
            for n, (when, _) in enumerate(eras):
                if when <= moment:
                    index = n
        when, sha = eras[index]
        return index, "{0} ({1})".format(sha, when.strftime("%d %b %Y"))


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
            for ts, rec in rows:
                rec["_rev"], rec["_rev_label"] = revisions.of(vignette_dir, ts, rec)
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


def config_state(tool, vignettes, now, retired=None):
    """Everything the index says about one configuration and tool.

    retired: this configuration's RETIRED_FILE entry, or None. A retired
    configuration is never stale: no run is expected of it.
    """
    latest = []
    for vignette in sorted(vignettes, key=vignette_number):
        rows = vignettes[vignette]
        ts, record = rows[-1]
        drifted, judged = drift_by_record(rows).get(ts, ([], False))
        latest.append((vignette, ts, record, drifted, judged))
    counts = dict.fromkeys(STATUS_ORDER, 0)
    for entry in latest:
        counts[status_of(entry[2])[0]] += 1
    last_ts, last_version = max(
        (entry[1], drift.tool_version(entry[2]) or "") for entry in latest
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
        candidate = safe + ".html" if safe == config else None
        length = 10
        while candidate is None or candidate.lower() in used:
            candidate = "{0}-{1}.html".format(safe, digest[:length])
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


class VersionAxis(object):
    """x positions with the tool version as the axis, in version order.

    Each version is a band and its runs sit evenly across it in date order,
    so a configuration that ran on six days in two years fills its chart
    instead of leaving it blank between them. keys: [(version, timestamp)].
    A band is at least MIN_BAND wide so its label fits; the rest of the
    width goes to the bands in proportion to their runs.
    """

    MIN_BAND = 46
    GAP = 6

    def __init__(self, keys, left, right):
        self.versions = sorted({v for v, _ in keys}, key=version_key)
        runs = {v: sorted({ts for vv, ts in keys if vv == v}) for v in self.versions}
        width = right - left - self.GAP * (len(self.versions) - 1)
        base = min(self.MIN_BAND, width / float(len(self.versions)))
        spare = width - base * len(self.versions)
        total = float(sum(len(r) for r in runs.values()))
        self.bands = []
        self._x = {}
        x = left
        for version in self.versions:
            band = base + spare * len(runs[version]) / total
            self.bands.append((version, x, x + band))
            for index, ts in enumerate(runs[version]):
                self._x[(version, ts)] = x + band * (index + 0.5) / len(runs[version])
            x += band + self.GAP

    def x(self, version, ts):
        return self._x[(version, ts)]

    def band(self, version):
        return next((x0, x1) for v, x0, x1 in self.bands if v == version)


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


def svg_version_bands(axis, top, bottom_y, label_y):
    """Every other version band shaded, each labelled under the axis."""
    out = []
    for index, (version, x0, x1) in enumerate(axis.bands):
        if index % 2 == 0:
            out.append(
                '<rect class="band" x="{0:.1f}" y="{1}" width="{2:.1f}" '
                'height="{3}"/>'.format(x0, top, x1 - x0, bottom_y - top)
            )
        out.append(
            '<text class="blabel" x="{0:.1f}" y="{1}" text-anchor="middle">'
            "v{2}</text>".format((x0 + x1) / 2.0, label_y, esc(version))
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
def svg_metric_chart(title, unit, points, slot_of, drifted):
    """One metric with the tool version as the x axis.

    points: [(ts, version, value, why)], why as comparable_rows gives it.
    Each version is a band holding its runs in date order; a bar across the
    band marks the median of its runs comparable with the latest. The rest
    are faded, their tooltip saying why.
    """
    width, height = 380, 196
    left, right, top, bottom = 54, 14, 12, 26
    unit_shown, factor = display_unit(unit, [p[2] for p in points])
    ticks = nice_ticks(max(p[2] for p in points) * factor)
    y_max = ticks[-1]
    axis = VersionAxis([(p[1], p[0]) for p in points], left, width - right)
    bottom_y = height - bottom

    def sy(value):
        return top + (bottom_y - top) * (1 - value * factor / y_max)

    out = [svg_open(width, height, "{0} per run, by tool version".format(title))]
    out.append(svg_version_bands(axis, top, bottom_y, height - 8))
    out.append(svg_y_grid(ticks, y_max, left, width - right, top, bottom_y))
    by_version = {}
    for ts, version, value, why in points:
        if not why:
            by_version.setdefault(version, []).append(value)
    for version, values in by_version.items():
        if len(values) > 1:
            x0, x1 = axis.band(version)
            median = statistics.median(values)
            out.append(
                '<line class="med" x1="{0:.1f}" x2="{1:.1f}" y1="{2:.1f}" y2="{2:.1f}" '
                'data-tip="{3}"><title>{3}</title></line>'.format(
                    x0 + 3,
                    x1 - 3,
                    sy(median),
                    esc(
                        "v{0} median of {1} runs: {2:,.3g} {3}".format(
                            version, len(values), median * factor, unit_shown
                        )
                    ),
                )
            )
    for ts, version, value, why in points:
        note = drifted.get(ts)
        tip = "{0} | v{1} | {2:,.3g} {3}{4}{5}".format(
            long_date(ts),
            version,
            value * factor,
            unit_shown,
            " | not comparable with the latest run: " + why if why else "",
            " | DRIFT: " + note if note else "",
        )
        extra = (" faded" if why else "") + (" drift" if note else "")
        out.append(
            svg_dot(
                slot_of(version),
                axis.x(version, ts),
                sy(value),
                tip,
                extra,
                6 if note else 4,
            )
        )
    out.append("</svg>")
    return "".join(out), unit_shown


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


def svg_relative_panel(config, series, ticks, slot_of):
    """One configuration's earlier versions against its newest, shared scale."""
    width, height = 260, 150
    left, right, top, bottom = 34, 10, 16, 24
    y_max = ticks[-1]
    bottom_y = height - bottom
    axis = VersionAxis([(v, v) for v, _, _ in series], left, width - right)

    def sy(ratio):
        return top + (bottom_y - top) * (1 - ratio / y_max)

    out = [
        svg_open(width, height, "{0}: time against the newest version".format(config))
    ]
    out.append(svg_version_bands(axis, top, bottom_y, height - 8))
    out.append(svg_y_grid(ticks, y_max, left, width - right, top, bottom_y))
    out.append(
        '<line class="ref" x1="{0}" x2="{1}" y1="{2:.1f}" y2="{2:.1f}"/>'.format(
            left, width - right, sy(1.0)
        )
    )
    if len(series) > 1:
        out.append(
            '<path class="trend" d="{0}"/>'.format(
                " ".join(
                    "{0}{1:.1f},{2:.1f}".format(
                        "M" if n == 0 else "L", axis.x(v, v), sy(ratio)
                    )
                    for n, (v, ratio, _) in enumerate(series)
                )
            )
        )
    newest = series[-1][0]
    for version, ratio, count in series:
        x, y = axis.x(version, version), sy(ratio)
        if version == newest:
            tip = "{0} | v{1} | the newest version here, {2} vignettes timed".format(
                config, version, count
            )
            label = "1"
        else:
            tip = (
                "{0} | v{1} | {2:.2f}x the time of v{3}, over the {4} vignettes "
                "both ran unchanged".format(config, version, ratio, newest, count)
            )
            label = "{0:.2f}x ({1})".format(ratio, count)
        out.append(svg_dot(slot_of(version), x, y, tip, r=5))
        out.append(
            '<text class="vallabel" x="{0:.1f}" y="{1:.1f}" '
            'text-anchor="middle">{2}</text>'.format(x, y - 9, esc(label))
        )
    out.append("</svg>")
    return "".join(out)


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
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;
--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--ring:rgba(11,11,11,.10);--good:#0ca30c;--warn:#fab219;--bad:#d03b3b;
--good-soft:#d6f0d6;--bad-soft:#f7d9d9;--na:#efeee9;--mid:#f0efec;
--r-3:#1c5cab;--r-2:#5598e7;--r-1:#b7d3f6;--r1:#f5c2c1;--r2:#ec8584;--r3:#b8302f;
%(light)s}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){%(dark)s}}
:root[data-theme="dark"]{%(dark)s}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1240px;margin:0 auto;padding:20px 16px 64px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:36px 0 6px}
h3{font-size:15px;margin:0 0 4px}
p.lede{font-size:15px;color:var(--ink2);margin:4px 0 8px}
.note{color:var(--ink2);font-size:13px;margin:2px 0 8px}
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
svg .band{fill:var(--na);opacity:.7}
svg .blabel{fill:var(--ink2);font-size:10px}
svg .med{stroke:var(--ink2);stroke-width:2;stroke-linecap:round}
svg .trend{fill:none;stroke:var(--axis);stroke-width:2}
svg .ref{stroke:var(--ink2);stroke-width:1;stroke-dasharray:4 3}
svg .vallabel{fill:var(--ink2);font-size:10px;font-variant-numeric:tabular-nums}
svg .line{fill:none;stroke-width:2}
svg .dot{stroke:var(--surface);stroke-width:2}
svg .dot.faded{fill-opacity:.25;stroke-opacity:.4}
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
.r-3{background:var(--r-3)}.r-2{background:var(--r-2)}.r-1{background:var(--r-1)}
.r0{background:var(--mid)}.r1{background:var(--r1)}.r2{background:var(--r2)}
.r3{background:var(--r3)}.cell.none{background:transparent;color:var(--muted)}
.r-3,.r3{color:#fff}.r-2,.r-1,.r0,.r1,.r2{color:var(--ink)}
table.heat td.chg{min-width:44px}
.cell.changed{background:transparent;color:var(--ink2);outline:1px dashed var(--axis);
outline-offset:-2px}
.note.empty{margin:24px 8px;color:var(--muted)}
table.heat td.chg .cell{width:42px;font-size:11px;font-variant-numeric:tabular-nums}
table.heat th.from{font-size:10px;font-weight:400;color:var(--muted);text-align:center;
padding:2px}
#tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);
border:1px solid var(--ring);border-radius:6px;padding:4px 8px;font-size:12px;
box-shadow:0 2px 8px rgba(0,0,0,.15);display:none;z-index:9;max-width:340px}
footer{color:var(--muted);font-size:12px;margin-top:40px}
@media (max-width:600px){h1{font-size:20px}.tile .v{font-size:22px}
table.heat th.col span{max-height:130px}.grid-charts{grid-template-columns:1fr}}
"""

DARK = (
    "color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;"
    "--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);"
    "--good-soft:#173d17;--bad-soft:#4a1d1d;--na:#262624;--mid:#383835;"
    "--r-3:#3987e5;--r-2:#256abf;--r-1:#184f95;--r1:#6b2423;--r2:#a83a39;"
    "--r3:#e66767;"
)

SCRIPT = """
<div id="tip"></div>
<script>
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
    return base + classes


def page(title, body, generated):
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>{0}</title><style>{1}</style></head><body><main>{2}"
        "<footer>Generated {3} from the performance_metrics records in "
        "jameskress/Visualization_Vignettes by Testing/dashboard.py. "
        "Drift rule and record fields: Testing/README.md.</footer>"
        "</main>{4}</body></html>"
    ).format(esc(title), css(), body, esc(generated), SCRIPT)


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------
HOW_TO_READ = (
    (
        "&#10003; &#10007;",
        "pass / fail: every comparison gate (image, numbers, CSV). "
        "Recorded from metrics schema 6.",
    ),
    ("&#9679; &#9675;", "older runs: they say only whether the vignette finished."),
    (
        "x axis",
        "the tool version, oldest on the left. Runs of one version sit in "
        "date order inside its band; hover for the date.",
    ),
    ("dot, bar", "a dot is one run; a bar across a band is that version's median."),
    ("colour", "the tool version, the same on every chart and page."),
    (
        "faded dot",
        "not comparable with the latest run: an older revision of the "
        "vignette, or measured differently (older schema or scope).",
    ),
    (
        "revision",
        "a change to a vignette's code. Times are compared only between "
        "runs of the same revision.",
    ),
    ("ring, outline", "a drift warning: the run moved well outside its own history."),
    (
        "stale, retired",
        "stale: no run in {0} days, or not on the pinned build. "
        "Retired: hardware that left the suite; its history is kept.",
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
    body = [
        "<h1>Visualization Vignettes results</h1>",
        "<p class='lede'>{0} ParaView and {1} VisIt vignettes on {2} active "
        "configurations at {3} sites. Last run {4}. Pinned builds: ParaView v{5}, "
        "VisIt v{6}.</p>".format(
            vignette_count["ParaView"],
            vignette_count["VisIt"],
            len(active),
            len({site_of(c) for c in active}),
            esc(long_date(last)) if last else "never",
            CURRENT_PINS["ParaView"],
            CURRENT_PINS["VisIt"],
        ),
        "<div class='tiles'>",
    ]
    for value, label in (
        (len(active), "active configurations"),
        (len(stale), "stale configurations"),
        (totals["pass"], "latest runs passing"),
        (totals["fail"] + totals["run_failed"], "latest runs failing"),
        (drifting, "drift warnings"),
        (len(retired), "retired configurations"),
    ):
        body.append(
            "<div class='tile'><div class='v'>{0}</div><div class='k'>{1}</div></div>".format(
                value, esc(label)
            )
        )
    body.append("</div>")
    body.append(how_to_read())

    body.append(
        "<h2>Did everything pass?</h2><p class='note'>The latest run of each "
        "vignette on each configuration. Click a configuration for its history.</p>"
    )
    for tool in TOOLS:
        body.append(render_heatmap(tool, histories, states, configs))

    body.append(
        "<h2>Speed by tool version</h2><p class='note'>How long each earlier "
        "version took against the machine's newest (1), over the vignettes both "
        "ran unchanged; the count is in brackets. Above 1, the earlier version was "
        "slower. A version that ran only older revisions of the vignettes, as every "
        "run before the September 2026 rewrite did, measured different tests and "
        "is left out.</p>"
    )
    for tool in TOOLS:
        body.append(render_suite_versions(tool, histories, states, configs))

    body.append(
        "<h2>What changed in the last upgrade?</h2><p class='note'>Each vignette's "
        "median time at its machine's newest version against the version before it "
        "there, from runs of the same vignette code. Blue is faster, red slower, "
        "grey within 10%. One or two runs per version is common, so read single "
        "cells as a lead, not a verdict.</p>"
    )
    for tool in TOOLS:
        body.append(render_change_matrix(tool, histories, states, configs))

    body.append(
        "<h2>Which machine is fastest?</h2><p class='note'>Each vignette's latest "
        "time on every active configuration at the pinned build, on a log scale. "
        "Colour is the site.</p>"
    )
    for tool in TOOLS:
        body.append(render_dot_plot(tool, histories, states))

    body.append(
        "<h2>Configurations</h2><p class='note'>Drift <em>n/a</em>: no vignette "
        "there has three earlier runs at the same version and measurement yet.</p>"
    )
    body.append(render_config_table(states, active))
    if retired:
        body.append(
            "<h2>Retired configurations</h2><p class='note'>Hardware that left the "
            "suite (<code>{0}</code>). Their history and pages stay; they are left "
            "out of the charts above.</p>".format(
                esc(RETIRED_FILE.replace(os.sep, "/"))
            )
        )
        body.append(render_retired_table(states, retired))
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


def render_suite_versions(tool, histories, states, configs):
    slot_of, _ = tool_slot_map(histories, tool)
    panels = []
    for c in active_configs(states, configs, tool):
        if (c, tool) in histories:
            series = relative_by_version(histories[(c, tool)])
            if series:
                panels.append((c, series))
    if not panels:
        return ""
    ticks = nice_ticks(max(1.5, max(r for _, s in panels for _, r, _ in s)))
    versions = sorted({v for _, s in panels for v, _, _ in s}, key=version_key)
    rows = "".join(
        "<tr><td>{0}</td><td>v{1}</td><td class='num'>{2:.2f}</td>"
        "<td class='num'>{3}</td></tr>".format(esc(c), esc(v), ratio, count)
        for c, series in panels
        for v, ratio, count in series
    )
    cards = []
    for c, series in panels:
        if len(series) > 1:
            chart = svg_relative_panel(c, series, ticks, slot_of)
        else:
            chart = (
                "<p class='note empty'>Only v{0} has run the current vignettes "
                "here, so there is nothing to compare yet.</p>".format(
                    esc(series[0][0])
                )
            )
        cards.append(
            "<div class='panel'><h4><a href='{0}#{1}'>{2}</a> <span class='unit'>"
            "{3}</span></h4>{4}</div>".format(
                esc(page_name(c)), esc(tool), esc(c), esc(site_of(c)), chart
            )
        )
    return (
        "<div class='card'><h3>{0}</h3>{1}<div class='multiples'>{2}</div>"
        "<details><summary>table</summary><div class='scroll tall'><table><thead><tr>"
        "<th>Configuration</th><th>Version</th><th class='num'>Time against the newest"
        "</th><th class='num'>Vignettes compared</th></tr></thead><tbody>{3}</tbody>"
        "</table></div></details></div>".format(
            esc(tool),
            legend([(slot_of(v), "v" + v) for v in versions]),
            "".join(cards),
            rows,
        )
    )


def last_upgrade(vignettes):
    """(newest version, the version before) a configuration has times for."""
    versions = sorted(
        {v for rows in vignettes.values() for v in versions_timed(rows)},
        key=version_key,
    )
    return (versions[-1], versions[-2]) if len(versions) > 1 else (None, None)


def change_bin(ratio):
    return next((cls, text) for edge, cls, text in CHANGE_BINS if ratio <= edge)


def render_change_matrix(tool, histories, states, configs):
    cols, upgrades = [], {}
    for c in heat_columns(tool, states, configs):
        new, old = last_upgrade(histories[(c, tool)])
        if new:
            cols.append(c)
            upgrades[c] = (new, old)
    if not cols:
        return ""
    vignettes = sorted(
        {v for c in cols for v in histories[(c, tool)]}, key=vignette_number
    )
    from_row = "<tr><th class='from'>from</th>{0}</tr>".format(
        "".join(
            "<th class='from' title='{0}'>{1}</th>".format(
                esc("{0}: v{1} to v{2}".format(c, upgrades[c][1], upgrades[c][0])),
                esc(upgrades[c][1]),
            )
            for c in cols
        )
    )
    body, ratios, changed = [], [], 0
    for v in vignettes:
        body.append("<tr><td class='rowh'>{0}</td>".format(esc(v)))
        for c in cols:
            new, old = upgrades[c]
            rows = histories[(c, tool)].get(v, [])
            timed = versions_timed(rows)
            pair = like_for_like(rows, new, old)
            if pair is None and new in timed and old in timed:
                changed += 1
                body.append(
                    "<td class='hm chg' data-tip='{0}'><span class='cell changed'>"
                    "&ne;</span></td>".format(
                        esc(
                            "{0} | {1} | the vignette changed between the v{2} and "
                            "v{3} runs: different tests, not compared".format(
                                v, c, old, new
                            )
                        )
                    )
                )
                continue
            if pair is None:
                missing = new if new not in timed else old
                body.append(
                    "<td class='hm chg' data-tip='{0}'><span class='cell none'>&middot;"
                    "</span></td>".format(
                        esc(
                            "{0} | {1} | no successful run at v{2}".format(
                                v, c, missing
                            )
                        )
                    )
                )
                continue
            before_runs, after_runs, rev = pair
            before = statistics.median(before_runs)
            after = statistics.median(after_runs)
            ratio = after / before
            ratios.append(ratio)
            cls, text = change_bin(ratio)
            tip = (
                "{0} | {1} | v{2} {3:.3g} s ({4} runs) to v{5} {6:.3g} s ({7} runs) "
                "| {8} | vignette revision {9}".format(
                    v,
                    c,
                    old,
                    before,
                    len(before_runs),
                    new,
                    after,
                    len(after_runs),
                    text,
                    rev or "unknown",
                )
            )
            body.append(
                "<td class='hm chg' data-tip='{0}'><span class='cell {1}'>{2:+.0f}%"
                "</span></td>".format(esc(tip), cls, (ratio - 1) * 100)
            )
        body.append("</tr>")
    if not ratios and not changed:
        return ""
    summary = (
        "{0} vignette and machine pairs ran the same vignette code at both "
        "versions".format(len(ratios))
    )
    if ratios:
        summary += ": median change {0:+.0f}%; {1} slower by more than 10%, {2} faster by more than 10%".format(
            (statistics.median(ratios) - 1) * 100,
            sum(1 for r in ratios if r > 1.1),
            sum(1 for r in ratios if r < 1 / 1.1),
        )
    summary += ". {0} more are not compared because the vignette changed in between (&ne;).".format(
        changed
    )
    keys = "".join(
        "<span class='key'><span class='cell {0}'></span>{1}</span>".format(
            cls, esc(text)
        )
        for _, cls, text in CHANGE_BINS
    )
    return (
        "<div class='card'><h3>{0}</h3><p class='note'>{1}</p>"
        "<div class='legend'>{2}</div><div class='scroll tall'><table class='heat'>"
        "{3}<tbody>{4}</tbody></table></div></div>".format(
            esc(tool),
            summary,
            keys,
            heat_head(cols, tool, states, from_row),
            "".join(body),
        )
    )


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
            rec = hist[-1][1]
            if drift.tool_version(rec) == pin and is_number(rec.get("execution_time")):
                dots.append((c, float(rec["execution_time"])))
                table.append((v, c, float(rec["execution_time"])))
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


def tool_slot_map(histories, tool):
    """(version -> slot, versions in order) for one tool, the same everywhere."""
    versions = sorted(
        {
            drift.tool_version(rec) or "unknown"
            for (_, t), vignettes in histories.items()
            if t == tool
            for rows in vignettes.values()
            for _, rec in rows
        },
        key=version_key,
    )
    mapping = {v: i % len(SLOTS_LIGHT) for i, v in enumerate(versions)}
    return (lambda v, m=mapping: m.get(v, 0)), versions


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


def render_vignette_card(tool, vignette, rows, slot_of):
    drifts = drift_by_record(rows)
    out = [
        "<div class='card' id='{0}-{1}'><h3>{1}</h3>".format(esc(tool), esc(vignette))
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
        svg, unit_shown = svg_metric_chart(title, unit, points, slot_of, drifted)
        charts.append(
            "<div class='chart-box'><h4>{0} <span class='unit'>({1})</span></h4>"
            "{2}</div>".format(esc(title), esc(unit_shown), svg)
        )
    if charts:
        out.append(
            legend(
                [(slot_of(v), "v" + v) for v in sorted(versions_seen, key=version_key)]
            )
        )
        out.append("<div class='grid-charts'>{0}</div>".format("".join(charts)))
        out.append(
            "<div class='note'>One band per tool version, its runs in date order "
            "(hover for the date); the bar is the median of the runs comparable with "
            "the latest. Faded: an older revision of the vignette, or measured "
            "differently.{0}</div>".format(
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


def render_tool_section(tool, vignettes, state, slot_of):
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
            "<tr><td><a href='#{0}-{1}'>{1}</a></td><td>{2}</td><td>{3}</td>"
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
            )
        )
    out.append("</tbody></table></div>")
    for entry in state["latest"]:
        out.append(render_vignette_card(tool, entry[0], vignettes[entry[0]], slot_of))
    return "".join(out)


def render_config(config, tools, states, slot_maps, generated):
    retired = next(
        (
            states[(config, t)]["retired"]
            for t in tools
            if states[(config, t)]["retired"]
        ),
        None,
    )
    body = [
        "<p><a href='index.html'>&larr; All configurations</a></p>",
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
                    tool, tools[tool], states[(config, tool)], slot_maps[tool]
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
    now = now or datetime.datetime.now()
    generated = generated or now.strftime("%Y-%m-%d %H:%M")
    os.makedirs(out_dir, exist_ok=True)

    retired = load_retired(repo_root)
    states = {
        key: config_state(key[1], vs, now, retired.get(key[0]))
        for key, vs in histories.items()
    }
    slot_maps = {tool: tool_slot_map(histories, tool)[0] for tool in TOOLS}

    PAGE_NAMES.clear()
    PAGE_NAMES.update(page_names({config for config, _ in histories}))
    with open(os.path.join(out_dir, "index.html"), "w") as handle:
        handle.write(render_index(histories, states, generated))

    by_config = {}
    for (config, tool), vignettes in histories.items():
        by_config.setdefault(config, {})[tool] = vignettes
    for config, tools in by_config.items():
        with open(os.path.join(out_dir, page_name(config)), "w") as handle:
            handle.write(render_config(config, tools, states, slot_maps, generated))

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
