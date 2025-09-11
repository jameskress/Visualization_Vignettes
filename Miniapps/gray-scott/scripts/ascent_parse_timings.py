import json
from collections import defaultdict
import glob
import re

def parse_ascent_timings():
    """
    Parses all 'timings.*.txt' or 'ascent_filter_times_*.csv' files, assuming 
    one file per rank, and combines them into a single, correctly ordered JSON 
    file with a timestep-major structure suitable for plotting.
    """
    # Intermediate structure to hold data as it's read: 
    # {rank: {operation: [time_step_0, time_step_1, ...]}}
    per_rank_data = defaultdict(lambda: defaultdict(list))
    
    # Find all potential timing files
    timing_files = glob.glob("timings.*.txt") + glob.glob("ascent_filter_times_*.csv")
    if not timing_files:
        print("Error: No 'timings.*.txt' or 'ascent_filter_times_*.csv' files found.")
        return

    # --- Sort files numerically by rank to ensure correct processing order ---
    def get_rank_from_filename(f):
        # Extracts number from '..._123.csv' or '..._123.txt'
        match = re.search(r'[_.](\d+)\.(?:txt|csv)$', f)
        return int(match.group(1)) if match else -1

    sorted_files = sorted(timing_files, key=get_rank_from_filename)
    print(f"Found and sorted {len(sorted_files)} timing files to process...")

    # --- Step 1: Read all data, grouping by rank first ---
    all_ops = set()
    for filename in sorted_files:
        rank_from_file = get_rank_from_filename(filename)
        if rank_from_file == -1:
            print(f"Warning: Could not extract rank from '{filename}'. Skipping.")
            continue

        with open(filename, 'r') as f:
            for line in f:
                try:
                    # The format is 'rank operation time'
                    rank_str, operation, time_str = line.strip().split()
                    time_val = float(time_str)
                    
                    # Store data in the per-rank structure. The line order within
                    # the file determines the timestep order.
                    per_rank_data[rank_from_file][operation].append(time_val)
                    all_ops.add(operation)
                except ValueError:
                    continue # Ignore malformed lines

    if not per_rank_data:
        print("Error: No valid timing data was parsed.")
        return

    # --- Step 2: Transpose the data to the final structure ---
    # Final structure: { "operation": { "timestep": [rank0_time, rank1_time, ...] } }
    output_data = defaultdict(lambda: defaultdict(list))
    
    try:
        # Determine number of steps and ranks from the collected data
        sorted_ranks = sorted(per_rank_data.keys())
        first_rank_data = per_rank_data[sorted_ranks[0]]
        # Find an operation that exists for the first rank to determine num_steps
        first_op = next(iter(first_rank_data))
        num_steps = len(first_rank_data[first_op])
    except (IndexError, KeyError, StopIteration):
        print("Error: Parsed data is inconsistent. Cannot determine number of steps.")
        return
        
    for op in sorted(list(all_ops)):
        for step_idx in range(num_steps):
            times_at_step = []
            for rank in sorted_ranks:
                # Append the time for the current rank at the current step.
                # Use a default value of 0.0 to handle cases where an operation
                # might be missing for a given rank or step (ragged data).
                op_times = per_rank_data[rank].get(op, [])
                if step_idx < len(op_times):
                    times_at_step.append(op_times[step_idx])
                else:
                    times_at_step.append(0.0)
            
            output_data[op][str(step_idx)] = times_at_step

    # --- Write the correctly structured JSON file ---
    output_filename = "ascent_timings_summary.json"
    with open(output_filename, 'w') as f:
        json.dump(output_data, f, indent=4)

    print(f"Successfully created correctly ordered summary file: {output_filename}")


if __name__ == "__main__":
    parse_ascent_timings()
