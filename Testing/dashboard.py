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
#                     vignette by configuration (switchable to time against
#                     that vignette's median), suite time per configuration
#                     over time, each vignette's time across machines on the
#                     current build, which tool version each configuration
#                     ran when, and a table of every configuration with its
#                     staleness and drift
#   <config>.html     per vignette: run history, telemetry charts over real
#                     dates with version changes marked, drift, builds and
#                     baselines, every run
#   records.json      every record, flattened, for analysis elsewhere
#
# .github/workflows/dashboard.yml publishes it to GitHub Pages.
#
#   python3 Testing/dashboard.py --out _site
#
# Standard library only, so it runs on a bare GitHub runner. Charts are
# inline SVG with a few lines of script for tooltips and the heatmap switch;
# without the script every page still reads, minus those two.
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
import datetime
import glob
import hashlib
import html
import json
import math
import os
import re
import statistics
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

# Diverging steps for "time against the vignette's median": blue faster, red
# slower, grey about the same. Upper edges of log2(time / median) bins.
RATIO_BINS = [
    (-1.0, "r-3", "under half"),
    (-0.5, "r-2", "0.5 to 0.7x"),
    (-0.15, "r-1", "0.7 to 0.9x"),
    (0.15, "r0", "about the median"),
    (0.5, "r1", "1.1 to 1.4x"),
    (1.0, "r2", "1.4 to 2x"),
    (float("inf"), "r3", "over 2x"),
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
    """[(ts, record, value, same)] for every row that has `metric`.

    `same` is the rule drift.py and plot_metrics.py use: a comparable
    schema, under the latest run's measurement scope. Rows that are not the
    same are drawn faded, so a change in what a number means is never read
    as a change in the number.
    """
    scope_field = SCOPE_FIELD.get(metric)
    current = [(ts, rec) for ts, rec in rows if drift.comparable(metric, rec)]
    latest_scope = None
    if scope_field and current:
        # The latest run sets the scope even when it has no value.
        latest_scope = current[-1][1].get(scope_field)
    out = []
    for ts, rec in rows:
        value = rec.get(metric)
        if not is_number(value):
            continue
        same = drift.comparable(metric, rec) and (
            not scope_field or rec.get(scope_field) == latest_scope
        )
        out.append((ts, rec, float(value), same))
    return out


def drift_by_record(rows):
    """{timestamp: (drift results, judged)} for one vignette's history.

    judged is False when every metric lacked the history drift.py needs, so
    a reader can tell "no drift" from "too little history to say".
    """
    out = {}
    for ts, results in drift.check_history(rows).items():
        drifted = [r for r in results if r["verdict"] == "drift"]
        judged = any(r["verdict"] != "insufficient" for r in results)
        out[ts] = (drifted, judged)
    return out


def config_state(tool, vignettes, now):
    """Everything the index says about one configuration and tool."""
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
    if age > STALE_DAYS:
        reasons.append("last run {0} days ago".format(age))
    pin = CURRENT_PINS.get(tool)
    if pin and last_version and version_key(last_version) < version_key(pin):
        reasons.append("last ran v{0}; the suite pins v{1}".format(last_version, pin))
    return {
        "latest": latest,
        "counts": counts,
        "last_ts": last_ts,
        "version": last_version,
        "drifting": drifting,
        "stale": reasons,
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


def date_ticks(start, end, max_ticks=5):
    """[(datetime, label)] at month starts between start and end."""
    months = (end.year - start.year) * 12 + end.month - start.month + 1
    step = next(
        s for s in (1, 2, 3, 6, 12, 24, 36, 120) if months / float(s) <= max_ticks
    )
    ticks = []
    year = start.year
    month = ((start.month - 1) // step) * step + 1 if step <= 12 else 1
    while True:
        tick = datetime.datetime(year, month, 1)
        if tick > end:
            break
        if tick >= start:
            ticks.append(tick)
        month += step
        while month > 12:
            month -= 12
            year += 1
    label = "%Y" if step >= 12 else "%b %Y"
    return [(t, t.strftime(label)) for t in ticks] or [
        (start, start.strftime("%d %b %Y"))
    ]


class TimeAxis(object):
    """x positions for timestamps across a chart's plot width."""

    def __init__(self, stamps, left, right):
        times = [parse_ts(s) for s in stamps]
        start, end = min(times), max(times)
        if end - start < datetime.timedelta(days=2):
            start -= datetime.timedelta(days=1)
            end += datetime.timedelta(days=1)
        pad = (end - start) * 0.04
        self.start, self.end = start - pad, end + pad
        self.left, self.right = left, right

    def x(self, stamp):
        moment = stamp if isinstance(stamp, datetime.datetime) else parse_ts(stamp)
        span = (self.end - self.start).total_seconds()
        frac = (moment - self.start).total_seconds() / span
        return self.left + frac * (self.right - self.left)

    def ticks(self, max_ticks=5):
        return date_ticks(self.start, self.end, max_ticks)


def svg_open(width, height, label):
    return (
        '<svg class="chart" viewBox="0 0 {0} {1}" role="img" aria-label="{2}">'.format(
            width, height, esc(label)
        )
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


def svg_x_dates(axis, y, max_ticks=5):
    return "".join(
        '<text class="tick" x="{0:.1f}" y="{1}" text-anchor="middle">{2}</text>'.format(
            axis.x(moment), y, esc(label)
        )
        for moment, label in axis.ticks(max_ticks)
    )


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
        "</span>drift warning</span></div>"
        '<p class="note">Pass and fail come from the comparison gates, recorded '
        "from metrics schema 6. Older records say only whether the vignette ran "
        "cleanly (ran OK / run failed).</p>".format(keys)
    )


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def svg_metric_chart(title, unit, points, slot_of, drifted, version_marks):
    """One metric over real dates. points: [(ts, version, value, same)].

    Runs measured like the latest are solid and joined per version; the
    rest are faded and unjoined. Each version change is a labelled rule.
    """
    width, height = 380, 196
    left, right, top, bottom = 54, 14, 24, 26
    unit_shown, factor = display_unit(unit, [p[2] for p in points])
    ticks = nice_ticks(max(p[2] for p in points) * factor)
    y_max = ticks[-1]
    axis = TimeAxis([p[0] for p in points], left, width - right)
    bottom_y = height - bottom

    def sy(value):
        return top + (bottom_y - top) * (1 - value * factor / y_max)

    out = [svg_open(width, height, "{0} per run".format(title))]
    out.append(svg_y_grid(ticks, y_max, left, width - right, top, bottom_y))
    out.append(svg_x_dates(axis, height - 8))
    last_label_x = -100
    for stamp, version in version_marks:
        if not axis.start <= parse_ts(stamp) <= axis.end:
            continue  # outside this metric's dates
        x = axis.x(stamp)
        out.append(
            '<line class="vmark" x1="{0:.1f}" x2="{0:.1f}" y1="{1}" y2="{2}"/>'.format(
                x, top - 4, bottom_y
            )
        )
        if x - last_label_x > 34:  # do not stack labels on top of each other
            out.append(
                '<text class="vlabel" x="{0:.1f}" y="{1}">v{2}</text>'.format(
                    x + 2, top - 8, esc(version)
                )
            )
            last_label_x = x
    by_version = {}
    for ts, version, value, same in points:
        if same:
            by_version.setdefault(version, []).append((ts, value))
    for version, series in by_version.items():
        if len(series) > 1:
            path = " ".join(
                "{0}{1:.1f},{2:.1f}".format("M" if n == 0 else "L", axis.x(ts), sy(v))
                for n, (ts, v) in enumerate(series)
            )
            out.append(
                '<path class="line s{0}" d="{1}"/>'.format(slot_of(version), path)
            )
    for ts, version, value, same in points:
        note = drifted.get(ts)
        tip = "{0} | v{1} | {2:,.3g} {3}{4}{5}".format(
            long_date(ts),
            version,
            value * factor,
            unit_shown,
            "" if same else " | measured differently from the latest run",
            " | DRIFT: " + note if note else "",
        )
        extra = ("" if same else " faded") + (" drift" if note else "")
        out.append(
            svg_dot(
                slot_of(version), axis.x(ts), sy(value), tip, extra, 6 if note else 4
            )
        )
    out.append("</svg>")
    return "".join(out), unit_shown


def suite_runs(vignettes):
    """[(timestamp, total seconds, vignettes, version)] per suite run.

    Records of one invocation share a run_id; older ones without it are
    grouped by day. A vignette counts once per run, its last record there,
    since an older day can hold several attempts. Only runs that covered
    most of the suite (10 vignettes or more) are kept, so a two-vignette
    rerun is not read as a fast suite.
    """
    groups = {}
    for vignette, rows in vignettes.items():
        for ts, rec in rows:
            key = rec.get("run_id") or "day-" + short_date(ts)
            if is_number(rec.get("execution_time")):
                # rows are oldest first, so the last assignment wins
                groups.setdefault(key, {})[vignette] = (
                    ts,
                    float(rec["execution_time"]),
                    rec,
                )
    out = []
    for per_vignette in groups.values():
        items = sorted(per_vignette.values(), key=lambda item: item[0])
        if len(items) < 10:
            continue
        version = drift.tool_version(items[-1][2]) or "unknown"
        out.append((items[-1][0], sum(v for _, v, _ in items), len(items), version))
    return sorted(out)


def svg_suite_time(label, series, config_slot):
    """Total suite time per run, in minutes, a line per configuration."""
    points = [p for _, runs in series for p in runs]
    width, height = 380, 200
    left, right, top, bottom = 54, 14, 12, 26
    ticks = nice_ticks(max(p[1] for p in points) / 60.0)
    y_max = ticks[-1]
    axis = TimeAxis([p[0] for p in points], left, width - right)
    bottom_y = height - bottom

    def sy(seconds):
        return top + (bottom_y - top) * (1 - seconds / 60.0 / y_max)

    out = [svg_open(width, height, label)]
    out.append(svg_y_grid(ticks, y_max, left, width - right, top, bottom_y))
    out.append(svg_x_dates(axis, height - 8))
    for config, runs in series:
        slot = config_slot[config]
        if len(runs) > 1:
            path = " ".join(
                "{0}{1:.1f},{2:.1f}".format("M" if n == 0 else "L", axis.x(ts), sy(t))
                for n, (ts, t, _, _) in enumerate(runs)
            )
            out.append('<path class="line s{0}" d="{1}"/>'.format(slot, path))
        for ts, total, count, version in runs:
            tip = "{0} | {1} | v{2} | {3:.1f} min over {4} vignettes".format(
                config, long_date(ts), version, total / 60.0, count
            )
            out.append(svg_dot(slot, axis.x(ts), sy(total), tip))
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
        svg_open(width, height, "{0} time per vignette across machines".format(tool))
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


def svg_version_timeline(tool, rows, slot_of):
    """Which version each configuration ran over time: one mark per run day.

    rows: [(config, [(ts, version)])].
    """
    stamps = [ts for _, runs in rows for ts, _ in runs]
    row_h = 20
    left, right, top, bottom = 178, 16, 8, 26
    width = 660
    height = top + bottom + row_h * len(rows)
    axis = TimeAxis(stamps, left, width - right)
    out = [
        svg_open(width, height, "{0} version per configuration over time".format(tool))
    ]
    for moment, label in axis.ticks(6):
        x = axis.x(moment)
        out.append(
            '<line class="grid" x1="{0:.1f}" x2="{0:.1f}" y1="{1}" y2="{2}"/>'
            '<text class="tick" x="{0:.1f}" y="{3}" text-anchor="middle">{4}</text>'.format(
                x, top, height - bottom, height - 8, esc(label)
            )
        )
    for index, (config, runs) in enumerate(rows):
        y = top + row_h * index + row_h / 2.0
        out.append(
            '<text class="rowlabel" x="{0}" y="{1:.1f}" text-anchor="end">{2}</text>'.format(
                left - 8, y + 4, esc(config)
            )
        )
        for ts, version in runs:
            tip = "{0} | {1} | v{2}".format(config, long_date(ts), version)
            out.append(
                '<rect class="s{0}" x="{1:.1f}" y="{2:.1f}" width="5" height="{3:.1f}" '
                'rx="1.5" data-tip="{4}"><title>{4}</title></rect>'.format(
                    slot_of(version),
                    axis.x(ts) - 2.5,
                    y - row_h * 0.35,
                    row_h * 0.7,
                    esc(tip),
                )
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
p.lede,.note{color:var(--ink2);max-width:80ch;margin:4px 0 8px}
.note{font-size:13px}
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
.chart-box .unit{color:var(--muted);font-weight:400}
svg.chart{width:100%%;height:auto;display:block}
svg .grid{stroke:var(--grid);stroke-width:1}
svg .axis{stroke:var(--axis);stroke-width:1}
svg .rowline{stroke:var(--grid);stroke-width:1;stroke-dasharray:2 3}
svg .tick{fill:var(--muted);font-size:10px}
svg .rowlabel{fill:var(--ink2);font-size:11px}
svg .vmark{stroke:var(--axis);stroke-width:1;stroke-dasharray:3 3}
svg .vlabel{fill:var(--ink2);font-size:10px}
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
.heat .mode-time{display:none}.heat.time .mode-status{display:none}
.heat.time .mode-time{display:inline-block}
.switch{display:inline-flex;border:1px solid var(--axis);border-radius:6px;overflow:hidden;
margin:4px 0 6px}
.switch button{font:inherit;font-size:12px;border:0;padding:4px 10px;
background:var(--surface);color:var(--ink2);cursor:pointer}
.switch button[aria-pressed="true"]{background:var(--ink);color:var(--surface)}
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
document.querySelectorAll('[data-heat]').forEach(function(sw){
var id=sw.getAttribute('data-heat'),table=document.getElementById(id);
sw.querySelectorAll('button').forEach(function(b){b.addEventListener('click',function(){
var time=b.value==='time';table.classList.toggle('time',time);
sw.querySelectorAll('button').forEach(function(o){o.setAttribute('aria-pressed',o===b);});
document.getElementById(id+'-legend-status').hidden=time;
document.getElementById(id+'-legend-time').hidden=!time;});});});})();
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
def render_index(histories, states, generated):
    configs = sorted({config for config, _ in histories}, key=site_order)
    totals = dict.fromkeys(STATUS_ORDER, 0)
    drifting, last = 0, ""
    for state in states.values():
        for key, count in state["counts"].items():
            totals[key] += count
        drifting += state["drifting"] or 0
        last = max(last, state["last_ts"])
    active = [
        c
        for c in configs
        if any((c, t) in states and not states[(c, t)]["stale"] for t in TOOLS)
    ]
    vignette_count = {
        tool: len({v for (c, t), vs in histories.items() if t == tool for v in vs})
        for tool in TOOLS
    }
    body = [
        "<h1>Visualization Vignettes results</h1>",
        "<p class='lede'>The regression suite's committed history: {0} configurations "
        "on {1} sites, {2} ParaView and {3} VisIt vignettes. Last run {4}. Latest run "
        "of every vignette everywhere: {5}.</p>".format(
            len(configs),
            len({site_of(c) for c in configs}),
            vignette_count["ParaView"],
            vignette_count["VisIt"],
            esc(long_date(last)) if last else "never",
            ", ".join(
                "{0} {1}".format(totals[k], STATUS[k][1])
                for k in STATUS_ORDER
                if totals[k]
            ),
        ),
        "<div class='tiles'>",
    ]
    for value, label in (
        (len(active), "active configurations"),
        (len(configs) - len(active), "stale configurations"),
        (totals["pass"], "vignettes passing (schema 6)"),
        (totals["fail"] + totals["run_failed"], "vignettes failing"),
        (totals["ran_ok"], "ran OK, verdicts not recorded"),
        (drifting, "drift warnings"),
    ):
        body.append(
            "<div class='tile'><div class='v'>{0}</div><div class='k'>{1}</div></div>".format(
                value, esc(label)
            )
        )
    body.append("</div>")

    body.append(
        "<h2>Latest result, every vignette on every configuration</h2>"
        "<p class='note'>Each cell is the latest run of that vignette there. "
        "<em>Time vs median</em> colours it by execution time against that "
        "vignette's median over the active configurations on the pinned build "
        "(ParaView v{0}, VisIt v{1}). Greyed columns are stale.</p>".format(
            CURRENT_PINS["ParaView"], CURRENT_PINS["VisIt"]
        )
    )
    for tool in TOOLS:
        body.append(render_heatmap(tool, histories, states, configs))

    body.append(
        "<h2>Suite time per configuration</h2><p class='note'>Total execution time "
        "of each recorded suite run that covered 10 vignettes or more, in minutes. "
        "One chart per site and tool, one line per configuration.</p>"
    )
    body.append(render_suite_time(histories, configs))

    body.append(
        "<h2>Each vignette across machines, current build</h2><p class='note'>Latest "
        "execution time of every vignette on every active configuration whose latest "
        "run used the pinned version, on a log scale. Colour is the site.</p>"
    )
    for tool in TOOLS:
        body.append(render_dot_plot(tool, histories, states))

    body.append(
        "<h2>Tool versions over time</h2><p class='note'>One mark per day a "
        "configuration recorded a run, coloured by the tool version it ran.</p>"
    )
    for tool in TOOLS:
        body.append(render_version_timeline(tool, histories, configs))

    body.append("<h2>Configurations</h2>")
    body.append(render_config_table(states, configs))
    body.append(
        "<p class='note'><strong>Drift</strong> counts vignettes whose latest run "
        "moved well outside their own history; <em>n/a</em> means none there has "
        "enough comparable runs yet (three earlier runs at the same version and "
        "measurement). <strong>Stale</strong>: no run for {0} days, or the last run "
        "used an older version than the suite pins.</p>".format(STALE_DAYS)
    )
    return page("Vignette results", "".join(body), generated)


def heat_medians(tool, histories, states, cols, vignettes):
    """Median latest time per vignette over active configs on the pinned build."""
    medians = {}
    for v in vignettes:
        times = []
        for c in cols:
            rows = histories[(c, tool)].get(v)
            if not rows or states[(c, tool)]["stale"]:
                continue
            rec = rows[-1][1]
            if drift.tool_version(rec) == CURRENT_PINS[tool] and is_number(
                rec.get("execution_time")
            ):
                times.append(float(rec["execution_time"]))
        if times:
            medians[v] = statistics.median(times)
    return medians


def render_heatmap(tool, histories, states, configs):
    cols = [c for c in configs if (c, tool) in states]
    if not cols:
        return ""
    vignettes = sorted(
        {v for c in cols for v in histories[(c, tool)]}, key=vignette_number
    )
    medians = heat_medians(tool, histories, states, cols, vignettes)
    table_id = "heat-" + tool.lower()
    ratio_keys = "".join(
        "<span class='key'><span class='cell {0}'></span>{1}</span>".format(
            cls, esc(text)
        )
        for _, cls, text in RATIO_BINS
    )
    out = [
        "<div class='card'><h3>{0}</h3>".format(esc(tool)),
        "<div class='switch' data-heat='{0}' role='group' aria-label='Colour cells by'>"
        "<button value='status' aria-pressed='true'>status</button>"
        "<button value='time' aria-pressed='false'>time vs median</button></div>".format(
            table_id
        ),
        "<div id='{0}-legend-status'>{1}</div>".format(table_id, status_legend()),
        "<div id='{0}-legend-time' hidden><div class='legend'>{1}<span class='key'>"
        "<span class='cell none'>&middot;</span>not on the pinned build or no "
        "median</span></div></div>".format(table_id, ratio_keys),
        "<div class='scroll tall'><table class='heat' id='{0}'><thead><tr><th></th>".format(
            table_id
        ),
    ]
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
    out.append("</tr></thead><tbody>")
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
            ratio_cls, ratio_txt = "none", "not on the pinned build"
            if (
                v in medians
                and drift.tool_version(rec) == CURRENT_PINS[tool]
                and is_number(seconds)
                and seconds > 0
            ):
                ratio = math.log2(seconds / medians[v])
                ratio_cls = next(cls for edge, cls, _ in RATIO_BINS if ratio <= edge)
                ratio_txt = "{0:.2g}x the median of {1:.3g} s".format(
                    seconds / medians[v], medians[v]
                )
            tip = "{0} | {1} | {2} | v{3} | {4}{5} | {6}".format(
                v,
                c,
                long_date(ts),
                drift.tool_version(rec),
                detail,
                " | drift: " + ", ".join(d["label"] for d in drifted)
                if drifted
                else "",
                "{0:.3g} s, {1}".format(seconds, ratio_txt)
                if is_number(seconds)
                else "time not recorded",
            )
            out.append(
                "<td class='hm{0}' data-tip='{1}'>"
                "<span class='mode-status cell c-{2}'>{3}</span>"
                "<span class='mode-time cell {4}'></span></td>".format(
                    " drift" if drifted else "",
                    esc(tip),
                    status_class(status),
                    STATUS[status][0],
                    ratio_cls,
                )
            )
        out.append("</tr>")
    out.append("</tbody></table></div></div>")
    return "".join(out)


def render_suite_time(histories, configs):
    boxes = []
    for tool in TOOLS:
        for site in SITES:
            series = [
                (c, suite_runs(histories[(c, tool)]))
                for c in configs
                if site_of(c) == site and (c, tool) in histories
            ]
            series = [(c, runs) for c, runs in series if runs]
            if not series:
                continue
            config_slot = {c: i % len(SLOTS_LIGHT) for i, (c, _) in enumerate(series)}
            label = "{0} {1} suite time per run".format(site, tool)
            rows = "".join(
                "<tr><td>{0}</td><td>{1}</td><td>v{2}</td><td class='num'>{3:.1f}</td>"
                "<td class='num'>{4}</td></tr>".format(
                    esc(c), short_date(ts), esc(version), total / 60.0, count
                )
                for c, runs in series
                for ts, total, count, version in runs
            )
            boxes.append(
                "<div class='chart-box card'><h4>{0} &middot; {1} <span class='unit'>"
                "(min)</span></h4>{2}{3}<details><summary>table</summary>"
                "<div class='scroll'><table><thead><tr><th>Configuration</th><th>Date</th>"
                "<th>Version</th><th class='num'>Minutes</th><th class='num'>Vignettes"
                "</th></tr></thead><tbody>{4}</tbody></table></div></details></div>".format(
                    esc(site),
                    esc(tool),
                    legend([(config_slot[c], c) for c, _ in series]),
                    svg_suite_time(label, series, config_slot),
                    rows,
                )
            )
    return "<div class='grid-charts'>{0}</div>".format("".join(boxes))


def render_dot_plot(tool, histories, states):
    pin = CURRENT_PINS[tool]
    configs = sorted(
        (c for (c, t), s in states.items() if t == tool and not s["stale"]),
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


def render_version_timeline(tool, histories, configs):
    slot_of, versions = tool_slot_map(histories, tool)
    rows = []
    for c in configs:
        if (c, tool) not in histories:
            continue
        days = {}
        for vrows in histories[(c, tool)].values():
            for ts, rec in vrows:
                days[short_date(ts)] = (ts, drift.tool_version(rec) or "unknown")
        rows.append((c, sorted(days.values())))
    if not rows:
        return ""
    return (
        "<div class='card'><h3>{0}</h3>{1}<div class='scroll'>{2}</div></div>".format(
            esc(tool),
            legend([(slot_of(v), "v" + v) for v in versions]),
            svg_version_timeline(tool, rows, slot_of),
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


def version_marks(rows):
    """[(timestamp, version)] at the first run of each version after the first.

    First appearances only: a configuration that alternates between a new
    build and an older reference build would otherwise draw a rule at every
    run.
    """
    marks, seen = [], set()
    for ts, rec in rows:
        version = drift.tool_version(rec) or "unknown"
        if version not in seen:
            if seen:
                marks.append((ts, version))
            seen.add(version)
    return marks


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

    marks = version_marks(rows)
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
            (ts, drift.tool_version(rec) or "unknown", value, same)
            for ts, rec, value, same in series
        ]
        versions_seen.update(p[1] for p in points)
        svg, unit_shown = svg_metric_chart(title, unit, points, slot_of, drifted, marks)
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
            "<div class='note'>Faded points were measured differently from the latest "
            "run (an older metrics schema or another measurement scope), so they are "
            "context, not a comparison. Dashed rules mark version changes.{0}</div>".format(
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
        "<th class='num'>Load</th><th>Build</th><th>Baseline</th>"
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
            "<td>{14}</td></tr>".format(
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
    body = [
        "<p><a href='index.html'>&larr; All configurations</a></p>",
        "<h1>{0}</h1><p class='lede'>Site: {1}. Tools: {2}.</p>".format(
            esc(config),
            esc(site_of(config)),
            " ".join(
                "<a href='#{0}'>{0}</a>".format(esc(t)) for t in TOOLS if t in tools
            ),
        ),
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
    now = now or datetime.datetime.now()
    generated = generated or now.strftime("%Y-%m-%d %H:%M")
    os.makedirs(out_dir, exist_ok=True)

    states = {key: config_state(key[1], vs, now) for key, vs in histories.items()}
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
