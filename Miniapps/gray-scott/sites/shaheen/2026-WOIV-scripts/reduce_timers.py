import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import argparse
import sys

# Define the percentiles for the heartbeat plot
def p25(x): return np.percentile(x, 25)
def p75(x): return np.percentile(x, 75)

def load_csv(file_path):
    """Loads only the necessary columns from a single rank's CSV to save memory."""
    cols = ['step', 'rss_MB', 'init_writer', 'writer_open', 'compute_step', 'write_step', 'total_step']
    try:
        return pd.read_csv(file_path, usecols=cols)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return pd.DataFrame()

def reduce_run_data(run_dir, output_csv):
    print(f"Processing directory: {run_dir}...")
    
    # Find all CSV files in the directory (searches recursively)
    files = list(Path(run_dir).rglob("*.csv"))
    if not files:
        print(f"No CSV files found in {run_dir}")
        sys.exit(1)

    print(f"Found {len(files)} rank files. Reducing in parallel...")
    
    # 1. Read all files in parallel (Max out the node's CPU/Disk IO)
    with ProcessPoolExecutor() as executor:
        dfs = list(executor.map(load_csv, files))
        
    # Filter out any empty dataframes caused by read errors
    dfs = [df for df in dfs if not df.empty]
        
    # 2. Concatenate into one master dataframe
    full_df = pd.concat(dfs, ignore_index=True)
    
    # 3. Group by step and calculate aggregations across all 3000+ ranks
    summary = full_df.groupby('step').agg({
        'total_step':   ['mean', 'min', 'max', p25, p75],
        'compute_step': ['mean'],
        'write_step':   ['mean'],
        'init_writer':  ['mean', 'max'], 
        'writer_open':  ['mean', 'max'],
        'rss_MB':       ['mean', 'max'] 
    })
    
    # Flatten the multi-level column names (e.g., 'total_step', 'mean' -> 'total_step_mean')
    summary.columns = ['_'.join(col).strip() for col in summary.columns.values]
    
    # Save to a tiny summary file
    summary.to_csv(output_csv)
    print(f"Success! Saved summary to: {output_csv}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reduce thousands of Gray-Scott rank CSVs into one summary file.")
    parser.add_argument("input_dir", help="Directory containing the rank CSVs (e.g., path/to/writer_timers/)")
    parser.add_argument("output_file", help="Name of the output summary CSV (e.g., summary_catalyst.csv)")
    args = parser.parse_args()
    
    reduce_run_data(args.input_dir, args.output_file)
