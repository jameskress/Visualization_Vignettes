"""Index Gray-Scott runs into one table for the telemetry corpus.

Usage: corpus_index.py <out_prefix> <results_dir> [<results_dir> ...]

Writes <out_prefix>.csv and <out_prefix>.jsonl, one row per run found in the
results directories (a run is any <id>_job.sbat). Each row holds:

* what was run: id, simulation and staging nodes, ranks, backends, grid,
  steps, reader decomposition, memory selection, ADIOS2 version, build;
* headline numbers: mean simulation step times over every simulation step
  from 1 up (most steps write nothing, so writer_write_step_s is small),
  mean reader step times over its steps from 1 up (step 0 includes
  start-up), the reader's EndStep, build and vis times,
  sampled energy and node power, and Darshan's bytes read and written;
* where everything is: the path of each artifact (timers, telemetry,
  accounting, environment snapshot, Darshan logs, MPICH counters), empty
  when a run does not have it.

Only the standard library is used. Missing or unreadable inputs leave their
columns empty; nothing is guessed.
"""

import csv
import glob
import json
import os
import re
import sys

READER_KEYS = ("total_step", "ADIOS_EndStep", "Blueprint_Time", "Vis_Time")
WRITER_KEYS = ("total_step", "compute_step", "write_step")
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
                values.append(float(row[key + "_mean"]))
            except (KeyError, TypeError, ValueError):
                pass
        out[key] = round(sum(values) / len(values), 4) if values else None
    return out


def _darshan_totals(directory):
    """Sum of each counter over a run's logs; None for a counter no log has a
    valid (non-negative) value for. Darshan writes -1 for unknown."""
    totals = {key: None for key in DARSHAN_KEYS}
    for path in glob.glob(os.path.join(directory, "*.total.txt")):
        try:
            text = open(path).read()
        except OSError:
            continue
        for key in DARSHAN_KEYS:
            match = re.search(r"^" + key + r":\s+(-?\d+)", text, re.M)
            if match and int(match.group(1)) >= 0:
                totals[key] = (totals[key] or 0) + int(match.group(1))
    return totals


def _sbatch_value(text, option):
    match = re.search(r"^#SBATCH --" + option + r"=(\S+)", text, re.M)
    return match.group(1) if match else None


def index_run(results_dir, run_id):
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
    for key, value in _csv_means(base + "_writer.csv", WRITER_KEYS).items():
        row["writer_" + key + "_s"] = value
    for key, value in _csv_means(base + "_reader.csv", READER_KEYS).items():
        row["reader_" + key + "_s"] = value
    tel = _load_json(base + "_telemetry.json") or {}
    totals = tel.get("totals") or {}
    row["job_id"] = tel.get("job_id")
    row["energy_j"] = totals.get("energy_j")
    row["node_power_mean_w"] = totals.get("node_power_mean_w")
    row["nodes_sampled"] = totals.get("nodes_sampled")
    row["nodes_expected"] = totals.get("nodes_expected")
    row["nic_tx_bytes"] = totals.get("nic_hni_sts_tx_ok_octets")
    row["nic_rx_bytes"] = totals.get("nic_hni_sts_rx_ok_octets")
    darshan_dir = artifact("_darshan")
    for key, value in (
        _darshan_totals(darshan_dir) if darshan_dir else {k: None for k in DARSHAN_KEYS}
    ).items():
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
        ("darshan_dir", "_darshan"),
        ("mpich_cxi_summary", "_mpich_cxi_summary.txt"),
    ):
        row["path_" + name] = artifact(suffix)
    row["path_run_dir"] = run_dir if os.path.isdir(run_dir) else ""
    return row


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[2])
        return 2
    prefix = argv[1]
    rows = []
    for results_dir in argv[2:]:
        for job in sorted(glob.glob(os.path.join(results_dir, "*_job.sbat"))):
            run_id = os.path.basename(job)[: -len("_job.sbat")]
            rows.append(index_run(os.path.abspath(results_dir), run_id))
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
            handle.write(json.dumps(row) + "\n")
    print("corpus_index: {0} runs -> {1}.csv, {1}.jsonl".format(len(rows), prefix))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
