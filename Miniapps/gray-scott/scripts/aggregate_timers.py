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

def p25(x): return np.nanpercentile(x, 25)
def p75(x): return np.nanpercentile(x, 75)

def process_timers(files, test, skip_base_cols):
    """Applies HPC-style exhaustive statistical reduction to a set of timer CSVs."""
    if not files:
        return None, 0.0, 0.0, 0.0, 0.0, 0.0, None
        
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    if 'step' not in df.columns:
        return None, 0.0, 0.0, 0.0, 0.0, 0.0, None

    # 1. Build aggregation dictionary for all numeric columns
    metrics = ['mean', 'min', 'max', p25, p75]
    agg_dict = {col: metrics for col in df.columns if col != 'step' and pd.api.types.is_numeric_dtype(df[col])}
    
    # 2. Group by step and calculate exhaustive stats
    summary = df.groupby('step').agg(agg_dict)
    summary.columns = ['_'.join(col).strip() for col in summary.columns.values]
    summary = summary.reset_index()
    
    # 3. Filter out cold-start steps (Steps 0 & 1)
    if len(summary) > 2: 
        summary = summary[summary['step'] > 1]
        
    # 4. Extract Console Stats
    t_mean, t_min, t_max = 0.0, 0.0, 0.0
    m_min, m_max = 0.0, 0.0
    
    if 'total_step_mean' in summary.columns:
        t_mean = summary['total_step_mean'].mean()
        t_min = summary['total_step_min'].min()
        t_max = summary['total_step_max'].max()
        
    # Find memory columns based on the _max and _min suffixes
    mem_max_cols = [c for c in summary.columns if any(x in c.lower() for x in ['mem', 'rss', 'hwm', 'vsize', 'bytes']) and c.endswith('_max')]
    mem_min_cols = [c.replace('_max', '_min') for c in mem_max_cols]
    
    if mem_max_cols:
        m_max = summary[mem_max_cols].max().max()
        m_min = summary[mem_min_cols].min().min()

    # 5. Extract strictly the _mean columns for accurate Stacked Bar plotting
    time_cols = [c for c in summary.columns if c.endswith('_mean') and c.replace('_mean', '') not in skip_base_cols and not any(m in c.lower() for m in ['mem', 'rss', 'hwm', 'vsize', 'bytes'])]
    
    mean_times = {}
    if time_cols:
        # Get the average of the means across all steady-state steps
        raw_means = summary[time_cols].mean().to_dict()
        # Clean up names for the plot legend (remove '_mean')
        mean_times = {k.replace('_mean', ''): v for k, v in raw_means.items()}
        mean_times['Test'] = test

    # Add the test name to the dataframe for master CSV concatenation
    summary.insert(0, 'Test', test)
        
    return mean_times, t_mean, t_min, t_max, m_min, m_max, summary

def build_master_plots(test_dir, output_prefix):
    tests = sorted([d for d in os.listdir(test_dir) if os.path.isdir(os.path.join(test_dir, d)) and d != "performance_summary_plots"])
    
    results_sim_time = []
    results_analysis_time = []
    results_mem = []
    console_stats = []
    all_summaries = []

    skip_cols = ['step', 'rank', 'hostname', 'thread', 'total_step', 'user_s', 'sys_s', 'elapsed_s']

    for test in tests:
        test_path = os.path.join(test_dir, test)
        
        # --- PARSE SIMULATION (WRITER) TIMERS ---
        w_files = glob.glob(os.path.join(test_path, "writer_timers", "*.csv"))
        sim_means, st_mean, st_min, st_max, sm_min, sm_max, sim_df = process_timers(w_files, test, skip_cols)
        if sim_means:
            results_sim_time.append(sim_means)
            sim_df.insert(1, 'Role', 'Simulation')
            all_summaries.append(sim_df)

        # --- PARSE ANALYSIS (READER) TIMERS ---
        r_files = glob.glob(os.path.join(test_path, "reader_timers", "*.csv"))
        ana_means, at_mean, at_min, at_max, am_min, am_max, ana_df = process_timers(r_files, test, skip_cols)
        if ana_means:
            results_analysis_time.append(ana_means)
            ana_df.insert(1, 'Role', 'Analysis')
            all_summaries.append(ana_df)

        if sm_max > 0 or am_max > 0:
            results_mem.append({"Test": test, "Simulation Peak Mem": sm_max, "Analysis Peak Mem": am_max})
            
        console_stats.append({
            "Test": test,
            "Sim_T": (st_mean, st_min, st_max),
            "Ana_T": (at_mean, at_min, at_max),
            "Sim_M": (sm_min, sm_max),
            "Ana_M": (am_min, am_max)
        })

    # --- SAVE EXHAUSTIVE MASTER CSV ---
    if all_summaries:
        master_df = pd.concat(all_summaries, ignore_index=True)
        csv_path = f"{output_prefix}_EXHAUSTIVE_STATS.csv"
        master_df.to_csv(csv_path, index=False)
        print(f"\n✅ Saved exhaustive statistical breakdown to: {csv_path}")

    # --- PRINT CONSOLE SUMMARY ---
    print("\n" + "="*140)
    print(f"{'Test Configuration':<42} | {'Steady-State Sim Time (s)':<28} | {'Steady-State Ana Time (s)':<28} | {'Sim Mem (Min/Max)':<16} | {'Ana Mem (Min/Max)':<16}")
    print(f"{'(Excludes Steps 0 & 1)':<42} | {'(Avg / Min / Max)':<28} | {'(Avg / Min / Max)':<28} | {'(MB)':<16} | {'(MB)':<16}")
    print("="*140)
    for s in console_stats:
        st_str = f"{s['Sim_T'][0]:.2f} / {s['Sim_T'][1]:.2f} / {s['Sim_T'][2]:.2f}" if s['Sim_T'][0] > 0 else "-"
        at_str = f"{s['Ana_T'][0]:.2f} / {s['Ana_T'][1]:.2f} / {s['Ana_T'][2]:.2f}" if s['Ana_T'][0] > 0 else "-"
        sm_str = f"{s['Sim_M'][0]:.0f} / {s['Sim_M'][1]:.0f}" if s['Sim_M'][1] > 0 else "-"
        am_str = f"{s['Ana_M'][0]:.0f} / {s['Ana_M'][1]:.0f}" if s['Ana_M'][1] > 0 else "-"
        print(f"{s['Test']:<42} | {st_str:<28} | {at_str:<28} | {sm_str:<16} | {am_str:<16}")
    print("="*140 + "\n")

plt.style.use('ggplot')

    if results_sim_time:
        df_sim = pd.DataFrame(results_sim_time).set_index("Test").fillna(0)
        fig, ax = plt.subplots(figsize=(16, 8))
        
        wait_indicators = ['adios_wait', 'adios_wait_mean']
        # 1. Properly identify columns
        active_cols = [c for c in df_sim.columns if c not in wait_indicators and c != 'Test']
        # 2. Safely find the wait column without crashing if it's missing
        wait_col = next((c for c in df_sim.columns if c in wait_indicators), None)
        has_idle = wait_col is not None and df_sim[wait_col].sum() > 0

        x = np.arange(len(df_sim))
        width = 0.4 if has_idle else 0.8
        offset = -width/2 if has_idle else 0
        
        # Draw Active Compute (Stacked)
        bottom = np.zeros(len(df_sim))
        cmap = plt.get_cmap('viridis')
        colors = cmap(np.linspace(0, 1, max(1, len(active_cols))))
        
        for idx, col in enumerate(active_cols):
            ax.bar(x + offset, df_sim[col], width, label=col, 
                   bottom=bottom, color=colors[idx], edgecolor='black')
            bottom += df_sim[col]
            
        # Draw Idle Time Bar if it exists
        if has_idle:
            ax.bar(x + width/2, df_sim[wait_col], width, label='adios_wait (Idle)', 
                   color='lightgray', hatch='///', edgecolor='black')
            
        ax.set_title("Master Performance: Simulation Stacked Breakdown\n(Steady-State Avg s/step | Steps 0 & 1 Excluded)", fontsize=16, fontweight='bold')
        ax.set_ylabel("Seconds / Step", fontsize=12)
        ax.set_xticks(x)
        ax.set_xticklabels(df_sim.index, rotation=45, ha='right', fontsize=10)
        ax.legend(bbox_to_anchor=(1.01, 1), loc='upper left')
        
        plt.tight_layout()
        plt.savefig(f"{output_prefix}_TIME_SIM_STACKED.png", dpi=300)
        plt.close()

    if results_analysis_time:
        df_analysis = pd.DataFrame(results_analysis_time).set_index("Test").fillna(0)
        fig, ax = plt.subplots(figsize=(16, 8))
        
        wait_indicators = ['adios_wait', 'adios_wait_mean']
        # CRITICAL FIX: Use df_analysis here, not df_sim
        active_cols = [c for c in df_analysis.columns if c not in wait_indicators and c != 'Test']
        wait_col = next((c for c in df_analysis.columns if c in wait_indicators), None)
        has_idle = wait_col is not None and df_analysis[wait_col].sum() > 0

        x = np.arange(len(df_analysis))
        width = 0.4 if has_idle else 0.8
        offset = -width/2 if has_idle else 0
        
        # Draw Active Compute (Stacked)
        bottom = np.zeros(len(df_analysis))
        cmap = plt.get_cmap('plasma')
        colors = cmap(np.linspace(0, 1, max(1, len(active_cols))))
        
        for idx, col in enumerate(active_cols):
            ax.bar(x + offset, df_analysis[col], width, label=col, 
                   bottom=bottom, color=colors[idx], edgecolor='black')
            bottom += df_analysis[col]
            
        # Draw Idle Time Bar if it exists
        if has_idle:
            ax.bar(x + width/2, df_analysis[wait_col], width, label='adios_wait (Idle)', 
                   color='lightgray', hatch='///', edgecolor='black')
            
        ax.set_title("Master Performance: In-Transit Analysis Stacked Breakdown\n(Steady-State Avg s/step | Steps 0 & 1 Excluded)", fontsize=16, fontweight='bold')
        ax.set_ylabel("Seconds / Step", fontsize=12)
        ax.set_xticks(x)
        ax.set_xticklabels(df_analysis.index, rotation=45, ha='right', fontsize=10)
        ax.legend(bbox_to_anchor=(1.01, 1), loc='upper left')
        
        plt.tight_layout()
        plt.savefig(f"{output_prefix}_TIME_ANALYSIS_STACKED.png", dpi=300)
        plt.close()
        
    if results_mem:
        df_m = pd.DataFrame(results_mem).set_index("Test")
        fig, ax = plt.subplots(figsize=(16, 8))
        df_m.plot(kind='bar', ax=ax, colormap='coolwarm', edgecolor='black', width=0.8)
        ax.set_title("Master Memory: Peak Footprint Across Active Run\n(Steps 0 & 1 Excluded)", fontsize=16, fontweight='bold')
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