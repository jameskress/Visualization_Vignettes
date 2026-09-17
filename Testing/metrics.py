#
# Visualization Vignettes
#
# metrics.py
#
# Performance metric collection and regression detection.
#
# WHAT CHANGED AND WHY
#
# The memory figure used to be `psutil.Process().memory_info().rss` -- the
# resident set of test_suite.py itself, not of the pvbatch or visit
# subprocess it had just run. Every memory_usage_mb value recorded before
# this change measured the harness measuring the test. The metric now comes
# from resource.getrusage(RUSAGE_CHILDREN), which reports the high-water mark
# of the child processes the harness actually waited on.
#
# Because the meaning of the field changed, `metrics_schema` is recorded
# alongside it. Historical entries have no such key and can be filtered out
# rather than silently compared against the new, correct numbers.
#
# `cpu_usage_percent` also used to call psutil.cpu_percent() with no
# interval, which returns 0.0 on its first call in a process -- and it was
# only ever called once. It is now derived from the child's own user+system
# time over the wall clock, which is both meaningful and independent of what
# else is running on the node.
#
# Author: James Kress, <james@jameskress.com>
#
import resource
import sys

try:
    import psutil  # pyright: ignore[reportMissingModuleSource]
except ImportError:  # pragma: no cover - psutil is in the documented venv
    psutil = None


# Bumped whenever the meaning of a recorded field changes, so plots and
# regression checks can refuse to compare across a schema boundary.
METRICS_SCHEMA = 2


def _maxrss_to_mb(maxrss):
    """Convert ru_maxrss to MB, accounting for the platform's units.

    Linux reports kilobytes; macOS and the BSDs report bytes. The repository
    is developed on macOS and run on Linux clusters, so both matter.
    """
    if sys.platform == "darwin":
        return float(maxrss) / (1024.0 * 1024.0)
    return float(maxrss) / 1024.0


def child_rusage_snapshot():
    """Capture child resource usage before launching a vignette."""
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "maxrss": usage.ru_maxrss,
        "utime": usage.ru_utime,
        "stime": usage.ru_stime,
    }


def gather_metrics(test_name, start_time, end_time, run_result=None, before=None):
    """Collect performance metrics for one vignette run.

    `run_result` is the payload run_tests.py wrote (return code, duration,
    timeout flag). `before` is a child_rusage_snapshot() taken immediately
    before the launch. Both are optional so that older call sites keep
    working, but without them the memory and CPU figures fall back to
    whole-process totals and are marked as such.
    """
    elapsed = float(end_time) - float(start_time)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)

    child_utime = after.ru_utime
    child_stime = after.ru_stime
    if before:
        child_utime -= before.get("utime", 0.0)
        child_stime -= before.get("stime", 0.0)

    # ru_maxrss for children is a high-water mark, not a running total, so it
    # cannot be differenced -- take it as-is and note when a prior snapshot
    # showed a higher mark from an earlier test in the same process.
    child_maxrss_mb = _maxrss_to_mb(after.ru_maxrss)
    measurement_scope = "children"
    if before and after.ru_maxrss <= before.get("maxrss", 0):
        measurement_scope = "children-highwater-from-earlier-test"

    cpu_seconds = child_utime + child_stime
    cpu_percent = (100.0 * cpu_seconds / elapsed) if elapsed > 0 else 0.0

    metrics = {
        "test_name": test_name,
        "metrics_schema": METRICS_SCHEMA,
        "execution_time": elapsed,
        # Retained under the original key so existing plots keep working.
        "memory_usage_mb": child_maxrss_mb,
        "memory_usage": child_maxrss_mb * 1024 * 1024,
        "memory_measurement_scope": measurement_scope,
        "cpu_usage_percent": cpu_percent,
        "cpu_seconds": cpu_seconds,
    }

    if run_result:
        metrics["returncode"] = run_result.get("returncode")
        metrics["timed_out"] = run_result.get("timed_out", False)
        metrics["run_succeeded"] = run_result.get("succeeded", False)
        if run_result.get("duration_s") is not None:
            metrics["subprocess_time"] = run_result["duration_s"]

    if psutil is not None:
        try:
            metrics["harness_rss_mb"] = psutil.Process().memory_info().rss / (
                1024.0 * 1024.0
            )
        except Exception:  # pragma: no cover - psutil edge cases
            pass

    return metrics


def detect_significant_changes(df, threshold=10, require_same_schema=True):
    """Flag a metric that regressed by more than `threshold` percent.

    Compares the two most recent runs. When `require_same_schema` is set,
    rows recorded before the metrics rewrite are excluded, because their
    memory and CPU columns measured something different and comparing across
    that boundary produces a guaranteed false positive.
    """
    print("\t\tChecking for significant changes...")

    if df is None or len(df) < 2:
        print("\tNot enough data for comparison.")
        return None

    frame = df
    if require_same_schema and "metrics_schema" in frame.columns:
        current = frame[frame["metrics_schema"] == METRICS_SCHEMA]
        if len(current) >= 2:
            frame = current
        else:
            print(
                "\t\tOnly {0} run(s) at metrics schema {1}; skipping comparison "
                "until a second comparable run exists.".format(
                    len(current), METRICS_SCHEMA
                )
            )
            return None

    metrics = [
        "execution_time",
        "memory_usage_mb",
        "cpu_usage_percent",
        "disk_usage_percent",
    ]

    for metric in metrics:
        if metric not in frame.columns:
            continue

        last_two_runs = frame[metric].dropna().tail(2).values
        if len(last_two_runs) != 2:
            continue

        previous_value, current_value = last_two_runs
        print(
            "\t\t\tComparing {0}: previous={1}, current={2}".format(
                metric, previous_value, current_value
            )
        )

        if not previous_value:
            continue

        percent_change = 100 * (current_value - previous_value) / previous_value
        if percent_change > threshold:
            print(
                "\t\t\t\tSignificant change detected for {0}: {1}% change".format(
                    metric, percent_change
                )
            )
            return {
                "Performance_stable": False,
                "metric": metric,
                "previous_value": previous_value,
                "current_value": current_value,
                "percent_change": percent_change,
            }

    print("\t\tNo significant changes found.")
    return None
