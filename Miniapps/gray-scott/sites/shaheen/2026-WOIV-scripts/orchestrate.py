import os
import argparse
import subprocess
import glob
import shutil

def main():
    parser = argparse.ArgumentParser(description="Gray-Scott Experiment Orchestrator")
    
    # Selection Criteria
    parser.add_argument("--script-dir", default="generated_scripts", help="Directory containing .sbat files")
    parser.add_argument("--results-dir", required=True, help="Root directory for results (Lustre)")
    
    parser.add_argument("--paper", choices=["paper1", "paper2", "init", "all"], default="all", help="Target specific paper (use 'init' for initialization runs)")
    parser.add_argument("--nodes", type=str, help="Target specific node count (e.g. 64, 256, 4096)")
    # ADDED: 'baseline' to choices
    parser.add_argument("--backend", choices=["adios", "ascent", "catalyst", "kombyne", "baseline", "all"], default="all", help="Target backend")
    parser.add_argument("--type", choices=["inline", "intransit", "all"], default="all", help="Target coupling type")
    
    # Mode Selection
    parser.add_argument("--mode", choices=["init", "run", "all"], default="all", 
                        help="Select 'init' to run checkpoints, 'run' for benchmarks, 'all' for both.")

    # Actions
    parser.add_argument("--submit", action="store_true", help="Submit jobs to Slurm")
    parser.add_argument("--clean", action="store_true", help="DELETE result data and logs (Preserves configs)")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Print actions without executing")

    args = parser.parse_args()

    # 1. Find all generated scripts
    scripts = glob.glob(os.path.join(args.script_dir, "*.sbat"))
    
    if not scripts:
        print(f"No scripts found in {args.script_dir}. Did you run generate_experiments.py?")
        return

    print(f"Found {len(scripts)} total scripts. Filtering...")

    # 2. Filter Scripts
    selected_scripts = []
    for s in scripts:
        basename = os.path.basename(s).replace(".sbat", "")
        parts = basename.split("_")
        
        # --- Mode Filter ---
        # Catch "init_" prefix (new convention) or "_init" suffix (old convention)
        is_init = basename.startswith("init_") or "_init" in basename
        
        if args.mode == "init" and not is_init: continue
        if args.mode == "run" and is_init: continue

        # --- Experiment Filters ---
        p_paper = parts[0] # "paper1", "paper2", or "init"
        
        p_type = "intransit" if ("transit" in parts or "intransit" in parts) else "inline"
        
        p_backend = "unknown"
        if "baseline" in basename: p_backend = "baseline"
        elif "adios" in basename: p_backend = "adios"
        elif "ascent" in basename: p_backend = "ascent"
        elif "catalyst" in basename: p_backend = "catalyst"
        elif "kombyne" in basename: p_backend = "kombyne"

        # Apply Filters
        if args.paper != "all" and args.paper != p_paper: continue
        
        # Skip type/backend filters for init runs unless explicitly requested, 
        # as init runs are usually just "inline adios"
        if not is_init:
            if args.type != "all" and args.type != p_type: continue
            if args.backend != "all" and args.backend != p_backend: continue
        
        # Check inside file for node count (reliable)
        if args.nodes:
            with open(s, 'r') as f:
                content = f.read()
                if f"#SBATCH --nodes={args.nodes}" not in content:
                    continue

        selected_scripts.append(s)

    selected_scripts.sort()
    print(f"Selected {len(selected_scripts)} experiments matching criteria.")
    
    if len(selected_scripts) == 0:
        return

    # 3. Perform Actions
    if not args.submit and not args.clean:
        print("\n[DRY RUN] Use --submit to run or --clean to reset results.")

    for s in selected_scripts:
        basename = os.path.basename(s).replace(".sbat", "")
        result_path = os.path.join(args.results_dir, basename)
        
        print(f"\nExperiment: {basename}")
        
        # CLEANUP (Surgical)
        if args.clean:
            if os.path.exists(result_path):
                print(f"  [CLEAN] Cleaning artifacts in: {result_path}")
                
                # 1. Directories to remove
                dirs_to_remove = ["data", "analysis_output"]
                for d in dirs_to_remove:
                    d_path = os.path.join(result_path, d)
                    if os.path.exists(d_path):
                        print(f"    Removing dir: {d}/")
                        if not args.dry_run:
                            shutil.rmtree(d_path)

                # 2. Logs to remove
                logs = glob.glob(os.path.join(result_path, "slurm-*.out")) + \
                       glob.glob(os.path.join(result_path, "slurm-*.err"))
                
                for log in logs:
                    print(f"    Removing log: {os.path.basename(log)}")
                    if not args.dry_run:
                        os.remove(log)
            else:
                print(f"  [CLEAN] Dir not found (nothing to clean): {result_path}")

        # SUBMIT
        if args.submit:
            # Check if output exists (safety)
            if os.path.exists(result_path):
                # Only skip if SLURM logs exist (indicates a run happened)
                has_logs = any(f.startswith("slurm-") for f in os.listdir(result_path))
                
                if has_logs:
                    print(f"  [SKIP] Slurm logs found in: {result_path}")
                    print("          Use --clean to overwrite.")
                    continue
            
            cmd = ["sbatch", s]
            print(f"  [SUBMIT] {' '.join(cmd)}")
            if not args.dry_run:
                subprocess.run(cmd)

if __name__ == "__main__":
    main()
