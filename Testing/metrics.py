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
import os
import resource
import sys

try:
    import psutil  # pyright: ignore[reportMissingModuleSource]
except ImportError:  # pragma: no cover - psutil is in the documented venv
    psutil = None


# Bumped whenever the meaning of a recorded field changes, so plots and
# regression checks can refuse to compare across a schema boundary.
METRICS_SCHEMA = 5


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


# Recorded as the CPU and memory scope when the ranks were launched by srun
# and so could not be measured from here. See gather_metrics().
SRUN_SCOPE = "unavailable-ranks-launched-by-srun"

# CPU and memory taken from Slurm's accounting of the run's job steps, plus
# the process tree the harness launched itself (the srun client, or VisIt's
# CLI and viewer). LOCAL_VALIDATION 4b.15.
SLURM_SCOPE = "slurm-steps-plus-local-tree"
# The same, when the local tree could not be sampled.
SLURM_STEPS_ONLY_SCOPE = "slurm-steps-only"
# The same, with the local tree's memory as RSS because PSS was unreadable.
SLURM_LOCAL_RSS_SCOPE = "slurm-steps-plus-local-rss"

# Summed PSS over the process tree. Replaces summed RSS, which counted shared
# libraries once per rank (LOCAL_VALIDATION 4b.15).
PSS_SCOPE = "child-tree-pss"

MB = 1024.0 * 1024.0


def _is_visit(run_result):
    command = run_result.get("command") or [""]
    return os.path.basename(str(command[0])).startswith("visit")


def _sum_field(items, key):
    """Sum of `key` over every item, or None if any item lacks it: a total
    with a step missing would read as a complete, smaller number."""
    values = [item.get(key) for item in items]
    if not values or any(value is None for value in values):
        return None
    return sum(values)


def _resource_figures(run_result, after, before, rusage_cpu):
    """CPU seconds, peak memory and their scopes for one run.

    In order of preference:

    * ranks under srun: Slurm's accounting of the steps, plus the local tree;
    * everything else: the sampled process tree, PSS for memory;
    * no tree sample (psutil missing): RUSAGE_CHILDREN, except for VisIt,
      whose engine it does not see (5 CPU seconds of a 225 s run).
    """
    figures = {}
    if run_result.get("ranks_outside_tree"):
        steps = run_result.get("slurm_steps") or []
        local = run_result.get("local_tree") or {}
        if not steps:
            figures.update(
                cpu_seconds=None,
                memory_mb=None,
                cpu_scope=SRUN_SCOPE,
                memory_scope=SRUN_SCOPE,
            )
            return figures
        # Without a local sample (no psutil) the figure covers less than a
        # sampled run does, VisIt's CLI and viewer in particular, so it gets
        # its own scope rather than a zero for the missing part.
        step_cpu = _sum_field(steps, "cpu_seconds")
        local_cpu = local.get("tree_cpu_seconds")
        cpu_scope = SLURM_SCOPE if local_cpu is not None else SLURM_STEPS_ONLY_SCOPE
        figures["cpu_seconds"] = (
            None if step_cpu is None else step_cpu + (local_cpu or 0.0)
        )
        figures["cpu_scope"] = cpu_scope if step_cpu is not None else SRUN_SCOPE
        for key, local_key in (
            ("cpu_user_seconds", "tree_cpu_user_seconds"),
            ("cpu_system_seconds", "tree_cpu_system_seconds"),
        ):
            part = _sum_field(steps, key)
            if part is not None:
                figures[key] = part + (local.get(local_key) or 0.0)
        # Steps run one after another, so the run's peak is the largest
        # step's, each step's being the sum of its tasks' peaks. A step that
        # reports 0 was never sampled (Shaheen's 600 s default), and its
        # peak could be the largest, so the run's memory is known only when
        # every step reported one.
        step_mems = [step.get("total_mem_bytes") or 0 for step in steps]
        # The local part is PSS when it could be read. RSS stands in
        # otherwise, and counts shared pages more than once, so the total
        # gets its own scope.
        local_mem = local.get("peak_pss_bytes")
        memory_scope = SLURM_SCOPE
        if local_mem is None:
            local_mem = local.get("peak_rss_bytes")
            memory_scope = (
                SLURM_LOCAL_RSS_SCOPE
                if local_mem is not None
                else SLURM_STEPS_ONLY_SCOPE
            )
        if all(step_mems):
            step_mem = max(step_mems)
            figures["memory_mb"] = (step_mem + (local_mem or 0)) / MB
            figures["memory_scope"] = memory_scope
        else:
            figures["memory_mb"] = None
            figures["memory_scope"] = SRUN_SCOPE
        max_tasks = [step.get("max_task_mem_bytes") or 0 for step in steps]
        if all(max_tasks):
            figures["memory_max_task_mb"] = max(max_tasks) / MB
        for key in ("disk_read_bytes", "disk_write_bytes"):
            total = _sum_field(steps, key)
            if total is not None:
                figures[key.replace("_bytes", "_mb")] = total / MB
        figures["slurm_steps"] = [step.get("step") for step in steps]
        return figures

    if run_result.get("peak_pss_mb"):
        figures["memory_mb"] = float(run_result["peak_pss_mb"])
        figures["memory_scope"] = PSS_SCOPE
        if run_result.get("peak_rss_mb"):
            figures["memory_rss_mb"] = float(run_result["peak_rss_mb"])
    elif run_result.get("peak_rss_mb"):
        figures["memory_mb"] = float(run_result["peak_rss_mb"])
        figures["memory_scope"] = "child-tree-sampled"
    elif _is_visit(run_result):
        # RUSAGE_CHILDREN does not see VisIt's engine, for memory as for CPU.
        figures["memory_mb"] = None
        figures["memory_scope"] = "unavailable-no-tree-sample"
    elif before and after.ru_maxrss <= before.get("maxrss", 0):
        figures["memory_mb"] = None
        figures["memory_scope"] = "unavailable-highwater-from-earlier-test"
    else:
        figures["memory_mb"] = _maxrss_to_mb(after.ru_maxrss)
        figures["memory_scope"] = "children-highwater"

    if run_result.get("tree_cpu_seconds") is not None:
        figures["cpu_seconds"] = float(run_result["tree_cpu_seconds"])
        figures["cpu_scope"] = "child-tree-sampled"
        for key in ("tree_cpu_user_seconds", "tree_cpu_system_seconds"):
            if run_result.get(key) is not None:
                figures[key.replace("tree_", "")] = float(run_result[key])
    elif _is_visit(run_result):
        figures["cpu_seconds"] = None
        figures["cpu_scope"] = "unavailable-no-tree-sample"
    else:
        figures["cpu_seconds"] = rusage_cpu
        figures["cpu_scope"] = "children-rusage"
    return figures


def gather_metrics(test_name, start_time, end_time, run_result=None, before=None):
    """Collect performance metrics for one vignette run.

    `run_result` is the payload run_tests.py wrote (return code, duration,
    timeout flag). `before` is a child_rusage_snapshot() taken immediately
    before the launch. Both are optional so that older call sites keep
    working, but without them the memory and CPU figures fall back to
    whole-process totals and are marked as such.
    """
    elapsed = float(end_time) - float(start_time)
    # run_tests.py may have waited for Slurm's accounting after the vignette
    # ended (see slurm_step_usage); that is not the vignette's time.
    if run_result and run_result.get("accounting_wait_s"):
        elapsed = max(0.0, elapsed - float(run_result["accounting_wait_s"]))
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
    run_result = run_result or {}
    figures = _resource_figures(run_result, after, before, child_utime + child_stime)
    cpu_seconds = figures.pop("cpu_seconds")
    child_maxrss_mb = figures.pop("memory_mb")

    metrics = {
        "test_name": test_name,
        "metrics_schema": METRICS_SCHEMA,
        "execution_time": elapsed,
        "memory_measurement_scope": figures.pop("memory_scope"),
        "cpu_measurement_scope": figures.pop("cpu_scope"),
    }
    if cpu_seconds is not None:
        metrics["cpu_seconds"] = cpu_seconds
        metrics["cpu_usage_percent"] = (
            (100.0 * cpu_seconds / elapsed) if elapsed > 0 else 0.0
        )
    # The rest is detail: the user/system split, the per-rank peak, disk
    # traffic and the steps themselves. None of it is compared by the gate.
    metrics.update(figures)

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


# The field that says how each schema-sensitive metric was measured. Rows
# with different scopes hold different quantities, even at the same schema.
MEASUREMENT_SCOPE = {
    "cpu_usage_percent": "cpu_measurement_scope",
    "memory_usage_mb": "memory_measurement_scope",
}


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

        rows = frame
        # CPU and memory each record which measurement produced them, and the
        # scopes share a schema: whole-tree sampling put ex00 at 317% CPU
        # where RUSAGE_CHILDREN said 28%. Compare only runs measured the same
        # way as the latest run. If the latest run could not measure it at
        # all, there is nothing current to compare.
        scope = MEASUREMENT_SCOPE.get(metric)
        if scope in rows.columns:
            latest_scope = rows[scope].iloc[-1]
            if isinstance(latest_scope, str):
                rows = rows[rows[scope] == latest_scope]
        rows = rows[rows[metric].notna()].tail(2)
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
