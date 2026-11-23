#!/usr/bin/env python3
#
# Visualization Vignettes
#
# node_telemetry.py -- what the node did while one vignette ran (schema 8)
#
# One background thread per vignette, started and stopped by run_tests.py
# around the vignette's process. Standard library only. Three sources, each
# optional; a source that is not there records nothing, never a zero:
#
#   power    Cray pm_counters (/sys/cray/pm_counters): node, CPU and memory
#            power and the CPU temperatures, read once a second, only when
#            the job owns the whole node (the counters cover the node). The
#            same files the Gray-Scott telemetry samples (node_sampler.sh).
#            Energy is not integrated from these: run_tests.py subtracts the
#            cumulative energy counters at start and end, which is exact.
#   gpu      nvidia-smi, run once for the vignette's whole duration with
#            -lms, so there is one process and no start-up cost per sample:
#            peak memory used, mean and peak utilisation and power, over the
#            GPUs this job can see.
#   memory   the exact peak resident set (VmHWM, the kernel's high-water
#            mark) of every process carrying this vignette's step name in
#            its environment (VV_SLURM_STEP_NAME, set by run_tests.py and
#            inherited by srun's tasks, VisIt's engine included), read ten
#            times a second. VmHWM never goes down, so a sample anywhere in
#            a process's life after its peak sees the peak; only a process
#            that peaks in its last 0.1 s is under-read. Slurm samples task
#            memory at most once a second, so a 2 s step gets one sample
#            (#140). Two figures come of it, both per srun step (VisIt
#            starts its engines one after another, each in its own step, so
#            steps are never added to each other):
#              step PSS peak  the largest sum of the step's processes' PSS
#                             (smaps_rollup) at one poll: processes alive at
#                             the same moment, shared pages counted once.
#                             The memory figure of a single-node srun run.
#                             Reading smaps_rollup costs about 12 ms per GB
#                             resident, so this poll paces itself to use at
#                             most PSS_BUDGET of one core (0.1 s for small
#                             runs, a few seconds for ex06's 45 GB).
#              step HWM sum   the sum of the step's processes' VmHWM: each
#                             process's exact peak, but at different times
#                             and with shared pages counted per process, so
#                             an upper bound. Cheap, read every 0.1 s.
#            The whole tool tree (the harness's own processes too: VisIt's
#            CLI and viewer, the srun client) is recorded as a separate
#            PSS peak. Only processes on this node: every suite run is
#            single-node.
#
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time

PM_COUNTERS_DIR = "/sys/cray/pm_counters"
PM_POWER_FILES = {
    "node_w": "power",
    "cpu_w": "cpu_power",
    "memory_w": "memory_power",
}
PM_TEMP_FILES = ("cpu0_temp", "cpu1_temp")
NVIDIA_FIELDS = "index,memory.used,utilization.gpu,power.draw"


def _number(text):
    """The first number in a sysfs or nvidia-smi value, or None."""
    match = re.match(r"\s*(-?\d+(?:\.\d+)?)", text or "")
    return float(match.group(1)) if match else None


def read_pm_power(directory=PM_COUNTERS_DIR):
    """{node_w, cpu_w, memory_w, temp_c} from one read of pm_counters, or None."""
    if not os.path.isdir(directory):
        return None
    reading = {}
    for key, name in PM_POWER_FILES.items():
        try:
            with open(os.path.join(directory, name), "r") as handle:
                value = _number(handle.read())
        except OSError:
            value = None
        if value is not None:
            reading[key] = value
    temps = []
    for name in PM_TEMP_FILES:
        try:
            with open(os.path.join(directory, name), "r") as handle:
                value = _number(handle.read())
        except OSError:
            value = None
        if value is not None:
            temps.append(value)
    if temps:
        reading["temp_c"] = max(temps)
    return reading or None


def parse_nvidia_line(line):
    """(index, memory MiB, utilisation %, power W) from one csv line, or None.

    nvidia-smi prints "[N/A]" or "[Not Supported]" for a field a GPU lacks;
    that field is None and the rest of the line still counts.
    """
    parts = [part.strip() for part in line.split(",")]
    if len(parts) != 4 or not parts[0].isdigit():
        return None
    return (int(parts[0]),) + tuple(_number(part) for part in parts[1:])


def step_hwm_kb(step_name, proc="/proc", uid=None, cache=None, groups=None):
    """{pid: VmHWM kB} for this user's processes whose environment names the step.

    `cache` maps pid -> False (not ours) or its Slurm step id ("" outside
    Slurm), so a process's owner and environment are read once, when its
    pid first appears; after that a matching process costs one read of its
    status and any other process nothing. `groups`, when given, is filled
    with pid -> step id for the processes found. A pid reused between two
    scans 0.1 s apart is not worth guarding against.
    """
    uid = os.getuid() if uid is None else uid
    cache = {} if cache is None else cache
    marker = ("VV_SLURM_STEP_NAME=" + step_name).encode("utf-8")
    found = {}
    try:
        pids = {int(name) for name in os.listdir(proc) if name.isdigit()}
    except OSError:
        return found
    for pid in list(cache):
        if pid not in pids:
            del cache[pid]
    for pid in pids:
        base = os.path.join(proc, str(pid))
        matches = cache.get(pid)
        if matches is None:
            try:
                if os.stat(base).st_uid != uid:
                    matches = False
                else:
                    with open(os.path.join(base, "environ"), "rb") as handle:
                        entries = handle.read().split(b"\0")
                    matches = marker in entries and _step_id(entries)
            except OSError:
                continue
            cache[pid] = matches
        if matches is False:
            continue
        try:
            with open(os.path.join(base, "status"), "r") as handle:
                for line in handle:
                    if line.startswith("VmHWM:"):
                        found[pid] = int(line.split()[1])
                        if groups is not None:
                            groups[pid] = matches
                        break
        except (OSError, IndexError, ValueError):
            continue
    return found


def _step_id(entries):
    """The SLURM_STEP_ID in a process's environment entries, "" without one."""
    for entry in entries:
        if entry.startswith(b"SLURM_STEP_ID="):
            return entry[len(b"SLURM_STEP_ID=") :].decode("ascii", "replace")
    return ""


def step_sums(kb_by_pid, groups, own_step):
    """{step: summed kB} over the srun steps, the harness's own step left out.

    own_step is the harness's SLURM_STEP_ID ("" outside Slurm): its
    processes are the tool's own tree, not ranks a step launched.
    """
    sums = {}
    for pid, kb in kb_by_pid.items():
        group = groups.get(pid, own_step)
        if group != own_step:
            sums[group] = sums.get(group, 0) + kb
    return sums


def pss_kb(pid, proc="/proc"):
    """The process's proportional set size in kB (smaps_rollup), or None."""
    try:
        with open(os.path.join(proc, str(pid), "smaps_rollup"), "r") as handle:
            for line in handle:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except (OSError, IndexError, ValueError):
        return None
    return None


def _read_first_line(path):
    try:
        with open(path, "r") as handle:
            return handle.readline().strip()
    except (OSError, UnicodeDecodeError):
        return None


def host_platform(root="/"):
    """The node settings a maintenance can change without changing the OS name.

    The same settings the Gray-Scott telemetry records (node_platform.sh):
    CPU frequency driver, turbo boost, maximum frequency, SMT, NUMA nodes,
    transparent and 2 MB huge pages, CPU microcode, and the kernel command
    line. The command line can name hosts and paths, so only a short digest
    of it is kept: enough to see that it changed. `root` is for tests.
    """

    def path(*parts):
        return os.path.join(root, *parts)

    cpufreq = path("sys", "devices", "system", "cpu", "cpu0", "cpufreq")
    out = {}
    value = _read_first_line(os.path.join(cpufreq, "scaling_driver"))
    if value:
        out["cpu_driver"] = value
    value = _read_first_line(os.path.join(cpufreq, "cpuinfo_max_freq"))
    if value and value.isdigit():
        out["cpu_max_mhz"] = int(value) // 1000
    # AMD and acpi-cpufreq expose a global boost switch; intel_pstate an
    # inverted one.
    value = _read_first_line(
        path("sys", "devices", "system", "cpu", "cpufreq", "boost")
    )
    if value in ("0", "1"):
        out["cpu_boost"] = value == "1"
    else:
        value = _read_first_line(
            path("sys", "devices", "system", "cpu", "intel_pstate", "no_turbo")
        )
        if value in ("0", "1"):
            out["cpu_boost"] = value == "0"
    value = _read_first_line(path("sys", "devices", "system", "cpu", "smt", "active"))
    if value in ("0", "1"):
        out["smt_active"] = value == "1"
    try:
        nodes = [
            n
            for n in os.listdir(path("sys", "devices", "system", "node"))
            if re.match(r"node\d+$", n)
        ]
        if nodes:
            out["numa_nodes"] = len(nodes)
    except OSError:
        pass
    value = _read_first_line(
        path("sys", "kernel", "mm", "transparent_hugepage", "enabled")
    )
    match = re.search(r"\[(\w+)\]", value or "")
    if match:
        out["thp"] = match.group(1)
    value = _read_first_line(
        path("sys", "kernel", "mm", "hugepages", "hugepages-2048kB", "nr_hugepages")
    )
    if value and value.isdigit():
        out["hugepages_2m"] = int(value)
    try:
        with open(path("proc", "cpuinfo"), "r") as handle:
            for line in handle:
                if line.startswith("microcode"):
                    out["cpu_microcode"] = line.split(":", 1)[1].strip()
                    break
    except (OSError, UnicodeDecodeError):
        pass
    value = _read_first_line(path("proc", "cmdline"))
    if value:
        out["kernel_cmdline_digest"] = hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()[:12]
    return out


class NodeTelemetry(object):
    """Sample power, GPU and step memory while one vignette runs.

    start() and stop() bracket the vignette; figures() is what to record.
    Every source is optional and best effort: an error stops that source
    and leaves its figures out.
    """

    MEMORY_PERIOD_S = 0.1
    # The PSS poll may use at most this share of one core; it waits longer
    # between polls of large processes, whose smaps_rollup costs more.
    PSS_BUDGET = 0.10
    POWER_PERIOD_S = 1.0

    def __init__(self, step_name=None, power=False, gpu=True, pm_dir=PM_COUNTERS_DIR):
        self.step_name = step_name
        self.power = power and os.path.isdir(pm_dir)
        self.pm_dir = pm_dir
        self.gpu = gpu and shutil.which("nvidia-smi") is not None
        self._stop = threading.Event()
        self._threads = []
        self._smi = None
        self._power = []
        self._gpu = {}
        # (pid, step) -> peak kB: a pid the kernel reuses in another step is
        # another process.
        self._hwm = {}
        self._memory_samples = 0
        self._memory_cost_s = 0.0
        self._own_step = os.environ.get("SLURM_STEP_ID", "")
        self._step_pss_peak = {}  # step -> largest summed PSS kB at one poll
        self._tree_pss_peak = 0  # every process, the tool's own tree too
        self._pss_samples = 0
        self._pss_cost_s = 0.0

    # -- sources -----------------------------------------------------------
    def _memory_loop(self):
        cache = {}
        next_pss = 0.0
        while not self._stop.is_set():
            began = time.time()
            groups = {}
            found = step_hwm_kb(self.step_name, cache=cache, groups=groups)
            for pid, kb in found.items():
                key = (pid, groups.get(pid, ""))
                if kb > self._hwm.get(key, 0):
                    self._hwm[key] = kb
            if found and began >= next_pss:
                pss_began = time.time()
                read = {pid: pss_kb(pid) for pid in found}
                # A step counts at this poll only when every one of its
                # processes was read: a partial sum is not that step's memory.
                partial = {
                    groups.get(pid, self._own_step)
                    for pid, kb in read.items()
                    if kb is None
                }
                pss = {pid: kb for pid, kb in read.items() if kb is not None}
                for step, kb in step_sums(pss, groups, self._own_step).items():
                    if step not in partial and kb > self._step_pss_peak.get(step, 0):
                        self._step_pss_peak[step] = kb
                if not partial:
                    self._tree_pss_peak = max(self._tree_pss_peak, sum(pss.values()))
                cost = time.time() - pss_began
                self._pss_samples += 1
                self._pss_cost_s += cost
                next_pss = began + max(self.MEMORY_PERIOD_S, cost / self.PSS_BUDGET)
            spent = time.time() - began
            self._memory_samples += 1
            self._memory_cost_s += spent
            self._stop.wait(max(0.0, self.MEMORY_PERIOD_S - spent))

    def _power_loop(self):
        while not self._stop.is_set():
            reading = read_pm_power(self.pm_dir)
            if reading:
                self._power.append(reading)
            self._stop.wait(self.POWER_PERIOD_S)

    def _start_smi(self):
        """Start nvidia-smi here, before any thread, so stop() always sees it.

        Started inside the reading thread, it could begin after a quick
        vignette's stop() had already looked for it, and poll forever.
        """
        try:
            self._smi = subprocess.Popen(
                [
                    shutil.which("nvidia-smi"),
                    "--query-gpu=" + NVIDIA_FIELDS,
                    "--format=csv,noheader,nounits",
                    "-lms",
                    "1000",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                universal_newlines=True,
            )
        except (OSError, ValueError):
            self._smi = None
        return self._smi is not None

    def _gpu_loop(self):
        try:
            for line in self._smi.stdout:
                sample = parse_nvidia_line(line)
                if sample is not None:
                    self._gpu.setdefault(sample[0], []).append(sample[1:])
            # Reap it as soon as it ends (at once on a node with no GPU), so
            # no zombie waits for stop().
            self._smi.wait()
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

    # -- control -----------------------------------------------------------
    def start(self):
        loops = []
        if self.step_name:
            loops.append(self._memory_loop)
        if self.power:
            loops.append(self._power_loop)
        if self.gpu and self._start_smi():
            loops.append(self._gpu_loop)
        for loop in loops:
            thread = threading.Thread(target=loop)
            thread.daemon = True
            thread.start()
            self._threads.append(thread)
        return self

    def stop(self):
        self._stop.set()
        if self._smi is not None:
            try:
                self._smi.terminate()
                self._smi.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                pass
        for thread in self._threads:
            thread.join(timeout=5.0)
        return self

    # -- results -----------------------------------------------------------
    def figures(self):
        """The run's telemetry as payload fields; absent sources are left out."""
        out = {}
        if self.step_name and self._memory_samples:
            out["step_hwm_samples"] = self._memory_samples
            out["step_hwm_mean_sample_s"] = round(
                self._memory_cost_s / self._memory_samples, 5
            )
            peaks = dict(self._hwm)
            if peaks:
                hwm = {i: kb for i, kb in enumerate(peaks.values())}
                groups = {i: key[1] for i, key in enumerate(peaks)}
                sums = step_sums(hwm, groups, self._own_step)
                out["step_hwm_processes"] = len(peaks)
                out["step_hwm_steps"] = len(sums)
                if sums:
                    # Upper bound: per-process peaks, each at its own time.
                    out["step_hwm_bytes"] = max(sums.values()) * 1024
            step_pss = dict(self._step_pss_peak)
            if step_pss:
                out["step_pss_peak_bytes"] = max(step_pss.values()) * 1024
                # How many of the steps seen (step_hwm_steps) have a complete
                # PSS sample; the figure is the run's memory only when all do.
                out["step_pss_steps"] = len(step_pss)
            if self._tree_pss_peak:
                out["tool_tree_pss_peak_bytes"] = self._tree_pss_peak * 1024
            if self._pss_samples:
                out["step_pss_samples"] = self._pss_samples
                out["step_pss_mean_sample_s"] = round(
                    self._pss_cost_s / self._pss_samples, 5
                )
        if self._power:
            for key in ("node_w", "cpu_w", "memory_w"):
                values = [r[key] for r in self._power if key in r]
                if values:
                    out["power_mean_" + key] = round(sum(values) / len(values), 1)
                    out["power_peak_" + key] = max(values)
            temps = [r["temp_c"] for r in self._power if "temp_c" in r]
            if temps:
                out["temp_peak_cpu_c"] = max(temps)
            out["power_samples"] = len(self._power)
        if self._gpu:
            gpus = []
            # Copies: a thread that outlived stop()'s join may still append.
            for index, samples in sorted(dict(self._gpu).items()):
                samples = list(samples)
                one = {"index": index, "samples": len(samples)}
                for position, peak_key, mean_key in (
                    (0, "memory_peak_mib", None),
                    (1, "util_peak_pct", "util_mean_pct"),
                    (2, "power_peak_w", "power_mean_w"),
                ):
                    values = [s[position] for s in samples if s[position] is not None]
                    if values:
                        one[peak_key] = max(values)
                        if mean_key:
                            one[mean_key] = round(sum(values) / len(values), 1)
                gpus.append(one)
            out["gpu_telemetry"] = gpus
        return out


if __name__ == "__main__":
    # A quick look on a node: sample for a few seconds and print.
    telemetry = NodeTelemetry(
        step_name=os.environ.get("VV_SLURM_STEP_NAME"), power=True
    ).start()
    time.sleep(float(os.environ.get("SECONDS_TO_SAMPLE", "3")))
    print(json.dumps(telemetry.stop().figures(), indent=1))
