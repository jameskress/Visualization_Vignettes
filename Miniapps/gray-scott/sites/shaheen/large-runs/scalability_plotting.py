import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import ScalarFormatter

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
STRONG_NODES = [256, 1024, 4096]
WEAK_NODES   = [8, 64, 512, 4096]
TYPES        = ["baseline", "adios_data", "ascent_data", "ascent_render", "catalyst_data", "catalyst_render"]

# --- NEW: Transit Definitions ---
# Standard runs for the In-situ vs Transit bar chart
TRANSIT_STANDARD = [
    ("Small", 64, "small_N0064"),
    ("Compressed", 512, "compressed_N0512"),
    ("Hero", 4096, "hero_N4096")
]

# The "Carte Blanche" Sweep for the sweet-spot curve
TRANSIT_SWEEPS = [
    (64, "sweep_64_N4096_S064"),
    (128, "sweep_128_N4096_S128"),
    (256, "sweep_256_N4096_S256"),
    (384, "sweep_384_N4096_S384")
]

# Visual Settings
STEADY_STATE_START = 65021
NORMALIZE_X_AXIS = True

colors = {
    "baseline": "#808080",
    "adios_data": "#d62728",
    "ascent_data": "#98df8a",
    "ascent_render": "#2ca02c",
    "catalyst_data": "#aec7e8",
    "catalyst_render": "#1f77b4",
    # Added darker shades for transit bars
    "adios_transit": "#8b0000",
    "ascent_transit": "#006400",
    "catalyst_transit": "#00008b"
}

labels = {
    "baseline": "Baseline",
    "adios_data": "ADIOS (Data)",
    "ascent_data": "Ascent (Data)",
    "ascent_render": "Ascent (Render)",
    "catalyst_data": "Catalyst (Data)",
    "catalyst_render": "Catalyst (Render)"
}

def get_run_data(filename):
    """Loads a summary CSV and returns the dataframe if successful."""
    try:
        return pd.read_csv(filename)
    except:
        return None

def print_publication_stats(name, df):
    """Prints exhaustive statistics for the paper."""
    print(f"\n[{name}]")
    mem_mean = df['rss_MB_mean'].max()
    print(f"  Peak Memory (MB) : Mean: {mem_mean:.2f}")
    comp_mean = df['compute_step_mean'].sum()
    print(f"  Total Compute (s): Mean: {comp_mean:.2f}")
    write_mean = df['write_step_mean'].sum()
    print(f"  Write/Render (s) : Mean: {write_mean:.2f}")
    tot_mean = df['total_step_mean'].sum()
    print(f"  Total Step (s)   : Mean: {tot_mean:.2f}")

# ---------------------------------------------------------
# 1. Print Publication Stats for All Found Runs
# ---------------------------------------------------------
print("\n=== PAPER 2 PUBLICATION STATISTICS (ACCUMULATED TIME) ===")

for t in TYPES:
    for n in STRONG_NODES:
        fname = f"summary_strong_N{n:04d}_{t}.csv"
        df = get_run_data(fname)
        if df is not None:
            print_publication_stats(f"Strong Scaling: N={n} {labels[t]}", df)

for scale_name, n, prefix in TRANSIT_STANDARD:
    for t in ["adios_data", "ascent_render", "catalyst_render"]:
        fname = f"summary_transit_{prefix}_{t}.csv"
        df = get_run_data(fname)
        if df is not None:
            print_publication_stats(f"Transit ({scale_name}): N={n} {labels[t]}", df)

print("\n" + "="*60 + "\nGenerating Figures...")

# ---------------------------------------------------------
# 2. Strong Scaling (Time and Speedup)
# ---------------------------------------------------------
fig_time, ax_time = plt.subplots(figsize=(10, 6))
fig_speed, ax_speed = plt.subplots(figsize=(10, 6))

for t in TYPES:
    times, nodes = [], []
    for n in STRONG_NODES:
        df = get_run_data(f"summary_strong_N{n:04d}_{t}.csv")
        if df is not None:
            times.append(df['total_step_mean'].sum())
            nodes.append(n)
    if times:
        ax_time.plot(nodes, times, 'o-', label=labels[t], color=colors[t], linewidth=2)
        speedup = [times[0] / t_n for t_n in times]
        ax_speed.plot(nodes, speedup, 'o-', label=labels[t], color=colors[t], linewidth=2)

ax_speed.plot(STRONG_NODES, [n/STRONG_NODES[0] for n in STRONG_NODES], '--', color='black', label='Ideal Speedup', alpha=0.5)

for ax, title, ylabel in [(ax_time, 'Strong Scaling: Execution Time', 'Total Execution Time (s)'),
                          (ax_speed, 'Strong Scaling: Speedup', f'Speedup (T_{STRONG_NODES[0]} / T_N)')]:
    ax.set_xscale('log', base=2)
    ax.set_yscale('log', base=2)
    ax.set_xlabel('Number of Nodes (N)', fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, which="both", ls="--", alpha=0.5)

fig_time.savefig("paper2_strong_time.png", dpi=300)
fig_speed.savefig("paper2_strong_speedup.png", dpi=300)

# ---------------------------------------------------------
# 3. Weak Scaling (Time and Efficiency)
# ---------------------------------------------------------
fig_wtime, ax_wtime = plt.subplots(figsize=(10, 6))
fig_eff, ax_eff = plt.subplots(figsize=(10, 6))
max_eff = 1.1

for t in TYPES:
    times, nodes = [], []
    for n in WEAK_NODES:
        df = get_run_data(f"summary_weak_N{n:04d}_{t}.csv")
        if df is not None:
            times.append(df['total_step_mean'].sum())
            nodes.append(n)
    if times:
        ax_wtime.plot(nodes, times, 's-', label=labels[t], color=colors[t], linewidth=2)
        efficiency = [times[0] / t_n for t_n in times]
        max_eff = max(max_eff, max(efficiency))
        ax_eff.plot(nodes, efficiency, 's-', label=labels[t], color=colors[t], linewidth=2)

ax_eff.axhline(y=1.0, color='black', linestyle='--', alpha=0.5, label='Ideal Efficiency')
ax_eff.set_ylim(0, max_eff * 1.1)

for ax, title, ylabel in [(ax_wtime, 'Weak Scaling: Execution Time', 'Total Execution Time (s)'),
                          (ax_eff, 'Weak Scaling: Efficiency', f'Efficiency (T_{WEAK_NODES[0]} / T_N)')]:
    ax.set_xscale('log', base=8)
    ax.set_xlabel('Number of Nodes (N)', fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, which="both", ls="--", alpha=0.5)

fig_wtime.savefig("paper2_weak_time.png", dpi=300)
fig_eff.savefig("paper2_weak_efficiency.png", dpi=300)

# ---------------------------------------------------------
# 4. Heartbeat Plot (Focus on N=4096 Strong Scaling)
# ---------------------------------------------------------
loaded_heartbeats = []
for t in TYPES:
    df = get_run_data(f"summary_strong_N4096_{t}.csv")
    if df is not None:
        loaded_heartbeats.append((t, df))

if loaded_heartbeats:
    num_hb = len(loaded_heartbeats)
    fig_hb, axes_hb = plt.subplots(nrows=(num_hb+1)//2, ncols=2, figsize=(14, 3 * ((num_hb+1)//2)), sharex=True)
    axes_hb = axes_hb.flatten()
    
    for i, (t, df) in enumerate(loaded_heartbeats):
        ax = axes_hb[i]
        df_plot = df[df.index >= STEADY_STATE_START]
        if df_plot.empty: df_plot = df
        
        idx = df_plot.index - df.index.min() if NORMALIZE_X_AXIS else df_plot.index
        
        ax.fill_between(idx, df_plot['total_step_p25'], df_plot['total_step_p75'], alpha=0.3, color=colors[t])
        ax.plot(idx, df_plot['total_step_mean'], color=colors[t], label=labels[t])
        ax.set_title(f"{labels[t]} (N=4096)", loc='left', fontsize=10, fontweight='bold')
        ax.set_ylim(bottom=0, top=df_plot['total_step_mean'].max() * 1.2)
        ax.grid(True, ls="--", alpha=0.4)
    
    fig_hb.suptitle('N=4096 Steady-State Heartbeat (excluding initialization)', fontsize=14, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    fig_hb.savefig("paper2_heartbeat_N4096.png", dpi=300)

# ---------------------------------------------------------
# 5. Overhead Stacked Bar (Strong Scaling Comparison)
# ---------------------------------------------------------
plt.figure(figsize=(12, 7))
bar_names = []
comp_stack, base_stack, situ_stack, write_stack = [], [], [], []

for t in TYPES:
    for n in STRONG_NODES:
        df = get_run_data(f"summary_strong_N{n:04d}_{t}.csv")
        if df is not None:
            bar_names.append(f"{labels[t]}\nN={n}")
            c = df['compute_step_mean'].sum()
            w = df['write_step_mean'].sum()
            total = df['total_step_mean'].sum()
            
            ref_df = get_run_data(f"summary_strong_N256_baseline.csv")
            base_mpi = (ref_df['total_step_mean'].sum() - ref_df['compute_step_mean'].sum()) if ref_df is not None else 0
            
            comp_stack.append(c)
            base_stack.append(base_mpi)
            situ_stack.append(max(0, total - c - w - base_mpi))
            write_stack.append(w)

if bar_names:
    x = np.arange(len(bar_names))
    width = 0.7
    plt.bar(x, comp_stack, width, label='Compute', color='#D3D3D3', edgecolor='black')
    plt.bar(x, base_stack, width, bottom=comp_stack, label='Baseline MPI', color='#A9A9A9', edgecolor='black')
    plt.bar(x, situ_stack, width, bottom=np.array(comp_stack)+np.array(base_stack), label='In-Situ Contention', color='#87CEEB', edgecolor='black')
    plt.bar(x, write_stack, width, bottom=np.array(comp_stack)+np.array(base_stack)+np.array(situ_stack), label='Write/Render', color='#4682B4', edgecolor='black')
    
    plt.xticks(x, bar_names, rotation=45, ha='right', fontsize=9)
    plt.ylabel('Total Time (s)')
    plt.title('Strong Scaling Overhead Breakdown', fontweight='bold')
    plt.legend(loc='upper left', bbox_to_anchor=(1, 1))
    plt.tight_layout()
    plt.savefig("paper2_overhead_scaling.png", dpi=300)

# ---------------------------------------------------------
# 6. In-Situ vs. In-Transit Comparison Bar Chart
# ---------------------------------------------------------
fig_trans, ax_trans = plt.subplots(figsize=(12, 6))

group_labels = []
situ_ascent, transit_ascent = [], []
situ_catalyst, transit_catalyst = [], []
situ_adios, transit_adios = [], []

for scale_name, n, prefix in TRANSIT_STANDARD:
    group_labels.append(f"{scale_name}\n(N={n})")
    
    prefix_situ = f"summary_strong_N{n:04d}" if n in STRONG_NODES else f"summary_weak_N{n:04d}"
    
    def get_tot(fname):
        df = get_run_data(fname)
        return df['total_step_mean'].sum() if df is not None else 0
        
    situ_ascent.append(get_tot(f"{prefix_situ}_ascent_render.csv"))
    transit_ascent.append(get_tot(f"summary_transit_{prefix}_ascent_render.csv"))
    
    situ_catalyst.append(get_tot(f"{prefix_situ}_catalyst_render.csv"))
    transit_catalyst.append(get_tot(f"summary_transit_{prefix}_catalyst_render.csv"))
    
    situ_adios.append(get_tot(f"{prefix_situ}_adios_data.csv"))
    transit_adios.append(get_tot(f"summary_transit_{prefix}_adios_data.csv"))

if any(transit_ascent) or any(transit_catalyst) or any(transit_adios):
    x = np.arange(len(group_labels))
    width = 0.12  

    ax_trans.bar(x - 2.5*width, situ_ascent, width, label='In-Situ Ascent', color=colors['ascent_render'])
    ax_trans.bar(x - 1.5*width, transit_ascent, width, label='In-Transit Ascent', color=colors['ascent_transit'], hatch='//')

    ax_trans.bar(x - 0.5*width, situ_catalyst, width, label='In-Situ Catalyst', color=colors['catalyst_render'])
    ax_trans.bar(x + 0.5*width, transit_catalyst, width, label='In-Transit Catalyst', color=colors['catalyst_transit'], hatch='//')

    ax_trans.bar(x + 1.5*width, situ_adios, width, label='In-Situ ADIOS', color=colors['adios_data'])
    ax_trans.bar(x + 2.5*width, transit_adios, width, label='In-Transit ADIOS', color=colors['adios_transit'], hatch='//')

    ax_trans.set_ylabel('Total Execution Time (s)', fontsize=12)
    ax_trans.set_title('In-Situ vs. In-Transit Workflow Performance', fontsize=14, fontweight='bold')
    ax_trans.set_xticks(x)
    ax_trans.set_xticklabels(group_labels, fontsize=11)
    ax_trans.legend(loc='upper left', bbox_to_anchor=(1.05, 1))
    ax_trans.grid(True, axis='y', ls="--", alpha=0.5)

    plt.tight_layout()
    fig_trans.savefig("paper2_transit_comparison.png", bbox_inches="tight", dpi=300)


# ---------------------------------------------------------
# 7. NEW: In-Transit Staging Sweep Curve
# ---------------------------------------------------------
fig_sweep, ax_sweep = plt.subplots(figsize=(10, 6))
sweep_plotted = False

for t in ["adios_data", "ascent_render", "catalyst_render"]:
    times = []
    valid_nodes = []
    for stage_nodes, sweep_prefix in TRANSIT_SWEEPS:
        fname = f"summary_transit_{sweep_prefix}_{t}.csv"
        df = get_run_data(fname)
        if df is not None:
            times.append(df['total_step_mean'].sum())
            valid_nodes.append(stage_nodes)
            
    if times:
        sweep_plotted = True
        ax_sweep.plot(valid_nodes, times, 'o-', label=labels[t], color=colors.get(t, "black"), linewidth=2.5, markersize=8)

if sweep_plotted:
    ax_sweep.set_xlabel('Number of Staging Nodes (Ratio vs 4096 Sim Nodes)', fontsize=12)
    ax_sweep.set_ylabel('Total Execution Time (s)', fontsize=12)
    ax_sweep.set_title('N=4096 In-Transit Resource Sweet-Spot', fontsize=14, fontweight='bold')
    ax_sweep.set_xticks([64, 128, 256, 384])
    ax_sweep.set_xticklabels(['64\n(64:1)', '128\n(32:1)', '256\n(16:1)', '384\n(~10:1)'])
    ax_sweep.grid(True, which="major", ls="--", alpha=0.6)
    ax_sweep.legend()
    
    plt.tight_layout()
    fig_sweep.savefig("paper2_transit_sweep_curve.png", dpi=300)

print("All scalability, heartbeat, overhead, and sweep figures generated.")
