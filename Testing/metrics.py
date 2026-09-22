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
METRICS_SCHEMA = 4


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

    # Memory, in order of preference.
    #
    # run_tests.py samples the vignette's own process tree while it runs and
    # records the peak in run_result.json. That is the only figure here that
    # describes THIS vignette.
    #
    # resource.getrusage(RUSAGE_CHILDREN).ru_maxrss is the fallback, and it
    # is a poor one: it is a high-water mark over every child this process
    # has ever reaped, and it never decreases. test_suite.py runs all
    # thirteen vignettes from a single process, so after ex06 peaked at
    # 62 GB, ex07 through ex12 each recorded 61965.6 MB -- ex06's number,
    # written into their committed history and then compared against by the
    # performance gate. The scope string used to flag this and the wrong
    # number was recorded anyway.
    #
    # When neither figure is trustworthy the metric is omitted rather than
    # filled in from a different test: a missing number is a gap, a wrong one
    # is a false baseline.
    sampled_peak_mb = None
    if run_result and run_result.get("peak_rss_mb"):
        sampled_peak_mb = float(run_result["peak_rss_mb"])

    child_maxrss_mb = _maxrss_to_mb(after.ru_maxrss)
    stale_highwater = bool(before and after.ru_maxrss <= before.get("maxrss", 0))

    if sampled_peak_mb is not None:
        child_maxrss_mb = sampled_peak_mb
        measurement_scope = "child-tree-sampled"
    elif stale_highwater:
        child_maxrss_mb = None
        measurement_scope = "unavailable-highwater-from-earlier-test"
    else:
        measurement_scope = "children-highwater"

    # CPU time has the same shape of problem as memory, and it bites VisIt
    # hardest. RUSAGE_CHILDREN counts only the processes this harness reaped
    # itself. `visit -cli` forks a viewer, an mdserver and a compute engine,
    # and the engine is where all the render and query time goes -- so the
    # first VisIt suite run put ex06 at 13% CPU over 207 seconds while its
    # engine held 33 GB. run_tests.py now samples the whole tree; prefer that
    # when it is there, and say which one was used.
    cpu_scope = "children-rusage"
    cpu_seconds = child_utime + child_stime
    if run_result and run_result.get("tree_cpu_seconds"):
        cpu_seconds = float(run_result["tree_cpu_seconds"])
        cpu_scope = "child-tree-sampled"
    cpu_percent = (100.0 * cpu_seconds / elapsed) if elapsed > 0 else 0.0

    metrics = {
        "test_name": test_name,
        "metrics_schema": METRICS_SCHEMA,
        "execution_time": elapsed,
        "memory_measurement_scope": measurement_scope,
        "cpu_measurement_scope": cpu_scope,
        "cpu_usage_percent": cpu_percent,
        "cpu_seconds": cpu_seconds,
    }

    # Retained under the original key so existing plots keep working, but
    # only when there is a real number to put there.
    if child_maxrss_mb is not None:
        metrics["memory_usage_mb"] = child_maxrss_mb
        metrics["memory_usage"] = child_maxrss_mb * 1024 * 1024

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


def _tool_versions(frame):
    """Per-row tool version, read from the machine_info each record carries.

    Returns None when the column is absent, which is the case for the oldest
    records in some histories.
    """
    if "machine_info" not in frame.columns:
        return None

    def one(info):
        if not isinstance(info, dict):
            return None
        return info.get("paraview_version") or info.get("visit_version")

    return frame["machine_info"].map(one)


def detect_significant_changes(df, threshold=10, require_same_schema=True):
    """Flag a metric that moved by more than `threshold` percent.

    Compares the two most recent runs. Two kinds of difference are reported,
    and they are not the same thing:

    * **Same tool version, metric moved.** A regression. Fails the run.
    * **Different tool version.** Not a regression: the software itself
      changed. Reported in both directions and at any size, because comparing
      versions is a large part of what this suite is for (a new build that
      costs 2x the memory is worth knowing about), but it does not fail the
      run. The newest record is often deliberately an *older* build, such as
      the cluster version kept as a local reference, in which case a "slower,
      fatter" result is the expected answer rather than a problem.

    When `require_same_schema` is set, rows recorded before the metrics
    rewrite are excluded. That exclusion is about the *measurement* changing
    meaning, not the software: those rows' memory and CPU columns recorded a
    different quantity, so comparing across that boundary says nothing about
    either version.
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

    versions = _tool_versions(frame)
    version_changes = []

    for metric in metrics:
        if metric not in frame.columns:
            continue

        rows = frame[frame[metric].notna()].tail(2)
        if len(rows) != 2:
            continue

        previous_value, current_value = rows[metric].values
        if versions is None:
            previous_version = current_version = None
        else:
            previous_version, current_version = versions.loc[rows.index].values

        def label(value, version):
            if version is None:
                return "{0}".format(value)
            return "{0} (v{1})".format(value, version)

        print(
            "\t\t\tComparing {0}: previous={1}, current={2}".format(
                metric,
                label(previous_value, previous_version),
                label(current_value, current_version),
            )
        )

        if not previous_value:
            continue

        percent_change = 100 * (current_value - previous_value) / previous_value

        if previous_version != current_version:
            if abs(percent_change) > threshold:
                print(
                    "\t\t\t\tTool version differs between these two runs: "
                    "v{0} (earlier) -> v{1} (latest), {2} moved {3:+.1f}%. "
                    "Reported rather than failed, because this compares two "
                    "builds and the latest run is not always the newer "
                    "build. Worth investigating when the more expensive side "
                    "is the newer release.".format(
                        previous_version, current_version, metric, percent_change
                    )
                )
                version_changes.append(
                    {
                        "metric": metric,
                        "previous_value": previous_value,
                        "current_value": current_value,
                        "percent_change": percent_change,
                        "previous_version": previous_version,
                        "current_version": current_version,
                    }
                )
            continue

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
                "tool_version": current_version,
            }

    if version_changes:
        print(
            "\t\tNo regression: the two most recent runs are different tool "
            "versions, and the differences are reported above."
        )
        return {
            "Performance_stable": True,
            "version_comparison": version_changes,
        }

    print("\t\tNo significant changes found.")
    return None
