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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drift  # noqa: E402

try:
    import psutil  # pyright: ignore[reportMissingModuleSource]
except ImportError:  # pragma: no cover - psutil is in the documented venv
    psutil = None


# Bumped whenever the meaning of a recorded field changes, so plots and
# regression checks can refuse to compare across a schema boundary.
#
# 6 adds fields (verdicts, build, baseline, I/O, energy, host context) and
# changes the meaning of none, so its CPU and memory still compare with 5's:
# MIN_COMPARABLE_SCHEMA is the oldest schema whose CPU and memory figures
# mean what the current one's do. Bump that too when a figure changes
# meaning; leave it when a schema only adds fields.
#
# 7 adds fields again: `repeat` (this record is one of N runs of the
# vignette in one invocation, --repeat), `load_1m_at_end`, and the host's OS
# release, CPU governor and GPUs with their driver in machine_info. A figure
# means what it did at 6.
#
# 8 adds fields once more (#140): the node's platform settings in
# machine_info (boost, SMT, THP, huge pages, NUMA, microcode, a digest of
# the kernel command line), and what the node did during the vignette
# (node_telemetry.py): node, CPU and memory power and the peak CPU
# temperature from pm_counters, per-GPU memory, utilisation and power from
# nvidia-smi, and the memory of the vignette's processes read from /proc.
# Figures mean what they did at 7, with one addition: a run whose ranks srun
# launched on this one node takes its memory from the ranks' peak summed PSS
# (STEP_PSS_SCOPE), the processes Slurm's step accounting covers, sampled up
# to ten times a second where Slurm samples once at best and missed 22 to 57%
# of a short step's peak on Shaheen (#140). Slurm's figure stays beside it.
# The scope keeps the gate and drift from comparing the two kinds of figure.
METRICS_SCHEMA = 8
MIN_COMPARABLE_SCHEMA = 5


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

# The largest summed PSS of the ranks of one srun step at one poll
# (node_telemetry.py): the processes Slurm's step accounting covers, alive at
# the same moment, shared pages counted once, polled up to ten times a
# second. Only when the job has one node, so every rank is on the node the
# poller reads. VisIt's CLI and viewer are not in it; they are in
# tool_tree_pss_peak_mb.
STEP_PSS_SCOPE = "srun-step-pss-single-node"

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


# Energy from Slurm's accounting of the run's steps (schema 6).
ENERGY_SLURM_SCOPE = "slurm-steps-whole-nodes"
# Energy from /sys/cray/pm_counters on the node the harness ran on.
ENERGY_PM_SCOPE = "node-pm-counters"
# Storage I/O summed over the sampled process tree, from /proc/<pid>/io.
IO_TREE_SCOPE = "child-tree-proc-io"


def _local_tree_detail(run_result):
    """Schema-6 detail from the sampled tree, for runs whose ranks it holds.

    Not used for srun runs: there the local tree is only the launcher, and
    its I/O and thread counts would read as the vignette's.
    """
    detail = {}
    if run_result.get("io_read_bytes") is not None:
        detail["io_scope"] = IO_TREE_SCOPE
        for key in ("io_read", "io_write", "io_rchar", "io_wchar"):
            value = run_result.get(key + "_bytes")
            if value is not None:
                detail[key + "_mb"] = value / MB
    for key in (
        "peak_processes",
        "peak_threads",
    ):
        if run_result.get(key) is not None:
            detail[key] = run_result[key]
    # Whole-node energy, recorded by run_tests.py only when the job owned
    # the node; on one node, which is where these runs' ranks are.
    energy = run_result.get("pm_energy")
    if energy and energy.get("node_joules") is not None:
        detail["energy_joules"] = float(energy["node_joules"])
        # A split pm_energy rejected (None) stays out rather than reading 0.
        for key, field in (
            ("cpu_joules", "energy_cpu_joules"),
            ("memory_joules", "energy_memory_joules"),
        ):
            if energy.get(key) is not None:
                detail[field] = float(energy[key])
        detail["energy_scope"] = ENERGY_PM_SCOPE
    return detail


TELEMETRY_KEYS = (
    "power_mean_node_w",
    "power_peak_node_w",
    "power_mean_cpu_w",
    "power_peak_cpu_w",
    "power_mean_memory_w",
    "power_peak_memory_w",
    "temp_peak_cpu_c",
    "power_samples",
    "gpu_telemetry",
    "step_hwm_processes",
    "step_hwm_steps",
    "step_hwm_samples",
    "step_hwm_mean_sample_s",
    "step_pss_samples",
    "step_pss_steps",
    "step_pss_mean_sample_s",
    "srun_steps_expected",
)


def node_telemetry_fields(run_result):
    """Schema-8 detail from node_telemetry.py, as recorded fields.

    Context and detail, not compared by the gate. For a single-node srun
    run step_pss_peak_mb is also the run's memory figure (prefer_exact_peak).
    Not memory_*: that prefix would tie these to the run's memory scope.
    """
    out = {key: run_result[key] for key in TELEMETRY_KEYS if key in run_result}
    for key, field in (
        # The ranks' peak summed PSS at one poll: the memory figure.
        ("step_pss_peak_bytes", "step_pss_peak_mb"),
        # The ranks' per-process VmHWM summed: an upper bound.
        ("step_hwm_bytes", "step_hwm_mb"),
        # Every process of the run, VisIt's CLI and viewer included.
        ("tool_tree_pss_peak_bytes", "tool_tree_pss_peak_mb"),
    ):
        if run_result.get(key):
            out[field] = run_result[key] / MB
    gpus = run_result.get("gpu_telemetry") or []
    for key, field in (
        ("memory_peak_mib", "gpu_memory_peak_mib"),
        ("power_peak_w", "gpu_power_peak_w"),
    ):
        values = [g[key] for g in gpus if g.get(key) is not None]
        if values:
            # The busiest GPU: a job can see idle ones too.
            out[field] = max(values)
    # GPU energy: every GPU the job can see, idle ones included, since an
    # idle GPU the job holds still draws power for it. Its own field, not
    # energy_joules: that is the node's (or Slurm's) figure, and GPU energy
    # is measured on every GPU machine, where the node's is not.
    # Only when every GPU has a figure: a GPU without power readings would
    # drop out of the sum and the total would look complete.
    energies = [g.get("energy_j") for g in gpus]
    if energies and None not in energies:
        out["gpu_energy_joules"] = round(sum(energies), 1)
    # The CPU and memory split of the node's energy, for srun runs too, whose
    # total comes from Slurm's step accounting rather than pm_counters.
    energy = run_result.get("pm_energy")
    if run_result.get("ranks_outside_tree") and energy:
        for key, name in (
            ("node_joules", "energy_pm_node_joules"),
            ("cpu_joules", "energy_cpu_joules"),
            ("memory_joules", "energy_memory_joules"),
        ):
            if energy.get(key) is not None:
                out[name] = float(energy[key])
    return out


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
        # Slurm's step energy covers whole nodes, so it is this run's only
        # when the job owned every node it ran on, and the run's total only
        # when every step reported one.
        energies = [step.get("energy_joules") for step in steps]
        if run_result.get("job_owns_its_nodes") and all(energies):
            figures["energy_joules"] = float(sum(energies))
            figures["energy_scope"] = ENERGY_SLURM_SCOPE
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

    figures.update(_local_tree_detail(run_result))

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


def prefer_exact_peak(figures, run_result):
    """Take a single-node srun run's memory from its ranks' PSS (STEP_PSS_SCOPE).

    Every rank ran on this node, so node_telemetry.py's poller saw each one.
    Slurm's figure stays beside it: slurm_memory_mb with its scope (the
    largest step plus the harness's own tree, as recorded before), and
    slurm_step_memory_mb, the ranks alone, the same processes the new figure
    covers. Neither is there when a step was never sampled. Other runs are
    left as they are: a local tree already has PSS, and a multi-node job has
    ranks the poller cannot see.
    """
    if not (
        run_result.get("ranks_outside_tree")
        and run_result.get("job_nodes") == 1
        and run_result.get("step_pss_peak_bytes")
        # Every srun step the poller saw has a complete PSS sample: a VisIt
        # engine that ended between PSS polls would leave the figure with
        # only the steps that were sampled.
        # How many steps the run started must be known: a step that started
        # and ended between two scans is in neither count below.
        and (run_result.get("srun_steps_expected") or 0) > 0
        and run_result.get("step_pss_steps", 0)
        >= max(
            run_result.get("step_hwm_steps") or 1,
            run_result["srun_steps_expected"],
        )
    ):
        return
    if figures.get("memory_mb") is not None:
        figures["slurm_memory_mb"] = figures["memory_mb"]
        figures["slurm_memory_scope"] = figures["memory_scope"]
    steps = [s.get("total_mem_bytes") or 0 for s in run_result.get("slurm_steps") or []]
    if steps and all(steps):
        figures["slurm_step_memory_mb"] = max(steps) / MB
    figures["memory_mb"] = run_result["step_pss_peak_bytes"] / MB
    figures["memory_scope"] = STEP_PSS_SCOPE


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
    prefer_exact_peak(figures, run_result)
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
        # Context for reading the numbers, not measurements of the run.
        for key in (
            "load_1m_at_start",
            "load_1m_at_end",
            "opengl_window",
            "job_owns_its_nodes",
        ):
            if run_result.get(key) is not None:
                metrics[key] = run_result[key]
        metrics.update(node_telemetry_fields(run_result))

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
# From drift.scope_of, the one metric-to-scope map, so the gate and the
# repeat fold cannot disagree.
MEASUREMENT_SCOPE = {
    metric: drift.scope_of(metric)
    for metric in ("cpu_usage_percent", "memory_usage_mb")
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
        current = frame[frame["metrics_schema"] >= MIN_COMPARABLE_SCHEMA]
        if len(current) >= 2:
            frame = current
        else:
            print(
                "\t\tOnly {0} run(s) at metrics schema {1} or later; skipping "
                "comparison until a second comparable run exists.".format(
                    len(current), MIN_COMPARABLE_SCHEMA
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
