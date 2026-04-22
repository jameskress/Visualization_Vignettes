import os
import glob
import argparse
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore", message="Unable to import Axes3D")
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter

def p25(x): return np.nanpercentile(x, 25)
def p75(x): return np.nanpercentile(x, 75)

def reduce_and_plot(timer_dir, output_prefix, title_prefix=""):
    files = glob.glob(os.path.join(timer_dir, "*.csv"))
    if not files: return False

    df_list = [pd.read_csv(f) for f in files]
    full_df = pd.concat(df_list, ignore_index=True)
        
    if 'step' not in full_df.columns: return False
        
    # Apply Shaheen-style exhaustive reduction
    metrics = ['mean', 'min', 'max', p25, p75]
    agg_dict = {col: metrics for col in full_df.columns if col != 'step' and pd.api.types.is_numeric_dtype(full_df[col])}
    
    summary = full_df.groupby('step').agg(agg_dict)
    summary.columns = ['_'.join(col).strip() for col in summary.columns.values]
    summary = summary.reset_index()

    # Before plotting, check if we actually have data
    if summary.empty:
        print(f"!!! WARNING: '{title_prefix}' has no numeric data to plot.")
        print(f"    Check {timer_dir} to see if the simulation actually ran.")
        return False

    # Smart column sorting
    skip_cols = ['step', 'rank', 'hostname', 'thread', 'total_step', 'user_s', 'sys_s', 'elapsed_s']
    mem_cols = [c for c in summary.columns if any(x in c.lower() for x in ['mem', 'rss', 'hwm', 'vsize', 'bytes']) and c.endswith('_max')]
    time_cols = [c for c in summary.columns if c.endswith('_mean') and c.replace('_mean', '') not in skip_cols and not any(m in c.lower() for m in ['mem', 'rss', 'hwm', 'vsize', 'bytes'])]

    plt.style.use('ggplot')
    
    # Create a 3-row, 1-column subplot figure
    fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(12, 16))
    fig.suptitle(f"Performance Profile: {title_prefix}", fontsize=18, fontweight='bold', y=0.98)

    # --- 1. STACKED BAR CHART (Timer Breakdown) ---
    if time_cols:
        ax = axes[0]
        plot_df = summary.fillna(0)
        
        # Separate active work from idle wait time
        idle_col = 'adios_wait_mean'
        # Explicitly filter active_cols to EXCLUDE the idle column
        active_cols = [c for c in time_cols if c != idle_col]
        has_idle = idle_col in plot_df.columns

        # Setup bar positions
        x = np.arange(len(plot_df['step']))
        width = 0.4 if has_idle else 0.8  # Make room for the second bar if idle time exists
        offset = -width/2 if has_idle else 0
        
        # Draw Left Bar: Active Compute (Stacked)
        bottom = np.zeros(len(plot_df))
        cmap = plt.get_cmap('viridis')
        colors = cmap(np.linspace(0, 1, len(active_cols)))
        
        for idx, col in enumerate(active_cols):
            ax.bar(x + offset, plot_df[col], width, label=col.replace('_mean', ''), 
                   bottom=bottom, color=colors[idx], edgecolor='black')
            bottom += plot_df[col]
            
        # Draw Right Bar: Idle Wait Time
        if has_idle:
            ax.bar(x + width/2, plot_df['adios_wait_mean'], width, label='adios_wait (Idle)', 
                   color='lightgray', hatch='///', edgecolor='black')
            
        ax.set_title("Time Breakdown: Active Compute vs Idle Wait", fontsize=14, fontweight='bold')
        ax.set_ylabel("Time (seconds)", fontsize=12)
        ax.set_xticks(x)
        ax.set_xticklabels(plot_df['step'].astype(int))
        
        ax.legend(bbox_to_anchor=(1.01, 1), loc='upper left')

    # --- 2. HEARTBEAT PLOT (Total Step Time Jitter) ---
    if 'total_step_mean' in summary.columns:
        ax = axes[1]
        
        # Add the Shaheen-style 25-75% quartile shading
        ax.fill_between(summary['step'], summary['total_step_p25'], summary['total_step_p75'], 
                        alpha=0.3, color='#e74c3c', label='25%-75% Quartiles')
        
        # Plot the mean line
        ax.plot(summary['step'], summary['total_step_mean'], marker='o', linestyle='-', color='#e74c3c', linewidth=2, label='Mean Time')
        
        ax.set_title("Heartbeat (Step Compute Consistency)", fontsize=14, fontweight='bold')
        ax.set_ylabel("Total Step Time (s)", fontsize=12)
        ax.grid(True, which="both", ls="--", alpha=0.5)
        
        # Force Y-axis to start at 0 and pad the top
        ax.set_ylim(bottom=0, top=summary['total_step_mean'].max() * 1.20)
        ax.legend(loc='upper right')

    # --- 3. MEMORY CEILING PLOT (If memory data exists) ---
    if mem_cols:
        ax = axes[2]
        summary.set_index('step')[mem_cols].plot(kind='line', marker='x', ax=ax, linewidth=2, colormap='coolwarm')
        ax.set_title("Memory Ceiling (Peak footprint across all ranks)", fontsize=14, fontweight='bold')
        ax.set_xlabel("Simulation Step", fontsize=12)
        ax.set_ylabel("Memory Usage", fontsize=12)
        
        # Clean up the legend labels (remove the '_max' suffix)
        handles, labels = ax.get_legend_handles_labels()
        clean_labels = [l.replace('_max', '') for l in labels]
        ax.legend(handles, clean_labels, bbox_to_anchor=(1.01, 1), loc='upper left')

    # Adjust layout to fit everything and save as a single PDF
    plt.tight_layout(rect=[0, 0, 0.95, 0.96])
    pdf_path = f"{output_prefix}_profile.pdf"
    plt.savefig(pdf_path, dpi=300, bbox_inches='tight')
    plt.close()

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-prefix", required=True, help="Prefix for the generated plots.")
    parser.add_argument("--title", default="Performance")
    args = parser.parse_args()
    reduce_and_plot(args.input_dir, args.output_prefix, args.title)