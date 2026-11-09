import os
import re
import glob
import argparse

def audit_runs(results_dir):
    print(f"\n{'='*60}")
    print(f"🔍 AUDITING RUNS IN: {results_dir}")
    print(f"{'='*60}")
    
    if not os.path.exists(results_dir):
        print(f"Error: Directory '{results_dir}' does not exist.")
        return

    # Find all experiment directories
    all_items = os.listdir(results_dir)
    exp_dirs = [d for d in all_items if os.path.isdir(os.path.join(results_dir, d)) and ("paper1" in d or "paper2" in d)]
    
    if not exp_dirs:
        print("No valid run directories found (looking for 'paper1_' or 'paper2_' prefixes).")
        return

    unsubmitted = []
    slurm_failed = []
    running_or_dead = []
    success_count = 0
    
    for exp_id in sorted(exp_dirs):
        exp_path = os.path.join(results_dir, exp_id)
        is_transit = "transit" in exp_id
        
        writer_csv = os.path.join(results_dir, f"{exp_id}_writer.csv")
        reader_csv = os.path.join(results_dir, f"{exp_id}_reader.csv")
        
        # --- FIX 1: The CSVs are the ultimate source of truth ---
        has_writer = os.path.exists(writer_csv)
        has_reader = os.path.exists(reader_csv) if is_transit else True
        
        slurm_outs = glob.glob(os.path.join(exp_path, "slurm-*.out"))
        content = ""
        if slurm_outs:
            # The most recent attempt (in case of requeues), .out and .err.
            latest_out = max(slurm_outs, key=os.path.getmtime)
            for log in (latest_out, latest_out[:-4] + ".err"):
                if os.path.exists(log):
                    with open(log, 'r', encoding='utf-8', errors='ignore') as f:
                        content += f.read()
        # The job prints its run's exit status (generate_experiments.py).
        m = re.search(r"Run exit status: (\d+)", content)
        run_failed = m is not None and m.group(1) != "0"

        if has_writer and has_reader and not run_failed:
            success_count += 1
            continue  # Data is there, move on!

        # --- If data is missing or the run failed, figure out why ---
        if not slurm_outs:
            unsubmitted.append(exp_id)
            continue

        if run_failed and not any(k in content for k in ("CANCELLED", "DUE TO TIME LIMIT", "OOM", "Out Of Memory", "SIGSEGV", "Fatal error")):
            slurm_failed.append(f"{exp_id} (RUN EXIT STATUS {m.group(1)})")
        elif "CANCELLED" in content or "DUE TO TIME LIMIT" in content:
            slurm_failed.append(f"{exp_id} (TIMEOUT)")
        elif "OOM" in content or "Out Of Memory" in content or "oom-kill" in content.lower():
            slurm_failed.append(f"{exp_id} (OUT OF MEMORY)")
        elif "SIGSEGV" in content or "Fatal error" in content or "segmentation fault" in content.lower():
            slurm_failed.append(f"{exp_id} (CRASHED - See Log)")
        else:
            # If there are no explicit errors but data is missing, it's either currently running/reducing or died silently
            running_or_dead.append(f"{exp_id} (Running / Post-Processing / Silently Failed)")

    # --- Print Summary ---
    if not unsubmitted and not slurm_failed and not running_or_dead:
        print(f"✅ ALL {success_count} JOBS COMPLETED SUCCESSFULLY AND PRODUCED DATA!\n")
        return
        
    if unsubmitted:
        print(f"📦 NOT STARTED / UNSUBMITTED ({len(unsubmitted)} jobs with no Slurm logs):")
        for r in unsubmitted: 
            print(f"  - {r}")
        print("")

    if running_or_dead:
        print(f"⏳ INCOMPLETE / RUNNING ({len(running_or_dead)} jobs missing CSVs, no explicit crash in log):")
        for r in running_or_dead: 
            print(f"  - {r}")
        print("")
            
    if slurm_failed:
        print(f"⚠️ SLURM ERRORS ({len(slurm_failed)} jobs explicitly crashed or timed out):")
        for r in slurm_failed: 
            print(f"  - {r}")
        print("")
        
    print(f"📊 SUMMARY: {success_count} Successful | {len(unsubmitted)} Unsubmitted | {len(running_or_dead)} Incomplete/Running | {len(slurm_failed)} Failed\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit Gray-Scott scaling runs.")
    parser.add_argument("--results-dir", required=True, help="Path to the main runs directory")
    args = parser.parse_args()
    
    audit_runs(args.results_dir)
