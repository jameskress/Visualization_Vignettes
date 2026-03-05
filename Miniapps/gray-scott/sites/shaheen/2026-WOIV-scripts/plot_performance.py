import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import ScalarFormatter

# ---------------------------------------------------------
# HPC PERFORMANCE TUNING (Add these to your SLURM script)
# ---------------------------------------------------------
# export FI_CXI_RX_MATCH_MODE=hybrid      # Prevents hardware queue exhaustion
# export FI_CXI_RDZV_THRESHOLD=16384      # Optimizes small vs large message handling
# export MPICH_OFI_CXI_COUNTER_REPORT=2   # Provides detailed timeout diagnostics
# ---------------------------------------------------------

# SETTINGS FOR THE PAPER
STEADY_STATE_START = 65021  # Start at step 65021 to ensure all init is complete
NORMALIZE_X_AXIS = True      # Align all runs to start at "Step 0" (Steps since restart)

# ---------------------------------------------------------
# 1. Load the summarized data
# ---------------------------------------------------------
runs = {
    "Baseline": "summary_baseline.csv", 
    "ADIOS (Data)": "summary_adios_data.csv",
    "Ascent (Data)": "summary_ascent_data.csv",
    "Ascent (Render)": "summary_ascent_render.csv",
    "Ascent (In Transit)": "summary_ascent_intransit_render.csv",
    "Catalyst (Data)": "summary_catalyst_data.csv",
    "Catalyst (Render)": "summary_catalyst_render.csv",
    "Catalyst (In Transit)": "summary_catalyst_intransit_render.csv",
    "Kombyne (Data)": "summary_kombyne_data.csv",
    "Kombyne (Render)": "summary_kombyne_render.csv"
}

# Define a clean color palette for the 10 runs
# Ascent family uses greens, Catalyst family uses blues
colors = {
    "Baseline": "#808080",              # Grey
    "ADIOS (Data)": "#d62728",          # Red
    "Ascent (Data)": "#a1d99b",         # Light Green
    "Ascent (Render)": "#41ab5d",       # Medium Green
    "Ascent (In Transit)": "#006d2c",   # Dark Green
    "Catalyst (Data)": "#9ecae1",       # Light Blue
    "Catalyst (Render)": "#4292c6",     # Medium Blue
    "Catalyst (In Transit)": "#084594",  # Dark Blue
    "Kombyne (Data)": "#fccde5",        # Light Purple/Pink
    "Kombyne (Render)": "#bc80bd"       # Medium Purple
}

labels = {
    "Baseline": "Baseline",
    "ADIOS (Data)": "ADIOS (Data)",
    "Ascent (Data)": "Ascent (Data)",
    "Ascent (Render)": "Ascent (Render)",
    "Ascent (In Transit)": "Ascent (In Transit)",
    "Catalyst (Data)": "Catalyst (Data)",
    "Catalyst (Render)": "Catalyst (Render)",
    "Catalyst (In Transit)": "Catalyst (In Transit)",
    "Kombyne (Data)": "Kombyne (Data)",
    "Kombyne (Render)": "Kombyne (Render)"
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
print("\n=== PUBLICATION STATISTICS (TOTAL ACCUMULATED TIME) ===")
for name, df in dataframes.items():
    print(f"\n[{name}]")
    
    # Memory (Peak across the run)
    mem_mean = df['rss_MB_mean'].max()
    mem_min = df['rss_MB_min'].max()
    mem_max = df['rss_MB_max'].max()
    print(f"  Peak Memory (MB) : Mean: {mem_mean:.2f} | Min: {mem_min:.2f} | Max: {mem_max:.2f}")
    
    # Compute
    comp_mean = df['compute_step_mean'].sum()
    comp_min = df['compute_step_min'].sum()
    comp_max = df['compute_step_max'].sum()
    print(f"  Total Compute (s): Mean: {comp_mean:.2f} | Lower Bound: {comp_min:.2f} | Upper Bound: {comp_max:.2f}")

    # Write/Render
    write_mean = df['write_step_mean'].sum()
    write_min = df['write_step_min'].sum()
    write_max = df['write_step_max'].sum()
    print(f"  Write/Render (s) : Mean: {write_mean:.2f} | Lower Bound: {write_min:.2f} | Upper Bound: {write_max:.2f}")

    # Total Step
    tot_mean = df['total_step_mean'].sum()
    tot_min = df['total_step_min'].sum()
    tot_max = df['total_step_max'].sum()
    print(f"  Total Step (s)   : Mean: {tot_mean:.2f} | Lower Bound: {tot_min:.2f} | Upper Bound: {tot_max:.2f}")


# ---------------------------------------------------------
# 3. Figure 1: The Heartbeat Plot (3-Column Layout, Frameworks by Row)
# ---------------------------------------------------------
# Reorganized to populate row-by-row:
# Row 1: All Ascent
# Row 2: All Catalyst
# Row 3: Kombyne + ADIOS (Baseline removed as requested)
heartbeat_layout = [
    "Ascent (Data)",       "Ascent (Render)",       "Ascent (In Transit)",
    "Catalyst (Data)",     "Catalyst (Render)",     "Catalyst (In Transit)",
    "Kombyne (Data)",      "Kombyne (Render)",      "ADIOS (Data)"
]

# Only plot if the data exists
loaded_hb_names = [name for name in heartbeat_layout if name in dataframes]

ncols = 3
nrows = (len(loaded_hb_names) + ncols - 1) // ncols

fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(18, 3.5 * nrows), sharex=True)
axes = np.atleast_1d(axes).flatten()

for i, name in enumerate(loaded_hb_names):
    df = dataframes[name]
    ax = axes[i]
    c = colors.get(name, '#333333')
    
    # Filter to show only steady state
    df_plot = df[df.index >= STEADY_STATE_START]
    if df_plot.empty: df_plot = df
    
    # Normalize X-axis
    plot_index = df_plot.index
    if NORMALIZE_X_AXIS:
        plot_index = df_plot.index - df.index.min()

    ax.fill_between(plot_index, 
                     df_plot['total_step_p25'], 
                     df_plot['total_step_p75'], 
                     alpha=0.3, color=c, label='25%-75% Quartiles')
    
    ax.plot(plot_index, df_plot['total_step_mean'], color=c, linestyle='-', linewidth=1.5, label='Mean Time')

    ax.set_ylabel('Time (s)', fontsize=10)
    ax.set_title(name, fontsize=12, fontweight='bold', loc='left', pad=3)
    ax.grid(True, which="both", ls="--", alpha=0.5)
    
    # Consistent 20% Y-padding
    ax.set_ylim(bottom=0, top=df_plot['total_step_mean'].max() * 1.20)
    
    formatter = ScalarFormatter()
    formatter.set_scientific(False)
    ax.yaxis.set_major_formatter(formatter)
    ax.legend(loc='upper right', fontsize=8)

# Clean up unused subplots
for i in range(len(loaded_hb_names), len(axes)):
    fig.delaxes(axes[i])

# Set x-labels for the bottom row
for i in range(len(loaded_hb_names)):
    if i >= len(loaded_hb_names) - ncols:
        axes[i].set_xlabel('Steps Since Restart', fontsize=12)

fig.suptitle('Steady-State Execution Heartbeat (excluding initialization)', 
             fontsize=16, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig("fig_heartbeat_plot.png", dpi=300, bbox_inches='tight')

# ---------------------------------------------------------
# 4. Figure 2: Detailed Stacked Bar Chart (Total Overhead)
# ---------------------------------------------------------
plt.figure(figsize=(12, 8)) 
names = list(dataframes.keys())

compute_times = [dataframes[n]['compute_step_mean'].sum() for n in names]
init_times    = [dataframes[n]['init_writer_mean'].sum() for n in names]
open_times    = [dataframes[n]['writer_open_mean'].sum() for n in names]
write_times   = [dataframes[n]['write_step_mean'].sum() for n in names]
total_times   = [dataframes[n]['total_step_mean'].sum() for n in names]

raw_gaps = [tot - (comp + ini + opn + wrt) for tot, comp, ini, opn, wrt in zip(total_times, compute_times, init_times, open_times, write_times)]
raw_gaps = [max(0, val) for val in raw_gaps]

baseline_idx = names.index("Baseline") if "Baseline" in names else 0
baseline_gap = raw_gaps[baseline_idx]

sim_overhead_times = [min(baseline_gap, g) for g in raw_gaps]
implicit_io_times  = [max(0, g - baseline_gap) for g in raw_gaps]

bar_width = 0.8
x_pos = np.arange(len(names))

plt.bar(x_pos, compute_times, width=bar_width, color='#D3D3D3', edgecolor='black', label='Simulation Compute', zorder=3)
b_sim = compute_times
plt.bar(x_pos, sim_overhead_times, bottom=b_sim, width=bar_width, color='#A9A9A9', edgecolor='black', label='Baseline Sim Overhead (MPI)', zorder=3)
b_implicit = np.add(b_sim, sim_overhead_times)
plt.bar(x_pos, implicit_io_times, bottom=b_implicit, width=bar_width, color='#87CEEB', edgecolor='black', label='Implicit In-Situ Contention', zorder=3)
b_init = np.add(b_implicit, implicit_io_times)
plt.bar(x_pos, init_times, bottom=b_init, width=bar_width, color='#FFDAB9', edgecolor='black', label='Init Writer', zorder=3)
b_open = np.add(b_init, init_times)
plt.bar(x_pos, open_times, bottom=b_open, width=bar_width, color='#FFA07A', edgecolor='black', label='Writer Open', zorder=3)
b_write = np.add(b_open, open_times)
plt.bar(x_pos, write_times, bottom=b_write, width=bar_width, color='#4682B4', edgecolor='black', label='Write / Render', zorder=3)

stack_totals = np.add(b_write, write_times)
for i, total in enumerate(stack_totals):
    label = f"{total:.1f}s"
    if "Kombyne" in names[i]: label += "*"
    plt.text(x_pos[i], total + (max(stack_totals) * 0.015), label, ha='center', va='bottom', fontweight='bold', fontsize=11, zorder=4)

plt.ylabel('Total Accumulated Time (seconds)', fontsize=12)
plt.title('Total Execution Time Breakdown (Sum of All Steps)', fontsize=14, fontweight='bold')
plt.xticks(x_pos, names, fontsize=10, rotation=25, ha='right')
plt.ylim(0, max(stack_totals) * 1.12)
plt.legend(loc='upper left', fontsize=10, framealpha=0.9, edgecolor='black').set_zorder(5)
plt.grid(axis='y', linestyle='--', alpha=0.7, zorder=0)

if any("Kombyne" in n for n in names):
    plt.figtext(0.1, 0.02, "* Note: Kombyne runs executed on 1024 procs (32 nodes) vs. 4096 procs (64 nodes) for other runs.", 
                ha="left", fontsize=9, style='italic')

plt.tight_layout(rect=[0, 0.05, 1, 1])
plt.savefig("fig_overhead_stacked_bar.png", dpi=300, bbox_inches='tight')

print("Final publication figures generated.")
