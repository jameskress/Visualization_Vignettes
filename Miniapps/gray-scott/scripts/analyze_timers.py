import os
import glob
import argparse
import pandas as pd
import warnings
warnings.filterwarnings("ignore", message="Unable to import Axes3D")
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def reduce_and_plot(timer_dir, output_prefix, title_prefix=""):
    files = glob.glob(os.path.join(timer_dir, "*.csv"))
    if not files: return False

    df_list = [pd.read_csv(f) for f in files]
    full_df = pd.concat(df_list, ignore_index=True)
        
    if 'step' not in full_df.columns: return False
        
    # Reduce by taking the MAX across all ranks per step (Critical Path)
    reduced_df = full_df.groupby('step').max().reset_index()

    # Smart column sorting
    skip_cols = ['step', 'rank', 'hostname', 'thread', 'total_step']
    mem_cols = [c for c in reduced_df.columns if any(x in c.lower() for x in ['mem', 'rss', 'hwm', 'vsize', 'bytes'])]
    time_cols = [c for c in reduced_df.columns if c not in skip_cols and c not in mem_cols]

    plt.style.use('ggplot')

    # --- 1. STACKED BAR CHART (Timer Breakdown) ---
    if time_cols:
        fig, ax = plt.subplots(figsize=(10, 6))
        reduced_df.set_index('step')[time_cols].plot(kind='bar', stacked=True, ax=ax, colormap='viridis', edgecolor='black')
        ax.set_title(f"{title_prefix}: Time Breakdown per Step", fontsize=14, fontweight='bold')
        ax.set_ylabel("Time (seconds)", fontsize=12)
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.savefig(f"{output_prefix}_stacked.png", dpi=300, bbox_inches='tight')
        plt.close()

    # --- 2. HEARTBEAT PLOT (Total Step Time Jitter) ---
    total_time = reduced_df['total_step'] if 'total_step' in reduced_df.columns else reduced_df[time_cols].sum(axis=1)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(reduced_df['step'], total_time, marker='o', linestyle='-', color='#e74c3c', linewidth=2)
    ax.set_title(f"{title_prefix}: Heartbeat (Critical Path Time)", fontsize=14, fontweight='bold')
    ax.set_xlabel("Simulation Step", fontsize=12)
    ax.set_ylabel("Total Step Time (s)", fontsize=12)
    ax.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(f"{output_prefix}_heartbeat.png", dpi=300)
    plt.close()

    # --- 3. MEMORY CEILING PLOT (If memory data exists) ---
    if mem_cols:
        fig, ax = plt.subplots(figsize=(10, 4))
        reduced_df.set_index('step')[mem_cols].plot(kind='line', marker='x', ax=ax, linewidth=2)
        ax.set_title(f"{title_prefix}: Memory Ceiling", fontsize=14, fontweight='bold')
        ax.set_xlabel("Simulation Step", fontsize=12)
        ax.set_ylabel("Memory Usage", fontsize=12)
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.savefig(f"{output_prefix}_memory.png", dpi=300, bbox_inches='tight')
        plt.close()

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-prefix", required=True, help="Prefix for the generated plots.")
    parser.add_argument("--title", default="Performance")
    args = parser.parse_args()
    reduce_and_plot(args.input_dir, args.output_prefix, args.title)