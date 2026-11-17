#
# Visualization Vignettes
#
# drift.py -- flag a run whose telemetry moved well outside its own history
#
# WHY THIS EXISTS NEXT TO THE PERFORMANCE GATE
#
# detect_significant_changes() in metrics.py compares the two most recent
# runs and fails at 10%. That catches a step change on the very run that
# makes it, and nothing else: a run that is twice as slow as the twenty
# before it passes if the run before it was also slow, and one noisy run
# fails the next one too. This module asks a different question, "is this
# run unusual for this vignette on this configuration and build?", against a
# robust summary of many earlier runs. It warns; it never fails the suite
# (that is James's call, and the gate already exists for hard failures).
#
# THE TEST
#
# For each metric, the history is the earlier runs of the same vignette on
# the same configuration (`--machine_name`, which names the machine and its
# rendering backend), the same tool version, a comparable metrics schema, and
# the same measurement scope. The build id that schema-6 records carry is not
# part of the key: one configuration runs one install of each version, and a
# key that changed with an install path would reset the history whenever a
# module moved. The dashboard shows the build id beside each run instead. Of those, the most recent WINDOW are summarised by
# their median and their median absolute deviation (MAD). The run is flagged
# when all three of these hold:
#
#   * |x - median| >= REL_FLOOR[metric] * median   (a move worth reading about)
#   * |x - median| >= ABS_FLOOR[metric]            (not a rounding-sized move)
#   * |x - median| >= K * 1.4826 * MAD, or MAD is 0 (outside the run-to-run
#                                                   noise this history shows)
#
# 1.4826 * MAD estimates the standard deviation of normal noise without being
# dragged by the outliers this is looking for, so K = 4 is about four sigma.
# The relative and absolute floors keep a very quiet history (MAD near 0)
# from flagging a 3% wobble. Fewer than MIN_HISTORY earlier runs give no
# verdict at all: three points cannot say what normal is.
#
# The thresholds were chosen from the committed history (LOCAL_VALIDATION
# 4b.16 has the measurement): at these values the existing records flag the
# runs that are known to be odd and leave ordinary run-to-run noise alone.
#
# Standard library only, so the dashboard generator can use it on a GitHub
# runner without the suite's environment.
#
# Author: James Kress, <james@jameskress.com>
#
import statistics

# The oldest schema whose CPU and memory figures mean what the current
# schema's do. Kept in step with metrics.MIN_COMPARABLE_SCHEMA, which is not
# imported because metrics.py needs psutil and this module must not.
MIN_COMPARABLE_SCHEMA = 5

K = 4.0
MAD_TO_SIGMA = 1.4826
MIN_HISTORY = 3
WINDOW = 20

# metric -> (label, unit, relative floor, absolute floor, scope field)
#
# The scope field names the record key that says how the metric was
# measured; two scopes are two different quantities and never share a
# history. None means the metric has a single definition.
METRICS = {
    "execution_time": ("execution time", "s", 0.25, 2.0, None),
    "cpu_seconds": ("CPU", "s", 0.25, 2.0, "cpu_measurement_scope"),
    "memory_usage_mb": ("peak memory", "MB", 0.25, 64.0, "memory_measurement_scope"),
    "disk_read_mb": ("disk read", "MB", 0.5, 16.0, "cpu_measurement_scope"),
    "disk_write_mb": ("disk write", "MB", 0.5, 16.0, "cpu_measurement_scope"),
    "io_read_mb": ("I/O read", "MB", 0.5, 16.0, "io_scope"),
    "io_write_mb": ("I/O write", "MB", 0.5, 16.0, "io_scope"),
    "energy_joules": ("energy", "J", 0.25, 500.0, "energy_scope"),
}

# Wall clock never changed meaning; every other figure did at schema 5.
SCHEMA_FREE = ("execution_time",)


def tool_version(record):
    info = record.get("machine_info") or {}
    if not isinstance(info, dict):
        return None
    return info.get("paraview_version") or info.get("visit_version")


def comparable(metric, record):
    """True when this record's `metric` can share a history with today's."""
    if metric in SCHEMA_FREE:
        return True
    try:
        return int(record.get("metrics_schema") or 0) >= MIN_COMPARABLE_SCHEMA
    except (TypeError, ValueError):
        return False


def history_key(metric, record):
    """Everything two runs must share for one to be judged against the other."""
    scope_field = METRICS[metric][4]
    return (
        record.get("test_name"),
        tool_version(record),
        record.get(scope_field) if scope_field else None,
    )


def _value(record, metric):
    value = record.get(metric)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def judge(value, history, metric):
    """Judge one value against a list of earlier values of the same metric.

    Returns a dict with the verdict ("drift", "ok" or "insufficient") and
    the numbers behind it, so a reader can see how far out it was.
    """
    label, unit, rel_floor, abs_floor, _ = METRICS[metric]
    history = history[-WINDOW:]
    result = {
        "metric": metric,
        "label": label,
        "unit": unit,
        "value": value,
        "history_runs": len(history),
    }
    if len(history) < MIN_HISTORY:
        result["verdict"] = "insufficient"
        return result
    median = statistics.median(history)
    mad = statistics.median([abs(item - median) for item in history])
    sigma = MAD_TO_SIGMA * mad
    deviation = value - median
    result.update(
        median=median,
        mad=mad,
        percent=(100.0 * deviation / median) if median else None,
        robust_z=(deviation / sigma) if sigma else None,
    )
    outside_noise = sigma == 0 or abs(deviation) >= K * sigma
    big_enough = (
        abs(deviation) >= rel_floor * abs(median) and abs(deviation) >= abs_floor
    )
    result["verdict"] = "drift" if (outside_noise and big_enough) else "ok"
    return result


def check_record(record, earlier):
    """Every metric of `record` judged against `earlier` (oldest first).

    `earlier` may hold any records from the same history file; the ones that
    do not share this record's history key are ignored here.
    """
    results = []
    for metric in METRICS:
        value = _value(record, metric)
        if value is None or not comparable(metric, record):
            continue
        key = history_key(metric, record)
        history = [
            _value(other, metric)
            for other in earlier
            if comparable(metric, other)
            and history_key(metric, other) == key
            and _value(other, metric) is not None
        ]
        results.append(judge(value, history, metric))
    return results


def check_history(records):
    """Judge every record against the ones before it.

    `records` is a list of (timestamp, record) for one configuration's
    history file, in any order. Returns {timestamp: [results]} for the
    dashboard, which marks every drifted point, not only the latest.

    The repeats of one --repeat run are judged as one run, by their median
    (collapse_repeats), and every repeat carries that run's verdict: judged
    one by one, a repeat's siblings would count as independent history and
    their narrow spread would call ordinary run-to-run noise drift.
    """
    folded = collapse_repeats(dict(records))
    ordered = sorted(folded.items())
    run_verdicts = {}
    for index, (timestamp, record) in enumerate(ordered):
        earlier = [other for _, other in ordered[:index]]
        run_verdicts[timestamp] = check_record(record, earlier)
    # collapse_repeats files a run under its last repeat's timestamp.
    run_last = {}
    for timestamp, record in records:
        key = _repeat_key(record)
        if key is not None and timestamp > run_last.get(key, ""):
            run_last[key] = timestamp
    verdicts = {}
    for timestamp, record in records:
        key = _repeat_key(record)
        verdicts[timestamp] = run_verdicts.get(
            run_last[key] if key is not None else timestamp, []
        )
    return verdicts


def _repeat_key(record):
    """The (run_id, test, version) a repeat folds under, or None for a single run.

    The test name too: one run id covers every vignette of an invocation,
    and a history passed in may hold more than one vignette.
    """
    if isinstance(record, dict) and record.get("repeat") and record.get("run_id"):
        return (record["run_id"], record.get("test_name"), tool_version(record))
    return None


def scope_of(metric):
    """The field naming how `metric` was measured, or None when it has none.

    The METRICS entries, plus the figures recorded beside them under the
    same measurement: CPU percentages and splits share the CPU scope, the
    byte and RSS memory figures the memory scope, the I/O call counts the
    I/O scope, the energy split the energy scope. The one map: the fold,
    the performance gate (metrics.py) and the dashboard all use it.
    """
    if metric in METRICS:
        return METRICS[metric][4]
    if metric.startswith("cpu_"):
        return "cpu_measurement_scope"
    if metric.startswith("memory_"):
        return "memory_measurement_scope"
    if metric.startswith("io_"):
        return "io_scope"
    if metric.startswith("energy_"):
        return "energy_scope"
    return None


def collapse_repeats(history):
    """{timestamp: record} with each repeated run folded into one record.

    `test_suite.py --repeat N` appends N records of one vignette, sharing a
    run_id and each carrying `repeat`. Judged one by one, each would be
    compared with its own siblings: the performance gate would compare the
    last repeat with the one before it, and drift would count this run's
    repeats as history. Folded, a repeated run is one record under the
    timestamp of its last repeat, every numeric field the median of its
    successful repeats (a scoped figure over those measured in the last
    one's scope), with `repeat_values` keeping each metric's individual
    values.
    Records without `repeat` pass through unchanged.
    """
    groups, out = {}, {}
    for timestamp, record in sorted(history.items()):
        key = _repeat_key(record)
        if key is not None:
            groups.setdefault(key, []).append((timestamp, record))
        else:
            out[timestamp] = record
    for members in groups.values():
        timestamp, last = members[-1]
        folded = dict(last)
        # A failed repeat's time measures a crash, not the vignette: the
        # median is taken over the repeats that ran, and the folded run
        # succeeded only if every repeat did. All failed: all are kept.
        succeeded = [m for m in members if m[1].get("run_succeeded") is not False]
        pool = succeeded or members
        folded["run_succeeded"] = len(succeeded) == len(members)
        reference = pool[-1][1]
        values = {}
        numeric = {
            key
            for _, record in members
            for key in record
            if _value(record, key) is not None
        }
        for metric in sorted(numeric):
            # A scoped figure (CPU, memory) is folded only over repeats
            # measured like the last one used, whose scope the record keeps.
            scope_field = scope_of(metric)
            usable = [
                record
                for _, record in pool
                if not scope_field
                or record.get(scope_field) == reference.get(scope_field)
            ]
            numbers = [_value(record, metric) for record in usable]
            numbers = [n for n in numbers if n is not None]
            if numbers:
                folded[metric] = statistics.median(numbers)
                values[metric] = numbers
                if scope_field:
                    folded[scope_field] = reference.get(scope_field)
            else:
                # Only repeats that do not count measured it.
                folded.pop(metric, None)
        folded["repeat_values"] = {m: values[m] for m in METRICS if m in values}
        folded["repeat"] = dict(last["repeat"], folded=len(members))
        out[timestamp] = folded
    return dict(sorted(out.items()))


def check_latest(history, timestamp=None):
    """Drift warnings for one record of a {timestamp: record} history.

    The record at `timestamp`, judged against those before it; the newest
    record when `timestamp` is None.
    """
    if not history:
        return []
    ordered = sorted(history.items())
    if timestamp is None:
        timestamp = ordered[-1][0]
    if timestamp not in history:
        return []
    earlier = [record for ts, record in ordered if ts < timestamp]
    results = check_record(history[timestamp], earlier)
    return [item for item in results if item["verdict"] == "drift"]


def describe(result):
    """One line for the harness summary."""
    percent = result.get("percent")
    z = result.get("robust_z")
    return (
        "{label} {value:.1f} {unit} vs median {median:.1f} over {runs} runs "
        "({pct}{z})".format(
            label=result["label"],
            value=result["value"],
            unit=result["unit"],
            median=result["median"],
            runs=result["history_runs"],
            pct="{0:+.0f}%".format(percent) if percent is not None else "n/a",
            z=", {0:+.1f} robust sigma".format(z) if z is not None else "",
        )
    )
