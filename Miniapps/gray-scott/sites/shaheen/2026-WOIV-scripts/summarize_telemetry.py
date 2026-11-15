"""Summarise a run's telemetry (--telemetry) into one JSON file.

Usage: summarize_telemetry.py <telemetry_dir> <out.json>

Reads the per-node CSV files node_sampler.sh wrote (<telemetry_dir>/nodes)
and the Slurm step accounting the reduction job saved (<telemetry_dir>/
sacct.txt), and writes per-run totals:

* energy: node, CPU and memory joules over the sampled interval, from the
  differences of Cray pm_counters' cumulative counters per node, summed over
  nodes; mean and peak node power.
* CPU: per-node mean utilisation from /proc/stat differences.
* NIC: bytes sent and received, and the NACK and retry counter increases.
* Slurm: each numbered step's elapsed time, CPU seconds, peak task memory
  and ConsumedEnergyRaw, as sacct reported them.

Counters that go backwards (a reset) are treated as missing for that node.
Only the standard library is used, so it runs in any Python 3.
"""

import csv
import glob
import json
import os
import sys

ENERGY_KEYS = ("pm_energy", "pm_cpu_energy", "pm_memory_energy")
CPU_KEYS = (
    "cpu_user",
    "cpu_nice",
    "cpu_system",
    "cpu_idle",
    "cpu_iowait",
    "cpu_irq",
    "cpu_softirq",
)
NIC_PREFIX = "nic_"


def _num(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _increase(rows, key):
    """Last minus first value of a cumulative counter, or None."""
    values = [_num(r.get(key)) for r in rows]
    values = [v for v in values if v is not None]
    if len(values) < 2 or values[-1] < values[0]:
        return None
    return values[-1] - values[0]


def summarize_node(path):
    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    node = {"node": os.path.splitext(os.path.basename(path))[0], "samples": len(rows)}
    if len(rows) < 2:
        return node
    t0, t1 = _num(rows[0]["time_s"]), _num(rows[-1]["time_s"])
    node["interval_s"] = (
        round(t1 - t0, 3) if t0 is not None and t1 is not None else None
    )
    for key in ENERGY_KEYS:
        node[key.replace("pm_", "") + "_j"] = _increase(rows, key)
    powers = [_num(r.get("pm_power")) for r in rows]
    powers = [p for p in powers if p is not None]
    if powers:
        node["power_mean_w"] = round(sum(powers) / len(powers), 1)
        node["power_max_w"] = max(powers)
    ticks = {k: _increase(rows, k) for k in CPU_KEYS}
    if all(v is not None for v in ticks.values()):
        total = sum(ticks.values())
        busy = total - ticks["cpu_idle"] - ticks["cpu_iowait"]
        node["cpu_busy_fraction"] = round(busy / total, 4) if total else None
    for key in rows[0]:
        if key.startswith(NIC_PREFIX):
            node[key] = _increase(rows, key)
    return node


def read_sacct(path):
    """Numbered steps from `sacct -P` output with a header line."""
    if not os.path.exists(path):
        return []
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        steps = []
        for row in reader:
            step = row.get("JobIDRaw", "")
            if "." not in step or not step.split(".", 1)[1].isdigit():
                continue
            steps.append(
                {
                    "step": step,
                    "name": row.get("JobName"),
                    "state": row.get("State"),
                    "nodes": row.get("NNodes"),
                    "tasks": row.get("NTasks"),
                    "elapsed": row.get("Elapsed"),
                    "total_cpu": row.get("TotalCPU"),
                    "max_rss": row.get("MaxRSS"),
                    "consumed_energy_j": _num(row.get("ConsumedEnergyRaw")),
                    "ave_cpu_freq": row.get("AveCPUFreq"),
                }
            )
        return steps


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[2])
        return 2
    tel_dir, out_path = argv[1], argv[2]
    nodes = [
        summarize_node(p)
        for p in sorted(glob.glob(os.path.join(tel_dir, "nodes", "*.csv")))
    ]
    totals = {"nodes_sampled": len(nodes)}
    for key in ("energy_j", "cpu_energy_j", "memory_energy_j"):
        values = [n.get(key) for n in nodes]
        totals[key] = (
            sum(values) if values and all(v is not None for v in values) else None
        )
    powers = [n["power_mean_w"] for n in nodes if "power_mean_w" in n]
    totals["node_power_mean_w"] = (
        round(sum(powers) / len(powers), 1) if powers else None
    )
    nic_keys = sorted({k for n in nodes for k in n if k.startswith(NIC_PREFIX)})
    for key in nic_keys:
        values = [n.get(key) for n in nodes]
        totals[key] = sum(values) if all(v is not None for v in values) else None
    summary = {
        "totals": totals,
        "slurm_steps": read_sacct(os.path.join(tel_dir, "sacct.txt")),
        "nodes": nodes,
    }
    with open(out_path, "w") as handle:
        json.dump(summary, handle, indent=1)
    print(
        "telemetry: {0} nodes, {1} J, mean node power {2} W".format(
            totals["nodes_sampled"], totals["energy_j"], totals["node_power_mean_w"]
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
