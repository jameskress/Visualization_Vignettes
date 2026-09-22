#
# Visualization Vignettes
#
# plot_metrics.py -- turn the committed metric history into pictures
#
# WHY THIS WAS REWRITTEN
#
# The old plot put every configuration on one axis whose x positions were the
# UNION of every configuration's timestamps. With eleven configurations and
# sixty-seven recorded runs between them, each configuration occupied a narrow
# band of consecutive positions and then drew a straight line across the whole
# figure to its next point, through sixty positions where it had no data. The
# axis carried sixty-seven rotated timestamps, most of them belonging to some
# other machine. Switching that axis from dates to indices had already been
# tried; it moved the problem from date-space to union-of-runs-space rather
# than removing it.
#
# Worse, it was actively misleading. ex00_pvQuery's memory went from 118 MB in
# 2024 to 428 MB in 2026 and the plot drew a line straight up between them.
# Nothing regressed: the 2024 number was the harness's own resident set and
# the 2026 number is the peak of the vignette's whole process tree, because
# the first figure was measuring the wrong process (see Testing/metrics.py).
# A plot that renders a change in what a number MEANS as a change in the
# number is worse than no plot.
#
# WHAT IT DOES NOW
#
# Three ideas, and they are the whole design:
#
#   1. One panel per configuration. A configuration's runs are plotted against
#      its own run index, 1..N, so they are evenly spaced by construction and
#      no line is ever drawn across a gap that belongs to somebody else. The
#      panels share a y axis, so they stay comparable by eye.
#
#   2. A separate "latest run" bar chart. "Is Shaheen slower than the
#      workstation" is not a question about time, and answering it with a time
#      series is why the time series was unreadable. One bar per
#      configuration, most recent run, labelled with the version and the date.
#
#   3. The schema boundary is drawn, not hidden. `metrics_schema` is bumped
#      whenever a recorded field changes meaning. Records from before the
#      current schema are drawn hollow, behind a shaded band, and are excluded
#      from the latest-run comparison for the metrics whose definition moved.
#      Execution time never changed meaning, so it keeps its whole history.
#
# Marker shape still encodes the tool version, which was worth keeping.
#
# Author: James Kress, <james@jameskress.com>
#
import collections
import itertools
import json
import os

import matplotlib

# Explicit, because these run on compute nodes with no display. matplotlib
# guesses right today; it does not have to keep guessing right.
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

try:
    from metrics import METRICS_SCHEMA
except ImportError:  # pragma: no cover - plotting standalone
    METRICS_SCHEMA = 4


MARKER_SHAPES = ["o", "s", "^", "D", "P", "X", "*", "v", "<", ">"]

# Which metrics changed meaning at the current schema. Execution time did not:
# a second was a second in 2024 too, so its history plots whole.
SCHEMA_SENSITIVE = ("memory_usage_mb", "cpu_usage_percent")

METRICS = (
    ("execution_time", "Execution time (s)"),
    ("memory_usage_mb", "Peak memory (MB)"),
    ("cpu_usage_percent", "CPU (%)"),
)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _version_of(record):
    info = record.get("machine_info") or {}
    return info.get("visit_version") or info.get("paraview_version") or "unknown"


def load_history(testing_dir):
    """Every recorded run in one directory, grouped by configuration.

    Returns {config_name: [record, ...]} sorted oldest first, where each
    record carries the keys the plots need plus `timestamp`, `version` and
    `legacy` (True when it predates the current metrics schema).
    """
    if not os.path.isdir(testing_dir):
        return {}

    history = {}
    for name in sorted(os.listdir(testing_dir)):
        if not (name.startswith("performance_metrics_") and name.endswith(".json")):
            continue
        # The configuration name can itself contain underscores and dots
        # (KW61316.kaust.edu.sa, shaheen3-ppn-gpu-L40), so strip the fixed
        # prefix and suffix rather than splitting on "_".
        config = name[len("performance_metrics_") : -len(".json")]
        try:
            with open(os.path.join(testing_dir, name), "r") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            continue
        if not payload:
            continue

        rows = []
        for timestamp in sorted(payload):
            record = dict(payload[timestamp])
            record["timestamp"] = timestamp
            record["version"] = _version_of(record)
            record["legacy"] = int(record.get("metrics_schema") or 0) < METRICS_SCHEMA
            rows.append(record)
        if rows:
            history[config] = rows
    return history


def _marker_map(history):
    versions = sorted({r["version"] for rows in history.values() for r in rows})
    cycle = itertools.cycle(MARKER_SHAPES)
    return {version: next(cycle) for version in versions}


def _series(rows, metric):
    """(x, y, record) for the runs that actually carry this metric.

    x is the run's position in THIS configuration's history, so a
    configuration with three runs gets x = 1, 2, 3 whatever anyone else did.
    A record missing the metric keeps its x position -- the run happened, the
    measurement did not -- so a gap reads as a gap.
    """
    points = []
    for index, record in enumerate(rows, start=1):
        value = record.get(metric)
        if value is None:
            continue
        try:
            points.append((index, float(value), record))
        except (TypeError, ValueError):
            continue
    return points


def _thin_labels(rows, limit=5):
    """At most `limit` date labels per panel, evenly spaced, oldest and newest
    always included. Sixty-seven rotated timestamps is not a label, it is a
    smear."""
    count = len(rows)
    if count == 0:
        return [], []
    if count <= limit:
        picks = list(range(count))
    else:
        picks = sorted({int(round(i)) for i in np.linspace(0, count - 1, limit)})
    ticks = [p + 1 for p in picks]
    # Date AND time: two runs of the same configuration on the same day is
    # the normal case, and two ticks both reading "2024-10-21" is not a
    # label, it is a coincidence the reader has to untangle.
    labels = [str(rows[p]["timestamp"])[2:16].replace("T", " ") for p in picks]
    return ticks, labels


# ---------------------------------------------------------------------------
# Trend: one panel per configuration
# ---------------------------------------------------------------------------
def _trend_figure(history, marker_map, metric, ylabel, vignette, path):
    configs = sorted(history)
    columns = min(4, max(1, len(configs)))
    rows_of_panels = int(np.ceil(len(configs) / float(columns)))

    fig, axes = plt.subplots(
        rows_of_panels,
        columns,
        figsize=(4.6 * columns, 3.4 * rows_of_panels + 1.1),
        squeeze=False,
        # Deliberately NOT shared. A trend panel answers "did THIS
        # configuration move", and one 428 MB point from the current schema
        # flattens eleven panels of 2024 data into a straight line at the
        # bottom if they all share an axis. Comparing configurations against
        # each other is what the companion *_latest.png bar chart is for, and
        # a bar chart does it better than eleven sparklines ever did.
        sharey=False,
    )
    colors = plt.cm.turbo(np.linspace(0.05, 0.95, len(configs)))

    drew_legacy = False
    seen_versions = {}
    any_data = False

    for position, config in enumerate(configs):
        axis = axes[position // columns][position % columns]
        rows = history[config]
        points = _series(rows, metric)

        if not points:
            axis.text(
                0.5,
                0.5,
                "no data",
                ha="center",
                va="center",
                transform=axis.transAxes,
                fontsize=10,
                color="0.5",
            )
            axis.set_title(config, fontsize=10)
            axis.set_xticks([])
            continue

        any_data = True
        colour = colors[position]
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        axis.plot(xs, ys, "-", color=colour, linewidth=1.6, alpha=0.6, zorder=2)

        # Shade the part of this panel that predates the current schema, for
        # the metrics whose meaning changed there.
        if metric in SCHEMA_SENSITIVE:
            legacy_x = [p[0] for p in points if p[2]["legacy"]]
            if legacy_x and len(legacy_x) < len(points):
                axis.axvspan(
                    min(xs) - 0.5,
                    max(legacy_x) + 0.5,
                    color="0.85",
                    zorder=0,
                )
                axis.axvline(
                    max(legacy_x) + 0.5,
                    color="0.45",
                    linestyle="--",
                    linewidth=1.2,
                    zorder=1,
                )
                drew_legacy = True
            elif legacy_x:
                axis.axvspan(min(xs) - 0.5, max(xs) + 0.5, color="0.85", zorder=0)
                drew_legacy = True

        for x, y, record in points:
            shape = marker_map.get(record["version"], "x")
            legacy = record["legacy"] and metric in SCHEMA_SENSITIVE
            axis.plot(
                x,
                y,
                marker=shape,
                markersize=7,
                markerfacecolor="none" if legacy else colour,
                markeredgecolor=colour,
                markeredgewidth=1.4,
                linestyle="None",
                zorder=3,
            )
            seen_versions[record["version"]] = shape

        ticks, labels = _thin_labels(rows)
        axis.set_xticks(ticks)
        axis.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        axis.set_xlim(0.4, len(rows) + 0.6)
        axis.set_title(config, fontsize=10)
        axis.grid(True, axis="y", alpha=0.25)
        if position % columns == 0:
            axis.set_ylabel(ylabel, fontsize=10)

    for empty in range(len(configs), rows_of_panels * columns):
        axes[empty // columns][empty % columns].axis("off")

    if not any_data:
        plt.close(fig)
        return False

    subtitle = (
        "each panel is one configuration, x is its own run number, "
        "y is autoscaled per panel"
    )
    if drew_legacy:
        subtitle += (
            "   |   shaded: recorded before metrics_schema {0}, when this "
            "number measured something else".format(METRICS_SCHEMA)
        )
    fig.suptitle(
        "{0} - {1}\n{2}".format(ylabel, vignette, subtitle),
        fontsize=13,
    )

    handles = [
        plt.Line2D([0], [0], marker=shape, linestyle="None", color="0.2", markersize=8)
        for shape in seen_versions.values()
    ]
    if handles:
        fig.legend(
            handles,
            list(seen_versions),
            title="Tool version",
            loc="lower center",
            ncol=min(8, len(handles)),
            frameon=False,
            fontsize=9,
        )

    fig.tight_layout(rect=[0, 0.05, 1, 0.93])
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# Latest run: one bar per configuration
# ---------------------------------------------------------------------------
def _latest_figure(history, metric, ylabel, vignette, path):
    entries = []
    for config, rows in sorted(history.items()):
        # One bar per configuration *and tool version*, not per configuration.
        # A machine that has run two versions of the tool is the case this
        # suite most wants to show: collapsing to the newest record alone
        # would hide the older version's numbers entirely, which is exactly
        # the comparison a reader came for.
        seen = set()
        for record in reversed(rows):
            value = record.get(metric)
            if value is None:
                continue
            if record["version"] in seen:
                continue
            if metric in SCHEMA_SENSITIVE and record["legacy"]:
                # Comparing a schema-3 memory figure against a schema-4 one
                # is comparing two different measurements. Leave it out and
                # say so, rather than drawing a bar nobody can trust.
                continue
            seen.add(record["version"])
            entries.append((config, float(value), record))

    if not entries:
        return False

    entries.sort(key=lambda e: e[1])
    # Name the version only where a configuration contributed more than one
    # bar; on the common single-version chart the label stays the plain
    # machine name it has always been.
    bars_per_config = collections.Counter(e[0] for e in entries)
    labels = [
        "{0}\nv{1}".format(e[0], e[2]["version"]) if bars_per_config[e[0]] > 1 else e[0]
        for e in entries
    ]
    values = [e[1] for e in entries]
    colors = plt.cm.turbo(np.linspace(0.05, 0.95, len(entries)))

    fig, axis = plt.subplots(figsize=(11, 0.55 * len(entries) + 2.4))
    positions = np.arange(len(entries))
    axis.barh(positions, values, color=colors, height=0.62)
    axis.set_yticks(positions)
    axis.set_yticklabels(labels, fontsize=10)
    axis.set_xlabel(ylabel, fontsize=11)
    axis.grid(True, axis="x", alpha=0.25)
    axis.set_axisbelow(True)

    span = max(values) if values else 1.0
    for position, (config, value, record) in enumerate(entries):
        axis.text(
            value + span * 0.012,
            position,
            "{0:,.2f}   v{1}   {2}".format(
                value, record["version"], str(record["timestamp"])[:10]
            ),
            va="center",
            fontsize=8.5,
            color="0.25",
        )
    axis.set_xlim(0, span * 1.38)

    note = ""
    if metric in SCHEMA_SENSITIVE:
        # Two short lines rather than one long one: this subtitle is drawn at
        # the figure's width, and a single line of it was being clipped on the
        # narrow figures that a two-configuration chart produces.
        note = (
            "\nconfigurations older than metrics_schema {0} are omitted"
            "\n(that number measured something else)".format(METRICS_SCHEMA)
        )
    axis.set_title(
        "{0} - {1}\nmost recent run per configuration and tool version{2}".format(
            ylabel, vignette, note
        ),
        fontsize=12,
    )

    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def generate_individual_graphs(test_directory, current_sub_test):
    """Write the trend and latest-run plots for one vignette."""
    testing_dir = os.path.join(test_directory, "Testing")
    print("\tGathering metrics and creating plots in {0}".format(testing_dir))

    history = load_history(testing_dir)
    if not history:
        print("\tNo performance data found for {0}.".format(testing_dir))
        return

    marker_map = _marker_map(history)
    written = 0
    for metric, ylabel in METRICS:
        if _trend_figure(
            history,
            marker_map,
            metric,
            ylabel,
            current_sub_test,
            os.path.join(testing_dir, "{0}_comparison.png".format(metric)),
        ):
            written += 1
        if _latest_figure(
            history,
            metric,
            ylabel,
            current_sub_test,
            os.path.join(testing_dir, "{0}_latest.png".format(metric)),
        ):
            written += 1

    print("\tDone with `generate_individual_graphs` ({0} plot(s))".format(written))


def generate_combination_execution_time_plot(base_directory):
    """One figure for a whole suite: latest execution time, every vignette,
    every configuration.

    The old version of this drew a hundred and forty three time series on one
    axis. This draws the only comparison anybody actually makes from it --
    which vignette costs what, where -- as grouped bars on a log scale,
    because ex06 is fifty times the next vignette and a linear axis renders
    the other twelve as a flat line at zero.
    """
    per_vignette = {}
    configs = set()

    for name in sorted(os.listdir(base_directory)):
        testing_dir = os.path.join(base_directory, name, "Testing")
        history = load_history(testing_dir)
        if not history:
            continue
        latest = {}
        for config, rows in history.items():
            for record in reversed(rows):
                if record.get("execution_time") is not None:
                    latest[config] = float(record["execution_time"])
                    configs.add(config)
                    break
        if latest:
            per_vignette[name] = latest

    if not per_vignette:
        print("No valid performance data found.")
        return

    vignettes = sorted(per_vignette)
    configs = sorted(configs)
    colors = plt.cm.turbo(np.linspace(0.05, 0.95, len(configs)))

    fig, axis = plt.subplots(figsize=(max(12, 1.5 * len(vignettes)), 8))
    width = 0.8 / max(1, len(configs))
    base = np.arange(len(vignettes))

    for index, config in enumerate(configs):
        values = [per_vignette[v].get(config, np.nan) for v in vignettes]
        axis.bar(
            base + index * width - 0.4 + width / 2.0,
            values,
            width=width,
            label=config,
            color=colors[index],
        )

    axis.set_xticks(base)
    axis.set_xticklabels(vignettes, rotation=40, ha="right", fontsize=9)
    axis.set_yscale("log")
    axis.set_ylabel("Execution time (s), log scale", fontsize=11)
    axis.set_title(
        "Most recent execution time per vignette and configuration\n"
        "{0}".format(os.path.basename(os.path.abspath(base_directory))),
        fontsize=13,
    )
    axis.grid(True, axis="y", alpha=0.25)
    axis.set_axisbelow(True)
    axis.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=9)

    fig.tight_layout(rect=[0, 0, 0.84, 1])
    output = os.path.join(base_directory, "combined_execution_time_plot.png")
    fig.savefig(output, dpi=110)
    plt.close(fig)
    print("Combined execution time plot saved as {0}".format(output))
