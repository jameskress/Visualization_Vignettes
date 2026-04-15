import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import argparse
import sys

# Define the percentiles for the heartbeat plot (using nanpercentile just in case of missing data)
def p25(x): return np.nanpercentile(x, 25)
def p75(x): return np.nanpercentile(x, 75)

def load_csv(file_path):
    """Loads a single rank's CSV. Dynamically reads all columns instead of hardcoding."""
    try:
        return pd.read_csv(file_path)
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

    print(f"Found {len(files)} rank files. Reducing in memory-safe batches...")
    
    dfs = []
    chunk_size = 10000  # Process 10,000 files at a time to save RAM
    
    # 1. Read files in chunks with a hard limit on parallel workers
    for i in range(0, len(files), chunk_size):
        chunk = files[i:i + chunk_size]
        print(f"  -> Reading files {i + 1} to {min(i + chunk_size, len(files))}...")
        
        # Restrict to 16 workers so we don't blow up the node's thread/memory limits
        with ProcessPoolExecutor(max_workers=16) as executor:
            results = list(executor.map(load_csv, chunk))
            dfs.extend([df for df in results if not df.empty])
            
    print("Concatenating master dataframe...")
    # 2. Concatenate into one master dataframe
    full_df = pd.concat(dfs, ignore_index=True)
    
    # Define the exhaustive statistical metrics we want for every column
    metrics = ['mean', 'min', 'max', p25, p75]
    
    # 3. Build aggregation dictionary dynamically for ALL numeric columns (except 'step')
    agg_dict = {}
    for col in full_df.columns:
        if col != 'step' and pd.api.types.is_numeric_dtype(full_df[col]):
            agg_dict[col] = metrics
    
    print("Calculating statistics...")
    # 4. Group by step and calculate aggregations across all ranks
    summary = full_df.groupby('step').agg(agg_dict)
    
    # Flatten the multi-level column names
    summary.columns = ['_'.join(col).strip() for col in summary.columns.values]
    
    # Save to a tiny summary file
    summary.to_csv(output_csv)
    print(f"Success! Saved exhaustive summary to: {output_csv}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reduce thousands of Gray-Scott rank CSVs into one summary file.")
    parser.add_argument("input_dir", help="Directory containing the rank CSVs (e.g., path/to/writer_timers/)")
    parser.add_argument("output_file", help="Name of the output summary CSV (e.g., summary_catalyst.csv)")
    args = parser.parse_args()
    
    reduce_run_data(args.input_dir, args.output_file)
