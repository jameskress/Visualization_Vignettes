#!/usr/bin/env python3
#
# Visualization Vignettes
#
# dashboard.py -- a static results dashboard from the committed history
#
# Reads every ParaView_Vignettes/*/Testing/performance_metrics_<config>.json
# and VisIt_Vignettes/*/Testing/performance_metrics_<config>.json and writes
# a small static site: an index of every configuration by site, and one page
# per configuration with each vignette's pass/fail history, its telemetry
# over time, its drift warnings (drift.py), and the build and baselines each
# run used. .github/workflows/dashboard.yml publishes it to GitHub Pages.
#
#   python3 Testing/dashboard.py --out _site
#
# Standard library only, so it runs on a bare GitHub runner. Charts are
# inline SVG with a few lines of script for the hover tooltip; the pages
# work without the script, minus the tooltip.
#
# What it deliberately leaves out: host names (machine_info.node) and
# executable paths. On the clusters those name nodes and module paths that
# stay out of anything public; the records name a build by a hash instead.
#
# Author: James Kress, <james@jameskress.com>
#
import argparse
import datetime
import glob
import html
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drift  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITES = (("ParaView", "ParaView_Vignettes"), ("VisIt", "VisIt_Vignettes"))
VIGNETTE_RE = re.compile(r"^ex(\d+)_")

# Charted metrics, in display order. Each chart holds one metric (one axis).
CHARTS = [
    ("execution_time", "Execution time", "s"),
    ("cpu_seconds", "CPU time", "s"),
    ("memory_usage_mb", "Peak memory", "MB"),
    ("disk_read_mb", "Disk read (Slurm)", "MB"),
    ("disk_write_mb", "Disk write (Slurm)", "MB"),
    ("io_read_mb", "Storage read (process tree)", "MB"),
    ("io_write_mb", "Storage write (process tree)", "MB"),
    ("energy_joules", "Energy", "J"),
]
SCOPE_FIELD = {metric: spec[4] for metric, spec in drift.METRICS.items()}

# Categorical slots in fixed order (dataviz reference palette). A tool
# version keeps its slot on every page: colour follows the entity.
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


def site_of(config):
    lowered = config.lower()
    if lowered.startswith("shaheen"):
        return "Shaheen"
    if lowered.startswith("ibex"):
        return "Ibex"
    if lowered.startswith("kw61316"):
        return "Workstation"
    return "Other"


def version_key(text):
    parts = []
    for item in re.split(r"[.\-]", str(text or "")):
        parts.append((0, int(item)) if item.isdigit() else (1, item))
    return parts


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


def status_of(record):
    """("pass" | "fail" | "ran" | "unknown", explanation)."""
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
        return "ran", "ran cleanly; comparison verdicts not recorded before schema 6"
    if record.get("run_succeeded") is False:
        return "fail", "run failed"
    return "unknown", "no verdict recorded"


def chart_points(rows, metric):
    """The rows whose `metric` can be charted with the latest run's.

    Same rule as drift.py and plot_metrics.py: only runs at a comparable
    schema and under the latest run's measurement scope, so a change in what
    a number means is never drawn as a change in the number.
    """
    scope_field = SCOPE_FIELD.get(metric)
    comparable = [(ts, rec) for ts, rec in rows if drift.comparable(metric, rec)]
    if not comparable:
        return []
    if scope_field:
        # The latest run sets the scope even when it has no value (an srun
        # run whose accounting was refused): older runs measured another
        # way must not stand in for it.
        latest_scope = comparable[-1][1].get(scope_field)
        comparable = [
            (ts, rec) for ts, rec in comparable if rec.get(scope_field) == latest_scope
        ]
    return [
        (ts, rec)
        for ts, rec in comparable
        if isinstance(rec.get(metric), (int, float))
        and not isinstance(rec.get(metric), bool)
    ]


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def fmt(value, digits=1):
    if value is None:
        return ""
    if isinstance(value, float):
        if abs(value) >= 1000:
            return "{0:,.0f}".format(value)
        return "{0:.{1}f}".format(value, digits)
    return str(value)


def short_date(timestamp):
    return str(timestamp)[:10]


def page_name(config):
    """A configuration's page; never index.html, which is the overview."""
    name = re.sub(r"[^A-Za-z0-9._-]", "_", config) + ".html"
    return "config-" + name if name.lower() == "index.html" else name


def nice_ticks(value, target=4):
    """Round tick values from 0 to at least `value`: 1, 2, 2.5 or 5 x 10^k."""
    if value <= 0:
        return [0.0, 1.0]
    raw = value / float(target)
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    count = int(math.ceil(value / step - 1e-9))
    return [step * k for k in range(count + 1)]


def svg_chart(title, unit, series_points, slot_of, drifted):
    """One metric, one axis. `series_points` is [(version, [(i, ts, value, rec)])].

    x is the run's position in this vignette's history (evenly spaced, so a
    year with no runs takes no room), y starts at zero.
    """
    width, height = 360, 170
    left, right, top, bottom = 52, 12, 10, 26
    all_points = [p for _, pts in series_points for p in pts]
    if not all_points:
        return ""
    xs = [p[0] for p in all_points]
    x_min, x_max = min(xs), max(xs)
    ticks = nice_ticks(max(p[2] for p in all_points))
    y_max = ticks[-1]

    def sx(i):
        if x_max == x_min:
            return left + (width - left - right) / 2.0
        return left + (i - x_min) * (width - left - right) / float(x_max - x_min)

    def sy(v):
        return top + (height - top - bottom) * (1 - v / y_max)

    parts = [
        '<svg class="chart" viewBox="0 0 {0} {1}" role="img" '
        'aria-label="{2} per run">'.format(width, height, esc(title))
    ]
    for value in ticks:
        y = sy(value)
        parts.append(
            '<line class="grid" x1="{0}" x2="{1}" y1="{2:.1f}" y2="{2:.1f}"/>'.format(
                left, width - right, y
            )
        )
        parts.append(
            '<text class="tick" x="{0}" y="{1:.1f}" text-anchor="end">{2}</text>'.format(
                left - 6, y + 3.5, esc("{0:,.6g}".format(value))
            )
        )
    parts.append(
        '<line class="axis" x1="{0}" x2="{1}" y1="{2:.1f}" y2="{2:.1f}"/>'.format(
            left, width - right, sy(0)
        )
    )
    first = min(all_points, key=lambda p: p[0])
    last = max(all_points, key=lambda p: p[0])
    parts.append(
        '<text class="tick" x="{0}" y="{1}" text-anchor="start">{2}</text>'.format(
            left, height - 8, esc(short_date(first[1]))
        )
    )
    if last[0] != first[0]:
        parts.append(
            '<text class="tick" x="{0}" y="{1}" text-anchor="end">{2}</text>'.format(
                width - right, height - 8, esc(short_date(last[1]))
            )
        )
    for version, points in series_points:
        slot = slot_of(version)
        if len(points) > 1:
            path = " ".join(
                "{0}{1:.1f},{2:.1f}".format("M" if n == 0 else "L", sx(p[0]), sy(p[2]))
                for n, p in enumerate(points)
            )
            parts.append('<path class="line s{0}" d="{1}"/>'.format(slot, path))
        for i, timestamp, value, record in points:
            is_drift = (timestamp, title) in drifted
            tip = "{0} | v{1} | {2} {3}{4}".format(
                short_date(timestamp),
                version,
                fmt(value, 2),
                unit,
                " | DRIFT: " + drifted[(timestamp, title)] if is_drift else "",
            )
            parts.append(
                '<circle class="dot s{0}{1}" cx="{2:.1f}" cy="{3:.1f}" r="{4}" '
                'data-tip="{5}"><title>{5}</title></circle>'.format(
                    slot,
                    " drift" if is_drift else "",
                    sx(i),
                    sy(value),
                    6 if is_drift else 4,
                    esc(tip),
                )
            )
    parts.append("</svg>")
    return "".join(parts)


def legend(versions, slot_of):
    if len(versions) < 2:
        return ""
    items = "".join(
        '<span class="key"><span class="swatch s{0}"></span>v{1}</span>'.format(
            slot_of(v), esc(v)
        )
        for v in versions
    )
    return '<div class="legend">{0}</div>'.format(items)


STATUS_GLYPH = {
    "pass": "&#10003;",
    "fail": "&#10007;",
    "ran": "&#9675;",
    "unknown": "?",
}
STATUS_LABEL = {
    "pass": "pass",
    "fail": "fail",
    "ran": "ran (no verdicts)",
    "unknown": "unknown",
}


def status_chip(status, detail=""):
    return '<span class="st st-{0}" title="{1}">{2} {3}</span>'.format(
        status, esc(detail), STATUS_GLYPH[status], STATUS_LABEL[status]
    )


def baseline_text(record):
    baseline = record.get("baseline")
    if not isinstance(baseline, dict):
        return ""
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
    return "; ".join(bits)


def build_text(record):
    build = record.get("build")
    if not isinstance(build, dict):
        return ""
    bits = [build.get("id") or ""]
    if build.get("opengl_window"):
        bits.append(
            str(build["opengl_window"]).replace("vtk", "").replace("RenderWindow", "")
        )
    if build.get("launcher"):
        bits.append(str(build["launcher"]))
    return " ".join(b for b in bits if b)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;
--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--ring:rgba(11,11,11,.10);--good:#0ca30c;--warn:#fab219;--bad:#d03b3b;
%(light)s}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);%(dark)s}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;
--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;
--ring:rgba(255,255,255,.10);%(dark)s}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 8px}
h3{font-size:15px;margin:0}
p.lede,.note{color:var(--ink2);max-width:72ch}
a{color:var(--ink)}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:8px;
padding:12px 14px;margin:10px 0}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%%;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--grid);
white-space:nowrap;vertical-align:top}
th{color:var(--ink2);font-weight:600;font-size:12px}
td.num,th.num{text-align:right}
.st{font-size:12px;white-space:nowrap}
.st-pass{color:var(--good)}.st-fail{color:var(--bad);font-weight:600}
.st-ran,.st-unknown{color:var(--muted)}
.drift-flag{color:var(--ink);background:color-mix(in srgb,var(--warn) 35%%,transparent);
border-radius:4px;padding:0 5px;font-size:12px}
.grid-charts{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));
gap:12px;margin-top:8px}
.chart-box h4{margin:0;font-size:13px;font-weight:600}
.chart-box .unit{color:var(--muted);font-weight:400}
svg.chart{width:100%%;height:auto;display:block}
svg .grid{stroke:var(--grid);stroke-width:1}
svg .axis{stroke:var(--axis);stroke-width:1}
svg .tick{fill:var(--muted);font-size:10px}
svg .line{fill:none;stroke-width:2}
svg .dot{stroke:var(--surface);stroke-width:2}
svg .dot.drift{stroke:var(--ink);stroke-width:2}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--ink2);
margin:6px 0}
.key{display:inline-flex;align-items:center;gap:6px}
.swatch{width:10px;height:10px;border-radius:50%%;display:inline-block}
details{margin:8px 0}summary{cursor:pointer;color:var(--ink2)}
.strip{display:flex;gap:2px;flex-wrap:nowrap}
.cell{width:14px;height:14px;border-radius:3px;display:inline-block;
font-size:10px;line-height:14px;text-align:center;color:#fff}
.cell.pass{background:var(--good)}.cell.fail{background:var(--bad)}
.cell.ran{background:var(--axis)}.cell.unknown{background:var(--grid);color:var(--ink2)}
.cell.drift{outline:2px solid var(--warn);outline-offset:1px}
#tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);
border:1px solid var(--ring);border-radius:6px;padding:4px 8px;font-size:12px;
box-shadow:0 2px 8px rgba(0,0,0,.15);display:none;z-index:9}
footer{color:var(--muted);font-size:12px;margin-top:40px}
"""

SCRIPT = """
<div id="tip"></div>
<script>
(function(){var t=document.getElementById('tip');
document.addEventListener('mouseover',function(e){var d=e.target.closest('[data-tip]');
if(!d){t.style.display='none';return;}t.textContent=d.getAttribute('data-tip');
t.style.display='block';});
document.addEventListener('mousemove',function(e){t.style.left=(e.clientX+12)+'px';
t.style.top=(e.clientY+12)+'px';});})();
</script>
"""


def css():
    def slots(colors):
        rules = "".join("--s{0}:{1};".format(i, c) for i, c in enumerate(colors))
        return rules

    base = CSS % {"light": slots(SLOTS_LIGHT), "dark": slots(SLOTS_DARK)}
    classes = "".join(
        ".s{0}{{stroke:var(--s{0})}}circle.s{0}{{fill:var(--s{0})}}"
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
        "Drift rule: Testing/README.md, “Drift warnings”.</footer>"
        "</main>{4}</body></html>"
    ).format(esc(title), css(), body, esc(generated), SCRIPT)


def drift_by_record(rows):
    """{timestamp: [drift results]} for one vignette's history."""
    verdicts = drift.check_history(rows)
    return {
        ts: [r for r in results if r["verdict"] == "drift"]
        for ts, results in verdicts.items()
    }


def latest_run(vignettes):
    """The newest record of each vignette, with its drift list."""
    latest = []
    for vignette in sorted(vignettes, key=lambda v: int(VIGNETTE_RE.match(v).group(1))):
        rows = vignettes[vignette]
        drifts = drift_by_record(rows)
        timestamp, record = rows[-1]
        latest.append((vignette, timestamp, record, drifts.get(timestamp, [])))
    return latest


def config_summary(vignettes):
    latest = latest_run(vignettes)
    counts = {"pass": 0, "fail": 0, "ran": 0, "unknown": 0}
    drifting = 0
    last = ""
    versions = set()
    for _, timestamp, record, drifts in latest:
        counts[status_of(record)[0]] += 1
        drifting += 1 if drifts else 0
        last = max(last, timestamp)
        versions.add(drift.tool_version(record))
    return counts, drifting, last, sorted(v for v in versions if v)


def render_index(histories, generated):
    by_site = {}
    for (config, tool), vignettes in histories.items():
        by_site.setdefault(site_of(config), {}).setdefault(config, {})[tool] = vignettes
    body = [
        "<h1>Visualization Vignettes results</h1>",
        "<p class='lede'>The regression suite's committed history, per site and "
        "configuration. Each configuration page has every vignette's pass/fail "
        "history, its execution time, CPU, memory and other telemetry over time, "
        "the build and baselines each run used, and drift warnings: runs that "
        "moved well outside that vignette's own history. Drift warnings do not "
        "fail the suite.</p>",
    ]
    for site in ("Workstation", "Ibex", "Shaheen", "Other"):
        configs = by_site.get(site)
        if not configs:
            continue
        body.append("<h2>{0}</h2><div class='card scroll'><table>".format(esc(site)))
        body.append(
            "<tr><th>Configuration</th><th>Tool</th><th>Latest version</th>"
            "<th>Last run</th><th>Latest run per vignette</th>"
            "<th class='num'>Drifting</th></tr>"
        )
        for config in sorted(configs):
            for tool in ("ParaView", "VisIt"):
                vignettes = configs[config].get(tool)
                if not vignettes:
                    continue
                counts, drifting, last, versions = config_summary(vignettes)
                chips = " ".join(
                    status_chip(s) + " " + str(counts[s])
                    for s in ("pass", "fail", "ran", "unknown")
                    if counts[s]
                )
                body.append(
                    "<tr><td><a href='{0}#{1}'>{2}</a></td><td>{1}</td>"
                    "<td>{3}</td><td>{4}</td><td>{5}</td><td class='num'>{6}</td>"
                    "</tr>".format(
                        esc(page_name(config)),
                        esc(tool),
                        esc(config),
                        esc(versions[-1] if versions else ""),
                        esc(short_date(last)),
                        chips,
                        "<span class='drift-flag'>{0}</span>".format(drifting)
                        if drifting
                        else "0",
                    )
                )
        body.append("</table></div>")
    body.append(
        "<p class='note'>Before metrics schema 6 the records held only whether "
        "the run itself succeeded, so older runs show <em>ran</em> rather than "
        "a pass or fail of the image and numeric gates.</p>"
    )
    return page("Vignette results", "".join(body), generated)


def render_tool_section(config, tool, vignettes, slot_of):
    out = ["<h2 id='{0}'>{0}</h2>".format(esc(tool))]
    latest = latest_run(vignettes)

    # Latest run table
    out.append("<div class='card scroll'><h3>Latest run of each vignette</h3><table>")
    out.append(
        "<tr><th>Vignette</th><th>Date</th><th>Version</th><th>Result</th>"
        "<th>Image</th><th>Numeric</th><th class='num'>Time (s)</th>"
        "<th class='num'>CPU (s)</th><th class='num'>Memory (MB)</th>"
        "<th>Build</th><th>Baseline</th><th>Drift</th></tr>"
    )
    for vignette, timestamp, record, drifts in latest:
        status, detail = status_of(record)
        verdicts = record.get("verdicts") or {}
        out.append(
            "<tr><td><a href='#{0}-{1}'>{1}</a></td><td>{2}</td><td>{3}</td>"
            "<td>{4}</td><td>{5}</td><td>{6}</td><td class='num'>{7}</td>"
            "<td class='num'>{8}</td><td class='num'>{9}</td><td>{10}</td>"
            "<td>{11}</td><td>{12}</td></tr>".format(
                esc(tool),
                esc(vignette),
                esc(short_date(timestamp)),
                esc(drift.tool_version(record)),
                status_chip(status, detail),
                esc(verdicts.get("image") or ""),
                esc(verdicts.get("numeric") or ""),
                fmt(record.get("execution_time")),
                fmt(record.get("cpu_seconds")),
                fmt(record.get("memory_usage_mb"), 0),
                esc(build_text(record)),
                esc(baseline_text(record)),
                " ".join(
                    "<span class='drift-flag' title='{0}'>{1}</span>".format(
                        esc(drift.describe(d)), esc(d["label"])
                    )
                    for d in drifts
                ),
            )
        )
    out.append("</table></div>")

    # Per vignette
    for vignette, _, _, _ in latest:
        rows = vignettes[vignette]
        drifts = drift_by_record(rows)
        out.append(
            "<div class='card' id='{0}-{1}'><h3>{1}</h3>".format(
                esc(tool), esc(vignette)
            )
        )
        # Pass/fail strip, newest 60
        cells = []
        for timestamp, record in rows[-60:]:
            status, detail = status_of(record)
            drifted = drifts.get(timestamp)
            tip = "{0} | v{1} | {2}{3}".format(
                short_date(timestamp),
                drift.tool_version(record),
                detail,
                (" | drift: " + ", ".join(d["label"] for d in drifted))
                if drifted
                else "",
            )
            cells.append(
                "<span class='cell {0}{1}' data-tip='{2}' title='{2}'>{3}</span>".format(
                    status,
                    " drift" if drifted else "",
                    esc(tip),
                    STATUS_GLYPH[status],
                )
            )
        out.append(
            "<div class='note'>Run history, oldest to newest "
            "(&#10003; pass, &#10007; fail, &#9675; ran with no verdicts recorded, "
            "outlined: drift)</div><div class='scroll'><div class='strip'>{0}"
            "</div></div>".format("".join(cells))
        )

        index_of = {ts: i for i, (ts, _) in enumerate(rows)}
        charts = []
        versions_seen = []
        for metric, title, unit in CHARTS:
            points = chart_points(rows, metric)
            if not points:
                continue
            drifted = {}
            for ts, results in drifts.items():
                for r in results:
                    if r["metric"] == metric:
                        drifted[(ts, title)] = drift.describe(r)
            series = {}
            for ts, rec in points:
                version = drift.tool_version(rec) or "unknown"
                series.setdefault(version, []).append(
                    (index_of[ts], ts, float(rec[metric]), rec)
                )
            ordered = sorted(series.items(), key=lambda item: version_key(item[0]))
            for version, _ in ordered:
                if version not in versions_seen:
                    versions_seen.append(version)
            svg = svg_chart(title, unit, ordered, slot_of, drifted)
            charts.append(
                "<div class='chart-box'><h4>{0} <span class='unit'>({1})</span></h4>"
                "{2}</div>".format(esc(title), esc(unit), svg)
            )
        if charts:
            out.append(
                legend(sorted(versions_seen, key=version_key), slot_of)
                + "<div class='grid-charts'>{0}</div>".format("".join(charts))
            )
            out.append(
                "<div class='note'>Each chart shows only runs measured the same "
                "way as the latest one (metrics schema and measurement scope); "
                "x is the run's position in this history.</div>"
            )

        # All runs table
        out.append(
            "<details><summary>All {0} runs</summary><div class='scroll'>"
            "<table>".format(len(rows))
        )
        out.append(
            "<tr><th>Date</th><th>Run id</th><th>Version</th><th>Result</th>"
            "<th class='num'>Time (s)</th><th class='num'>CPU (s)</th>"
            "<th class='num'>Memory (MB)</th><th class='num'>Read (MB)</th>"
            "<th class='num'>Write (MB)</th><th class='num'>Energy (J)</th>"
            "<th class='num'>Load</th><th>Build</th><th>Baseline</th>"
            "<th>Schema</th><th>Scope (CPU / memory)</th></tr>"
        )
        for timestamp, record in reversed(rows):
            status, detail = status_of(record)
            read = record.get("io_read_mb", record.get("disk_read_mb"))
            write = record.get("io_write_mb", record.get("disk_write_mb"))
            out.append(
                "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td>"
                "<td class='num'>{4}</td><td class='num'>{5}</td>"
                "<td class='num'>{6}</td><td class='num'>{7}</td>"
                "<td class='num'>{8}</td><td class='num'>{9}</td>"
                "<td class='num'>{10}</td><td>{11}</td><td>{12}</td>"
                "<td>{13}</td><td>{14}</td></tr>".format(
                    esc(str(timestamp)[:19].replace("T", " ")),
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
                    esc(build_text(record)),
                    esc(baseline_text(record)),
                    esc(record.get("metrics_schema") or ""),
                    esc(
                        "{0} / {1}".format(
                            record.get("cpu_measurement_scope") or "",
                            record.get("memory_measurement_scope") or "",
                        )
                        if record.get("cpu_measurement_scope")
                        else ""
                    ),
                )
            )
        out.append("</table></div></details></div>")
    return "".join(out)


def render_config(config, tools, slot_maps, generated):
    body = [
        "<p><a href='index.html'>&larr; All configurations</a></p>",
        "<h1>{0}</h1><p class='lede'>Site: {1}. Tools: {2}.</p>".format(
            esc(config),
            esc(site_of(config)),
            " ".join(
                "<a href='#{0}'>{0}</a>".format(esc(t))
                for t in ("ParaView", "VisIt")
                if t in tools
            ),
        ),
    ]
    for tool in ("ParaView", "VisIt"):
        if tool in tools:
            body.append(render_tool_section(config, tool, tools[tool], slot_maps[tool]))
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


def build_site(out_dir, repo_root=REPO_ROOT, generated=None):
    histories = load_histories(repo_root)
    generated = generated or datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    os.makedirs(out_dir, exist_ok=True)

    # A version keeps one slot everywhere: colour follows the entity.
    slot_maps = {}
    for tool in ("ParaView", "VisIt"):
        versions = sorted(
            {
                drift.tool_version(rec) or "unknown"
                for (config, t), vignettes in histories.items()
                if t == tool
                for rows in vignettes.values()
                for _, rec in rows
            },
            key=version_key,
        )
        mapping = {v: i % len(SLOTS_LIGHT) for i, v in enumerate(versions)}
        slot_maps[tool] = lambda v, m=mapping: m.get(v, 0)

    with open(os.path.join(out_dir, "index.html"), "w") as handle:
        handle.write(render_index(histories, generated))

    by_config = {}
    for (config, tool), vignettes in histories.items():
        by_config.setdefault(config, {})[tool] = vignettes
    for config, tools in by_config.items():
        with open(os.path.join(out_dir, page_name(config)), "w") as handle:
            handle.write(render_config(config, tools, slot_maps, generated))

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
