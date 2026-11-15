import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import argparse
import json
import sys

# Two input formats, one output (#71):
#  * runs made before #26 (the 2026 WOIV runs): writer_timers/rank_<r>.csv,
#    one row per step, timers in seconds;
#  * newer runs: a run directory under perf/ (or its steps/ folder) with
#    steps/rank_<r>.jsonl, one JSON object per step: timers in "t" (seconds),
#    rss_MB at top level. The new log calls init_writer create_writer.
# Either way the summary CSV has the same columns, so plot_performance.py
# reads both. A JSONL log also gets a column for every other timer and
# counter its records hold (the reader's ADIOS_Wait and ADIOS_EndStep, the
# writer's io and halo, counters as c_<name>, sys_s and user_s), so nothing
# the run measured is dropped; a timer a rank never logged is left out of
# that rank's statistics rather than counted as zero.
COLS = [
    "step",
    "rss_MB",
    "init_writer",
    "writer_open",
    "compute_step",
    "write_step",
    "total_step",
]
# Always present, as before: 0.0 where a log does not have them.
LEGACY = [
    "total_step",
    "compute_step",
    "write_step",
    "init_writer",
    "writer_open",
    "rss_MB",
]


# Define the percentiles for the heartbeat plot
def p25(x):
    return np.nanpercentile(x, 25) if np.isfinite(x).any() else np.nan


def p75(x):
    return np.nanpercentile(x, 75) if np.isfinite(x).any() else np.nan


def load_csv(file_path):
    """Loads only the necessary columns from a single rank's CSV to save memory."""
    try:
        return pd.read_csv(file_path, usecols=COLS)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return pd.DataFrame()


def load_jsonl(file_path):
    """One rank's step records from the structured performance log.

    A bad line or a record without rss_MB or total_step stops the reduction:
    dropping a rank would report a summary of the other ranks as complete.
    """
    rows = []
    with open(file_path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                t = r["t"]
                row = {
                    "step": r["step"],
                    "rss_MB": r["rss_MB"],
                    "init_writer": t.get("create_writer", t.get("init_writer", 0.0)),
                    "writer_open": t.get("writer_open", 0.0),
                    "compute_step": t.get("compute_step", 0.0),
                    "write_step": t.get("write_step", 0.0),
                    "total_step": t["total_step"],
                }
                for name, value in t.items():
                    if name not in row and name != "create_writer":
                        row[name] = float(value)
                for name, value in (r.get("c") or {}).items():
                    row["c_" + name] = float(value)
                for name in ("sys_s", "user_s"):
                    if name in r:
                        row[name] = float(r[name])
                rows.append(row)
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                raise RuntimeError(f"{file_path}:{n}: bad step record ({e!r})") from e
    if not rows:
        raise RuntimeError(f"{file_path}: no step records")
    return pd.DataFrame(rows)


def reduce_run_data(run_dir, output_csv):
    print(f"Processing directory: {run_dir}...")

    # New-format step files first; fall back to the old per-rank CSVs.
    files = sorted(Path(run_dir).rglob("rank_*.jsonl"))
    loader = load_jsonl
    if not files:
        files = list(Path(run_dir).rglob("*.csv"))
        loader = load_csv
    if not files:
        print(f"No rank_*.jsonl or CSV files found in {run_dir}")
        sys.exit(1)

    print(
        f"Found {len(files)} rank files ({'JSONL' if loader is load_jsonl else 'CSV'}). Reducing in parallel..."
    )

    # 1. Read all files in parallel (Max out the node's CPU/Disk IO)
    with ProcessPoolExecutor() as executor:
        dfs = list(executor.map(loader, files))

    # Filter out any empty dataframes caused by read errors
    dfs = [df for df in dfs if not df.empty]

    # 2. Concatenate into one master dataframe
    full_df = pd.concat(dfs, ignore_index=True)

    # Define the exhaustive statistical metrics we want for every column
    metrics = ["mean", "min", "max", p25, p75]

    # 3. Group by step and calculate aggregations across all 3000+ ranks:
    # the legacy columns first (in their old order), then every other one
    # by name. NaN (a timer this rank did not log) is skipped, not zero.
    extra = sorted(c for c in full_df.columns if c != "step" and c not in LEGACY)
    summary = full_df.groupby("step").agg({c: metrics for c in LEGACY + extra})

    # Flatten the multi-level column names (e.g., 'total_step', 'mean' -> 'total_step_mean')
    summary.columns = ["_".join(col).strip() for col in summary.columns.values]

    # Save to a tiny summary file
    summary.to_csv(output_csv)
    print(f"Success! Saved exhaustive summary to: {output_csv}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reduce thousands of Gray-Scott rank CSVs into one summary file."
    )
    parser.add_argument(
        "input_dir",
        help="A run's perf/<run> directory (new log) or its writer_timers/ directory (runs before #26)",
    )
    parser.add_argument(
        "output_file",
        help="Name of the output summary CSV (e.g., summary_catalyst.csv)",
    )
    args = parser.parse_args()

    reduce_run_data(args.input_dir, args.output_file)
