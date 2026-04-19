import os
import glob
import argparse
import pandas as pd
import warnings
warnings.filterwarnings("ignore", message="Unable to import Axes3D")
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def build_master_plots(test_dir, output_prefix):
    tests = sorted([d for d in os.listdir(test_dir) if os.path.isdir(os.path.join(test_dir, d)) and d != "performance_summary_plots"])
    
    results_time = []
    results_mem = []
    
    for test in tests:
        test_path = os.path.join(test_dir, test)
        sim_t, analysis_t = 0.0, 0.0
        sim_m, analysis_m = 0.0, 0.0
        
        # Parse Simulation
        w_files = glob.glob(os.path.join(test_path, "writer_timers", "*.csv"))
        if w_files:
            df = pd.concat([pd.read_csv(f) for f in w_files], ignore_index=True).groupby('step').max().reset_index()
            if len(df) > 1: df = df[df['step'] > 0] # Drop step 0 spike
            if 'total_step' in df.columns: sim_t = df['total_step'].mean()
            
            mem_cols = [c for c in df.columns if any(x in c.lower() for x in ['mem', 'rss', 'hwm'])]
            if mem_cols: sim_m = df[mem_cols].max().max() # Absolute peak memory

        # Parse Analysis
        r_files = glob.glob(os.path.join(test_path, "reader_timers", "*.csv"))
        if r_files:
            df = pd.concat([pd.read_csv(f) for f in r_files], ignore_index=True).groupby('step').max().reset_index()
            if len(df) > 1: df = df[df['step'] > 0]
            if 'total_step' in df.columns: analysis_t = df['total_step'].mean()
            
            mem_cols = [c for c in df.columns if any(x in c.lower() for x in ['mem', 'rss', 'hwm'])]
            if mem_cols: analysis_m = df[mem_cols].max().max()

        if sim_t > 0 or analysis_t > 0:
            results_time.append({"Test": test, "Simulation (s)": sim_t, "Analysis (s)": analysis_t})
        if sim_m > 0 or analysis_m > 0:
            results_mem.append({"Test": test, "Simulation Peak Mem": sim_m, "Analysis Peak Mem": analysis_m})

    # Plot Master Time
    if results_time:
        df_t = pd.DataFrame(results_time).set_index("Test")
        fig, ax = plt.subplots(figsize=(16, 8))
        df_t.plot(kind='bar', ax=ax, colormap='Set1', edgecolor='black', width=0.8)
        ax.set_title("Master Performance: Average Time per Step (Excluding Step 0)", fontsize=16, fontweight='bold')
        ax.set_ylabel("Seconds / Step", fontsize=12)
        plt.xticks(rotation=45, ha='right', fontsize=10)
        plt.tight_layout()
        plt.savefig(f"{output_prefix}_TIME.png", dpi=300)
        plt.close()

    # Plot Master Memory
    if results_mem:
        df_m = pd.DataFrame(results_mem).set_index("Test")
        fig, ax = plt.subplots(figsize=(16, 8))
        df_m.plot(kind='bar', ax=ax, colormap='coolwarm', edgecolor='black', width=0.8)
        ax.set_title("Master Memory: Peak Footprint Across All Steps", fontsize=16, fontweight='bold')
        ax.set_ylabel("Peak Memory Usage", fontsize=12)
        plt.xticks(rotation=45, ha='right', fontsize=10)
        plt.tight_layout()
        plt.savefig(f"{output_prefix}_MEMORY.png", dpi=300)
        plt.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-dir", required=True)
    parser.add_argument("--output-prefix", required=True)
    args = parser.parse_args()
    build_master_plots(args.test_dir, args.output_prefix)