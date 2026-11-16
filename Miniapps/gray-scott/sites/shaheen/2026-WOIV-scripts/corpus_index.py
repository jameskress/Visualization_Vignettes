"""Index Gray-Scott runs into one table for the telemetry corpus.

Usage: corpus_index.py [--topology FILE] <out_prefix> <results_dir> [<results_dir> ...]

--topology: a saved `scontrol show topology`, for runs that did not save
their own (runs before the topology capture); placement columns stay empty
without one.

Writes <out_prefix>.csv and <out_prefix>.jsonl, one row per run found in the
results directories (a run is any <id>_job.sbat). Each row holds:

* what was run: id, simulation and staging nodes, ranks, backends, grid,
  steps, reader decomposition, memory selection, ADIOS2 version, build;
* headline numbers: mean simulation step times over every simulation step
  from 1 up (most steps write nothing, so writer_write_step_s is small),
  the writer's io (BeginStep, Put and EndStep; the data moves at EndStep),
  mean reader step times over its steps from 1 up (step 0 includes
  start-up), the reader's wait for a step (BeginStep), EndStep, build and
  vis times (these need a _reader.csv reduced by the current
  reduce_timers.py; older ones leave them empty),
  sampled energy and node power, and Darshan's bytes read and written
  (with the number of logs and how many parsed; the bytes are empty unless
  every log parsed);
* where everything is: the path of each artifact (timers, telemetry,
  accounting, environment snapshot, Darshan logs, MPICH counters), empty
  when a run does not have it.

Only the standard library is used. Missing or unreadable inputs leave their
columns empty; nothing is guessed.
"""

import csv
import glob
import json
import math
import os
import re
import sys

READER_KEYS = (
    "total_step",
    "ADIOS_Wait",
    "Step_Latency",
    "ADIOS_EndStep",
    "Blueprint_Time",
    "Vis_Time",
)
WRITER_KEYS = ("total_step", "compute_step", "write_step", "io", "endstep_barrier")
DARSHAN_KEYS = (
    "total_POSIX_BYTES_READ",
    "total_POSIX_BYTES_WRITTEN",
    "total_MPIIO_BYTES_READ",
    "total_MPIIO_BYTES_WRITTEN",
    "total_STDIO_BYTES_READ",
    "total_STDIO_BYTES_WRITTEN",
)


def _load_json(path):
    try:
        with open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _csv_means(path, keys):
    """Mean of each <key>_mean column over rows with step >= 1."""
    try:
        with open(path, newline="") as handle:
            rows = [r for r in csv.DictReader(handle) if r.get("step", "0") != "0"]
    except OSError:
        return {key: None for key in keys}
    out = {}
    for key in keys:
        values = []
        for row in rows:
            try:
                value = float(row[key + "_mean"])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(value):  # nan or inf would make invalid JSON
                values.append(value)
        out[key] = round(sum(values) / len(values), 4) if values else None
    return out


def _darshan_totals(directory):
    """Sum of each counter over a run's logs, and how many logs there are and
    how many parsed. The totals are empty unless every log parsed (a partial
    sum would look complete), and a counter is empty when no log has a valid
    (non-negative) value for it; Darshan writes -1 for unknown."""
    logs = glob.glob(os.path.join(directory, "*.darshan"))
    # Each log's own summary (<log>.total.txt beside <log>.darshan): a log
    # counts as parsed only if that file reads; summaries with no log are
    # ignored, so an extra file can never make up for a missing one.
    texts = []
    for log in logs:
        try:
            with open(log[: -len(".darshan")] + ".total.txt") as handle:
                texts.append(handle.read())
        except OSError:
            pass  # missing or unreadable: not parsed
    totals = {key: None for key in DARSHAN_KEYS}
    totals["logs"] = len(logs)
    totals["logs_parsed"] = len(texts)
    if not logs or len(texts) < len(logs):
        return totals
    for text in texts:
        for key in DARSHAN_KEYS:
            match = re.search(r"^" + key + r":\s+(-?\d+)", text, re.M)
            if match and int(match.group(1)) >= 0:
                totals[key] = (totals[key] or 0) + int(match.group(1))
    return totals


def _expand_hostlist(spec):
    """Slurm's compressed host list ("nid[00089-00090,00262],login1") as names."""
    parts, depth, cur = [], 0, ""
    for ch in spec:
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
            continue
        depth += ch == "["
        depth -= ch == "]"
        cur += ch
    if cur:
        parts.append(cur)
    names = []
    for part in parts:
        m = re.match(r"^([^\[]+)\[([^\]]*)\]$", part)
        if not m:
            names.append(part)
            continue
        prefix, ranges = m.groups()
        for r in ranges.split(","):
            if "-" in r:
                a, b = r.split("-", 1)
                names += [
                    "%s%0*d" % (prefix, len(a), n) for n in range(int(a), int(b) + 1)
                ]
            else:
                names.append(prefix + r)
    return names


def _topology(path):
    """Node -> (leaf switch, level-1 switch) from `scontrol show topology`.

    On Shaheen III the leaf switches serve 16 nodes each (x1005c0r3) and the
    level-1 entries are the 256-node dragonfly groups (group4)."""
    leaf, group = {}, {}
    try:
        with open(path) as handle:
            text = handle.read()
    except OSError:
        return None
    for line in text.splitlines():
        name = re.search(r"SwitchName=(\S+)", line)
        level = re.search(r"Level=(\d+)", line)
        nodes = re.search(r"\bNodes=(\S+)", line)
        if not (name and level and nodes):
            continue
        target = (
            leaf if level.group(1) == "0" else group if level.group(1) == "1" else None
        )
        if target is not None:
            for node in _expand_hostlist(nodes.group(1)):
                target[node] = name.group(1)
    return (leaf, group) if leaf else None


def _placement(job_nodes, sim_nodes, topo):
    """Groups and leaf switches the simulation and the readers span."""
    out = {
        "placement_job_groups": None,
        "placement_sim_groups": None,
        "placement_stage_groups": None,
        "placement_shared_groups": None,
        "placement_sim_switches": None,
        "placement_stage_switches": None,
        "placement_unknown_nodes": None,
    }
    if not topo or not job_nodes:
        return out
    leaf, group = topo
    sim = [n for n in job_nodes if n in sim_nodes] if sim_nodes else []
    stage = [n for n in job_nodes if n not in sim_nodes] if sim_nodes else []
    out["placement_unknown_nodes"] = sum(1 for n in job_nodes if n not in leaf)
    out["placement_job_groups"] = len({group[n] for n in job_nodes if n in group})
    if sim_nodes:
        sim_g = {group[n] for n in sim if n in group}
        stage_g = {group[n] for n in stage if n in group}
        out["placement_sim_groups"] = len(sim_g)
        out["placement_stage_groups"] = len(stage_g)
        out["placement_shared_groups"] = len(sim_g & stage_g)
        out["placement_sim_switches"] = len({leaf[n] for n in sim if n in leaf})
        out["placement_stage_switches"] = len({leaf[n] for n in stage if n in leaf})
    return out


def _platform_nodes(path):
    """Per-node platform lines (node_platform.sh line): how many nodes, how
    many distinct platforms among them, and the NIC firmware versions."""
    try:
        with open(path) as handle:
            lines = [ln.split() for ln in handle if ln.startswith("host=")]
    except OSError:
        return None, None, None
    variants, firmware = set(), set()
    for fields in lines:
        kv = dict(f.split("=", 1) for f in fields if "=" in f)
        kv.pop("host", None)
        variants.add(tuple(sorted(kv.items())))
        firmware.add(kv.get("nic_fw", "na"))
    return len(lines), len(variants), ";".join(sorted(firmware))


def _sbatch_value(text, option):
    match = re.search(r"^#SBATCH --" + option + r"=(\S+)", text, re.M)
    return match.group(1) if match else None


def index_run(results_dir, run_id, fallback_topology=None):
    base = os.path.join(results_dir, run_id)
    run_dir = base  # the run's own directory (settings, data, telemetry)

    def artifact(suffix):
        path = base + suffix
        return path if os.path.exists(path) else ""

    row = {"id": run_id, "results_dir": results_dir}
    match = re.search(r"_N(\d+)(?:_S(\d+))?", run_id)
    row["sim_nodes"] = int(match.group(1)) if match else None
    text = ""
    job = artifact("_job.sbat")
    if job:
        try:
            text = open(job).read()
        except OSError:
            text = ""
    row["job_nodes"] = _sbatch_value(text, "nodes")
    row["job_ntasks"] = _sbatch_value(text, "ntasks")
    row["job_time"] = _sbatch_value(text, "time")
    # Staging nodes from the ID's _S part, else the job's nodes minus the
    # simulation's (paper1_func_N0064_transit_* has 4 and no _S); empty if
    # neither is known.
    if match and match.group(2):
        row["stage_nodes"] = int(match.group(2))
    elif row["sim_nodes"] is not None and (row["job_nodes"] or "").isdigit():
        row["stage_nodes"] = int(row["job_nodes"]) - row["sim_nodes"]
    else:
        row["stage_nodes"] = None
    settings = _load_json(os.path.join(run_dir, "settings.json")) or {}
    stage = _load_json(os.path.join(run_dir, "settings-stage.json")) or {}
    row["sim_output"] = settings.get("output_type")
    row["stage_output"] = stage.get("output_type")
    row["grid_L"] = settings.get("L")
    row["steps"] = settings.get("steps")
    row["plotgap"] = settings.get("plotgap")
    row["read_decomposition"] = settings.get("read_decomposition")
    row["reader_shared_planes"] = settings.get("reader_shared_planes")
    row["adios_endstep_barrier"] = settings.get("adios_endstep_barrier")
    row["adios_memory_selection"] = settings.get("adios_memory_selection")
    meta = _load_json(base + "_metadata.json") or {}
    row["adios2_version"] = (meta.get("backend") or {}).get("version")
    build = meta.get("build") or {}
    row["compiler"] = (
        "{0} {1}".format(
            build.get("compiler_id", ""), build.get("compiler_version", "")
        ).strip()
        or None
    )
    row["build_type"] = build.get("build_type")
    # Provenance: the commits that built the two programs (from a git
    # checkout, or the archive file in builds from git archive), the ADIOS2
    # library actually loaded, and rank 0's node platform.
    git = meta.get("git") or {}
    row["sim_git_commit"] = git.get("commit")
    row["sim_git_describe"] = git.get("describe")
    rmeta = _load_json(base + "_reader_metadata.json") or {}
    row["reader_git_commit"] = (rmeta.get("git") or {}).get("commit")
    libs = meta.get("libraries") or []
    row["adios2_library"] = next((lib for lib in libs if "libadios2_core" in lib), None)
    plat = (meta.get("host") or {}).get("platform") or {}
    for key in (
        "kernel",
        "os",
        "cpu_governor",
        "cpu_boost",
        "numa_nodes",
        "mem_total_kB",
    ):
        row["platform_" + key] = plat.get(key)
    for key, value in _csv_means(base + "_writer.csv", WRITER_KEYS).items():
        row["writer_" + key + "_s"] = value
    for key, value in _csv_means(base + "_reader.csv", READER_KEYS).items():
        row["reader_" + key + "_s"] = value
    tel = _load_json(base + "_telemetry.json") or {}
    totals = tel.get("totals") or {}
    row["job_id"] = tel.get("job_id")
    # Placement: the job's nodes (Slurm's job record), the simulation's (its
    # metadata), the rest are the readers', against the network topology the
    # run saved, or the --topology fallback.
    job_nodes = []
    job_txt = os.path.join(run_dir, "telemetry", str(row["job_id"]), "job.txt")
    try:
        with open(job_txt) as handle:
            m = re.search(r"^\s*NodeList=(\S+)", handle.read(), re.M)
        if m and m.group(1) != "(null)":
            job_nodes = _expand_hostlist(m.group(1))
    except OSError:
        pass
    sim_nodes = set((meta.get("host") or {}).get("hostnames") or [])
    topo = _topology(base + "_tel_topology.txt") or fallback_topology
    row.update(_placement(job_nodes, sim_nodes, topo))
    n, variants, firmware = _platform_nodes(base + "_tel_platform_nodes.txt")
    row["platform_nodes_listed"] = n
    row["platform_variants"] = variants
    row["platform_nic_fw"] = firmware
    row["energy_j"] = totals.get("energy_j")
    row["node_power_mean_w"] = totals.get("node_power_mean_w")
    row["nodes_sampled"] = totals.get("nodes_sampled")
    row["nodes_expected"] = totals.get("nodes_expected")
    row["nic_tx_bytes"] = totals.get("nic_hni_sts_tx_ok_octets")
    row["nic_rx_bytes"] = totals.get("nic_hni_sts_rx_ok_octets")
    darshan_dir = artifact("_darshan")
    blank = {k: None for k in DARSHAN_KEYS + ("logs", "logs_parsed")}
    for key, value in (_darshan_totals(darshan_dir) if darshan_dir else blank).items():
        row["darshan_" + key.replace("total_", "").lower()] = value
    for name, suffix in (
        ("job_script", "_job.sbat"),
        ("metadata", "_metadata.json"),
        ("summary", "_summary.json"),
        ("writer_csv", "_writer.csv"),
        ("reader_csv", "_reader.csv"),
        ("telemetry", "_telemetry.json"),
        ("sacct", "_sacct.txt"),
        ("env", "_env.txt"),
        ("tel_env", "_tel_env.txt"),
        ("tel_modules", "_tel_modules.txt"),
        ("tel_ldd", "_tel_ldd.txt"),
        ("tel_source", "_tel_source.txt"),
        ("tel_job", "_tel_job.txt"),
        ("darshan_dir", "_darshan"),
        ("mpich_cxi_summary", "_mpich_cxi_summary.txt"),
        ("reader_metadata", "_reader_metadata.json"),
        ("tel_topology", "_tel_topology.txt"),
        ("tel_platform", "_tel_platform.txt"),
        ("tel_platform_nodes", "_tel_platform_nodes.txt"),
    ):
        row["path_" + name] = artifact(suffix)
    row["path_run_dir"] = run_dir if os.path.isdir(run_dir) else ""
    return row


def main(argv):
    argv = list(argv)
    fallback = None
    if len(argv) > 2 and argv[1] == "--topology":
        fallback = _topology(argv[2])
        if fallback is None:
            print("corpus_index: cannot read a topology from " + argv[2])
            return 2
        del argv[1:3]
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[2])
        return 2
    prefix = argv[1]
    rows = []
    for results_dir in argv[2:]:
        for job in sorted(glob.glob(os.path.join(results_dir, "*_job.sbat"))):
            run_id = os.path.basename(job)[: -len("_job.sbat")]
            rows.append(index_run(os.path.abspath(results_dir), run_id, fallback))
    if not rows:
        print("corpus_index: no runs (no *_job.sbat) found")
        return 1
    columns = []
    for row in rows:
        columns.extend(k for k in row if k not in columns)
    with open(prefix + ".csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    with open(prefix + ".jsonl", "w") as handle:
        for row in rows:
            handle.write(json.dumps(row, allow_nan=False) + "\n")
    print("corpus_index: {0} runs -> {1}.csv, {1}.jsonl".format(len(rows), prefix))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
