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
# reads both.
COLS = ['step', 'rss_MB', 'init_writer', 'writer_open', 'compute_step', 'write_step', 'total_step']

# Define the percentiles for the heartbeat plot
def p25(x): return np.percentile(x, 25)
def p75(x): return np.percentile(x, 75)

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
                rows.append({"step": r["step"], "rss_MB": r["rss_MB"],
                             "init_writer": t.get("create_writer", t.get("init_writer", 0.0)),
                             "writer_open": t.get("writer_open", 0.0),
                             "compute_step": t.get("compute_step", 0.0),
                             "write_step": t.get("write_step", 0.0),
                             "total_step": t["total_step"]})
            except (ValueError, KeyError) as e:
                raise RuntimeError(f"{file_path}:{n}: bad step record ({e!r})") from e
    if not rows:
        raise RuntimeError(f"{file_path}: no step records")
    return pd.DataFrame(rows, columns=COLS)

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

    print(f"Found {len(files)} rank files ({'JSONL' if loader is load_jsonl else 'CSV'}). Reducing in parallel...")

    # 1. Read all files in parallel (Max out the node's CPU/Disk IO)
    with ProcessPoolExecutor() as executor:
        dfs = list(executor.map(loader, files))
        
    # Filter out any empty dataframes caused by read errors
    dfs = [df for df in dfs if not df.empty]
        
    # 2. Concatenate into one master dataframe
    full_df = pd.concat(dfs, ignore_index=True)
    
    # Define the exhaustive statistical metrics we want for every column
    metrics = ['mean', 'min', 'max', p25, p75]
    
    # 3. Group by step and calculate aggregations across all 3000+ ranks
    summary = full_df.groupby('step').agg({
        'total_step':   metrics,
        'compute_step': metrics,
        'write_step':   metrics,
        'init_writer':  metrics, 
        'writer_open':  metrics,
        'rss_MB':       metrics 
    })
    
    # Flatten the multi-level column names (e.g., 'total_step', 'mean' -> 'total_step_mean')
    summary.columns = ['_'.join(col).strip() for col in summary.columns.values]
    
    # Save to a tiny summary file
    summary.to_csv(output_csv)
    print(f"Success! Saved exhaustive summary to: {output_csv}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reduce thousands of Gray-Scott rank CSVs into one summary file.")
    parser.add_argument("input_dir", help="A run's perf/<run> directory (new log) or its writer_timers/ directory (runs before #26)")
    parser.add_argument("output_file", help="Name of the output summary CSV (e.g., summary_catalyst.csv)")
    args = parser.parse_args()
    
    reduce_run_data(args.input_dir, args.output_file)
