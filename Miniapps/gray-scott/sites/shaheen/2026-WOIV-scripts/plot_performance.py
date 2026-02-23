import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import ScalarFormatter

# ---------------------------------------------------------
# 1. Load the summarized data
# ---------------------------------------------------------
runs = {
    "Baseline": "summary_baseline.csv", 
    "ADIOS (Data)": "summary_adios_data.csv",
    "Ascent (Data)": "summary_ascent_data.csv",
    "Ascent (Render)": "summary_ascent_render.csv",
    "Catalyst (Data)": "summary_catalyst_data.csv",
    "Catalyst (Render)": "summary_catalyst_render.csv"
}

# Define a clean color palette for the 6 runs
colors = {
    "Baseline": "#808080",           # Grey
    "ADIOS (Data)": "#d62728",       # Red
    "Ascent (Data)": "#98df8a",      # Light Green
    "Ascent (Render)": "#2ca02c",    # Dark Green
    "Catalyst (Data)": "#aec7e8",    # Light Blue
    "Catalyst (Render)": "#1f77b4"   # Dark Blue
}

dataframes = {}
for name, file_path in runs.items():
    try:
        dataframes[name] = pd.read_csv(file_path, index_col='step')
    except FileNotFoundError:
        print(f"Warning: '{file_path}' not found. Skipping {name} in plots.")

if not dataframes:
    print("No summary files loaded. Please run reduce_timers.py first.")
    exit()

# ---------------------------------------------------------
# 2. Print Key Statistics for the Paper
# ---------------------------------------------------------
print("\n=== PUBLICATION STATISTICS ===")
for name, df in dataframes.items():
    total_init = df['init_writer_mean'].sum() 
    total_open = df['writer_open_mean'].sum()
    peak_memory = df['rss_MB_max'].max()
    total_compute = df['compute_step_mean'].sum()
    total_io = df['write_step_mean'].sum()
    total_step = df['total_step_mean'].sum()
    
    print(f"\n[{name}]")
    print(f"  Peak Memory     : {peak_memory:.2f} MB per rank")
    print(f"  Total Compute   : {total_compute:.2f} seconds")
    print(f"  Init Writer     : {total_init:.4f} seconds")
    print(f"  Writer Open     : {total_open:.4f} seconds")
    print(f"  Write/Render    : {total_io:.2f} seconds")
    print(f"  Total Step Time : {total_step:.2f} seconds")

# ---------------------------------------------------------
# 3. Figure 1: The Heartbeat Plot (Subplots per Run)
# ---------------------------------------------------------
num_plots = len(dataframes)
# Dynamically scale the height of the figure based on how many runs we have
fig, axes = plt.subplots(nrows=num_plots, ncols=1, figsize=(12, 2 * num_plots), sharex=True)

# If there is only one plot, wrap it in a list so we can iterate over it
if num_plots == 1:
    axes = [axes]

for ax, (name, df) in zip(axes, dataframes.items()):
    c = colors[name]
    
    # Plot the 25%-75% quartile envelope
    ax.fill_between(df.index, 
                     df['total_step_p25'], 
                     df['total_step_p75'], 
                     alpha=0.4, color=c, label='25%-75% Quartiles')
    
    # Plot Mean Line
    linestyle = '--' if name == "Baseline" else '-'
    linewidth = 2.0 if name == "Baseline" else 1.5
    ax.plot(df.index, df['total_step_mean'], color=c, linestyle=linestyle, linewidth=linewidth, label=f'Mean Time')

    # Formatting per subplot
    ax.set_ylabel('Time (s)', fontsize=10)
    ax.set_title(name, fontsize=12, fontweight='bold', loc='left', pad=3)
    ax.grid(True, which="both", ls="--", alpha=0.5)
    
    # Remove scientific notation from the Y-axis
    formatter = ScalarFormatter()
    formatter.set_scientific(False)
    ax.yaxis.set_major_formatter(formatter)
    
    # Only add the legend to the first plot to save space
    if ax == axes[0]:
        ax.legend(loc='upper right', fontsize=10)

# Set the overall X-axis label on the bottom plot only
axes[-1].set_xlabel('Simulation Step', fontsize=12)

# Overall Title
fig.suptitle('In-Situ Execution Heartbeat (64 Nodes / 3072 Cores)', fontsize=16, fontweight='bold', y=1.02)
plt.tight_layout()

plt.savefig("fig_heartbeat_plot.png", dpi=300, bbox_inches='tight')
print("\nSaved heartbeat plot to 'fig_heartbeat_plot.png'")

# ---------------------------------------------------------
# 4. Figure 2: Detailed Stacked Bar Chart (Amortized Overhead)
# ---------------------------------------------------------
plt.figure(figsize=(10, 6))

names = list(dataframes.keys())

# Extract every specific timer category (Sums represent TOTAL time over the entire run)
compute_times = [dataframes[n]['compute_step_mean'].sum() for n in names]
init_times    = [dataframes[n]['init_writer_mean'].sum() for n in names]
open_times    = [dataframes[n]['writer_open_mean'].sum() for n in names]
write_times   = [dataframes[n]['write_step_mean'].sum() for n in names]
total_times   = [dataframes[n]['total_step_mean'].sum() for n in names]

# Calculate untracked simulation overhead (MPI ghost cells, boundaries, etc)
other_times = [tot - (comp + ini + opn + wrt) for tot, comp, ini, opn, wrt in zip(total_times, compute_times, init_times, open_times, write_times)]
other_times = [max(0, val) for val in other_times] # Ensure no floating-point negatives

bar_width = 0.6
x_pos = np.arange(len(names))

# Plot Layer 1: Compute (Bottom)
p1 = plt.bar(x_pos, compute_times, width=bar_width, color='#D3D3D3', edgecolor='black', label='Simulation Compute')

# Plot Layer 2: Untracked Simulation Overhead (MPI Sync)
b_other = compute_times
p2 = plt.bar(x_pos, other_times, bottom=b_other, width=bar_width, color='#A9A9A9', edgecolor='black', label='MPI Sync & Ghost Cells')

# Plot Layer 3: Init Writer
b_init = np.add(b_other, other_times)
p3 = plt.bar(x_pos, init_times, bottom=b_init, width=bar_width, color='#FFDAB9', edgecolor='black', label='Init Writer')

# Plot Layer 4: Writer Open
b_open = np.add(b_init, init_times)
p4 = plt.bar(x_pos, open_times, bottom=b_open, width=bar_width, color='#FFA07A', edgecolor='black', label='Writer Open')

# Plot Layer 5: Write/Render (Top)
b_write = np.add(b_open, open_times)
p5 = plt.bar(x_pos, write_times, bottom=b_write, width=bar_width, color='#4682B4', edgecolor='black', label='Write / Render')

# Formatting - Explicitly labeled as "Total Accumulated Time"
plt.ylabel('Total Accumulated Time For Full Run (seconds)', fontsize=12)
plt.title('Total Execution Time Breakdown (Sum of All Steps)', fontsize=14, fontweight='bold')
plt.xticks(x_pos, names, fontsize=11, rotation=15, ha='right')

# Place legend outside the plot area
plt.legend(loc='upper left', bbox_to_anchor=(1.02, 1), fontsize=11)

plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()

plt.savefig("fig_overhead_stacked_bar.png", dpi=300, bbox_inches='tight')
print("Saved detailed stacked bar chart to 'fig_overhead_stacked_bar.png'")
