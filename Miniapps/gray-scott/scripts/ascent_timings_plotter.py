import json
import sys
import argparse
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from collections import defaultdict

def process_data_timestep_major(data):
    """
    Processes raw JSON data to create a flattened structure for plotting
    a stacked bar for each rank at each step.
    """
    processed = {
        'flat_stacked_data': defaultdict(list),
        'box_plot_data': defaultdict(list),
        'flat_total_line_data': [],
        'x_tick_positions': [],
        'x_tick_labels': [],
        'x_minor_tick_positions': [],
        'x_minor_tick_labels': [],
        'step_boundary_positions': []
    }

    if not data:
        return processed

    # --- Separate '[total]' from other operations ---
    total_data = data.pop('[total]', None)
    operations = list(data.keys())
    
    if not operations or not total_data:
        print("Warning: Data is missing operations or '[total]' entry. Cannot generate full plot.")
        return processed

    # --- Determine timesteps and ranks ---
    try:
        timesteps = sorted([int(k) for k in total_data.keys()])
        # Get number of ranks from the length of the array at the first timestep
        num_ranks = len(total_data[str(timesteps[0])])
    except (ValueError, IndexError, KeyError):
        print("Warning: Could not determine timesteps or ranks from data. Cannot process.")
        return processed

    # --- Create Flattened Data Structures ---
    x_pos = 0
    for step in timesteps:
        step_str = str(step)
        
        # Calculate positions and labels for the major x-axis ticks (Steps)
        processed['x_tick_positions'].append(x_pos + (num_ranks - 1) / 2.0)
        processed['x_tick_labels'].append(f'Step {step}')
        
        # Calculate average total time for the reference line
        avg_total_for_step = np.mean(total_data[step_str])
        
        for rank in range(num_ranks):
            # For each operation, get the time for this specific rank and step
            for op in operations:
                processed['flat_stacked_data'][op].append(data[op][step_str][rank])
            
            # Add minor ticks for individual rank labels
            processed['x_minor_tick_positions'].append(x_pos)
            processed['x_minor_tick_labels'].append(str(rank))
            
            # Repeat the average total time for each rank in the step for the line plot
            processed['flat_total_line_data'].append(avg_total_for_step)
            x_pos += 1
            
        # Add a boundary line after each step group, except the last one
        if step < timesteps[-1]:
            processed['step_boundary_positions'].append(x_pos - 0.5)

    # --- Prepare data for Box Plot (un-flattened) ---
    for op, step_data in data.items():
        for times_per_rank in step_data.values():
            processed['box_plot_data'][op].extend(times_per_rank)
            
    return processed

def plot_performance(processed_data, json_filename, show_plot):
    """
    Generates a multi-panel plot visualizing the performance data.
    """
    try:
        plt.style.use('seaborn-v0_8-whitegrid')
    except IOError:
        print("Warning: Style 'seaborn-v0_8-whitegrid' not found. Falling back to 'ggplot'.")
        plt.style.use('ggplot')

    fig = plt.figure(figsize=(24, 18), constrained_layout=True)
    gs = GridSpec(2, 1, figure=fig, height_ratios=[1, 1])
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[1, 0])

    fig.suptitle(f'Ascent Performance Analysis\n({json_filename})', fontsize=22, weight='bold')

    # --- 1. Detailed Stacked Bar Chart per Rank per Step ---
    flat_stacked_data = processed_data['flat_stacked_data']
    if flat_stacked_data:
        sorted_ops = sorted(flat_stacked_data.keys(), key=lambda op: np.mean(flat_stacked_data[op]), reverse=True)
        
        num_bars = len(list(flat_stacked_data.values())[0])
        x = np.arange(num_bars)
        bottom = np.zeros(num_bars)
        colors = plt.cm.viridis(np.linspace(0, 1, len(sorted_ops)))

        for i, op in enumerate(sorted_ops):
            ax1.bar(x, flat_stacked_data[op], bottom=bottom, label=op, color=colors[i], edgecolor='black', linewidth=0.5, width=1.0)
            bottom += np.array(flat_stacked_data[op])
            
        # Add the average total time as a reference line
        if processed_data['flat_total_line_data']:
            ax1.plot(x, processed_data['flat_total_line_data'], color='black', marker='_', markersize=8, linestyle='--', label='[total] (avg)', zorder=10)
            
        # Add vertical lines to separate timesteps
        for pos in processed_data['step_boundary_positions']:
            ax1.axvline(x=pos, color='grey', linestyle='--', linewidth=1.2)

        ax1.set_title('Time Breakdown per Rank for Each Step', fontsize=18, weight='bold')
        ax1.set_ylabel('Time (seconds)', fontsize=14)
        ax1.legend(title='Operations', bbox_to_anchor=(1.02, 1), loc='upper left')
        
        # Major ticks for Steps
        ax1.set_xticks(processed_data['x_tick_positions'])
        ax1.set_xticklabels(processed_data['x_tick_labels'], fontsize=12)
        
        # Minor ticks for Ranks
        ax1.set_xticks(processed_data['x_minor_tick_positions'], minor=True)
        ax1.set_xticklabels(processed_data['x_minor_tick_labels'], minor=True, fontsize=8)
        
        ax1.grid(True, which='major', axis='y', linestyle='--', linewidth=0.7)
        ax1.margins(x=0.01) # Add a small margin to the x-axis

    # --- 2. Box Plot (excluding total) ---
    box_data = processed_data['box_plot_data']
    if box_data:
        sorted_ops = sorted(box_data.keys(), key=lambda op: np.median(box_data[op]), reverse=True)
        
        N_TOP_OPS = 10
        top_ops = [op for op in sorted_ops if op in box_data][:N_TOP_OPS]
        plot_data = [box_data[op] for op in top_ops]

        if plot_data:
            bp = ax2.boxplot(plot_data, patch_artist=True, vert=True, whis=[5, 95], showfliers=False)
            ax2.set_xticklabels(top_ops, rotation=25, ha='right', fontsize=12)
            ax2.set_title(f'Distribution of Top {N_TOP_OPS} Operation Timings (All Ranks & Steps)', fontsize=18, weight='bold')
            ax2.set_ylabel('Time (seconds)', fontsize=14)
            ax2.set_yscale('log')
            ax2.grid(True, which='minor', linestyle=':', linewidth=0.5)
            ax2.grid(True, which='major', linestyle='--', linewidth=0.7)
            
            colors = plt.cm.viridis(np.linspace(0, 1, len(plot_data)))
            for patch, color in zip(bp['boxes'], colors):
                patch.set_facecolor(color)

    output_filename = 'ascent_performance_breakdown.png'
    plt.savefig(output_filename, dpi=150, bbox_inches='tight')
    print(f"\nPlot saved to {output_filename}")

    if show_plot:
        # The interactive window might fail silently on some systems. This message will always appear.
        print(f"\nAttempting to open interactive plot window (using backend: {plt.get_backend()})...")
        sys.stdout.flush() 
        plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot Ascent performance timing data from a JSON file.")
    parser.add_argument("json_filepath", help="Path to the JSON timing summary file.")
    parser.add_argument("--show", action="store_true", help="Display the plot interactively in a window.")
    args = parser.parse_args()
    
    # Check for non-interactive backend *before* processing if --show is used.
    if args.show:
        backend = plt.get_backend()
        non_interactive_backends = ['agg', 'pdf', 'svg', 'ps', 'cairo']
        if backend.lower() in non_interactive_backends:
            print(f"\nWarning: Your Matplotlib backend is '{backend}', which is non-interactive.")
            print("The plot window cannot be opened on this system.")
            print("If you are on a remote server, try connecting with 'ssh -X' or 'ssh -Y' to enable X11 forwarding.")
            sys.stdout.flush()
    
    try:
        with open(args.json_filepath, 'r') as f:
            raw_data = json.load(f)
            
        processed_data = process_data_timestep_major(raw_data)

    except FileNotFoundError:
        print(f"Error: File not found at {args.json_filepath}")
        sys.exit(1)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"Error: Could not process JSON from {args.json_filepath}. It may have an unexpected format. Details: {e}")
        sys.exit(1)

    plot_performance(processed_data, args.json_filepath, args.show)

