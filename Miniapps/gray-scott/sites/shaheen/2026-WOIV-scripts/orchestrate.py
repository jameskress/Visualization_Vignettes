import os
import argparse
import subprocess
import glob
import shutil
import json  # Added for parsing grid size
import random
import re
import time

# James's standing OK covers jobs up to about this many nodes (21 Nov 2026);
# anything larger is submitted only with --allow-over-limit naming it.
NODE_LIMIT = 3500


def _job_nodes(script):
    """The #SBATCH --nodes value of a generated job script (0 if absent)."""
    with open(script) as f:
        for line in f:
            m = re.match(r"#SBATCH --nodes=(\d+)", line)
            if m:
                return int(m.group(1))
    return 0


def main():
    parser = argparse.ArgumentParser(description="Gray-Scott Experiment Orchestrator")

    # Selection Criteria
    parser.add_argument(
        "--script-dir",
        default="generated_scripts",
        help="Directory containing .sbat files",
    )
    parser.add_argument(
        "--results-dir", required=True, help="Root directory for results (Lustre)"
    )

    parser.add_argument(
        "--paper",
        choices=["paper1", "paper2", "xport", "scale", "pipe", "init", "all"],
        default="all",
        help="Target specific paper ('xport' is the #72 step 1 transport matrix, 'scale' the step 2 scaling runs, 'pipe' the reader cost runs; 'init' the initialization runs)",
    )
    parser.add_argument(
        "--nodes",
        type=str,
        help="Target specific SIMULATION node count (e.g. 64, 256, 4096)",
    )
    parser.add_argument(
        "--grid", type=str, help="Target specific grid size (L) (e.g., 1024, 2048)"
    )  # NEW
    parser.add_argument(
        "--backend",
        choices=["adios", "ascent", "catalyst", "kombyne", "baseline", "all"],
        default="all",
        help="Target backend",
    )
    parser.add_argument(
        "--type",
        choices=["inline", "intransit", "all"],
        default="all",
        help="Target coupling type",
    )
    parser.add_argument(
        "--workload",
        choices=["data", "render", "volume", "isosurface", "all"],
        default="all",
        help="Target specific workload type",
    )

    # Mode Selection
    parser.add_argument(
        "--mode",
        choices=["init", "run", "all"],
        default="all",
        help="Select 'init' to run checkpoints, 'run' for benchmarks, 'all' for both.",
    )

    # Actions
    parser.add_argument("--submit", action="store_true", help="Submit jobs to Slurm")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="DELETE result data and logs (Preserves configs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print actions without executing",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Seed for the submission order (default: random, printed and logged)",
    )
    parser.add_argument(
        "--no-shuffle",
        action="store_true",
        help="Submit in name order. By default the order is shuffled so the repeats of one configuration "
        "(<id>_r01 ...) are spread over time and one bad stretch on the machine cannot hit them all",
    )
    parser.add_argument(
        "--allow-over-limit",
        action="append",
        default=[],
        metavar="SUBSTRING",
        help=f"Also submit jobs larger than {NODE_LIMIT} nodes whose name contains SUBSTRING "
        "(repeatable). Only with James's approval for those runs",
    )

    args = parser.parse_args()

    # 1. Find all generated scripts
    scripts = glob.glob(os.path.join(args.script_dir, "*.sbat"))

    if not scripts:
        print(
            f"No scripts found in {args.script_dir}. Did you run generate_experiments.py?"
        )
        return

    print(f"Found {len(scripts)} total scripts. Filtering...")

    # 2. Filter Scripts
    selected_scripts = []
    for s in scripts:
        basename = os.path.basename(s).replace(".sbat", "")
        parts = basename.split("_")

        # --- Mode Filter ---
        is_init = basename.startswith("init_") or "_init" in basename

        if args.mode == "init" and not is_init:
            continue
        if args.mode == "run" and is_init:
            continue

        # --- Experiment Filters ---
        p_paper = parts[0]  # "paper1", "paper2", or "init"
        p_type = (
            "intransit" if ("transit" in parts or "intransit" in parts) else "inline"
        )

        p_backend = "unknown"
        if "baseline" in basename:
            p_backend = "baseline"
        elif "adios" in basename:
            p_backend = "adios"
        elif "ascent" in basename:
            p_backend = "ascent"
        elif "catalyst" in basename:
            p_backend = "catalyst"
        elif "kombyne" in basename:
            p_backend = "kombyne"

        p_workload = "unknown"
        if "data" in basename:
            p_workload = "data"
        elif "render" in basename:
            p_workload = "render"
        elif "volume" in basename:
            p_workload = "volume"
        elif "isosurface" in basename:
            p_workload = "isosurface"

        # Apply Standard Filters
        if args.paper != "all" and args.paper != p_paper:
            continue

        if not is_init:
            if args.type != "all" and args.type != p_type:
                continue
            if args.backend != "all" and args.backend != p_backend:
                continue
            if args.workload != "all" and args.workload != p_workload:
                continue

        # Node filtering
        if args.nodes:
            try:
                node_tag = f"_N{int(args.nodes):04d}"
                if node_tag not in basename:
                    continue
            except ValueError:
                print(f"Warning: Invalid node count provided: {args.nodes}")
                continue

        # --- NEW: Grid Size Filtering via settings.json ---
        if args.grid:
            settings_path = os.path.join(args.results_dir, basename, "settings.json")
            try:
                with open(settings_path, "r") as f:
                    settings_data = json.load(f)
                    if str(settings_data.get("L")) != args.grid:
                        continue
            except (FileNotFoundError, json.JSONDecodeError):
                # If settings.json is missing, skip it so we don't accidentally launch the wrong size
                print(
                    f"Warning: Could not read {settings_path} to verify grid size. Skipping."
                )
                continue

        selected_scripts.append(s)

    selected_scripts.sort()
    print(f"Selected {len(selected_scripts)} experiments matching criteria.")

    if len(selected_scripts) == 0:
        return

    # Jobs above NODE_LIMIT need James's approval: dropped unless named.
    if args.submit:
        kept = []
        for s in selected_scripts:
            name = os.path.basename(s).replace(".sbat", "")
            n = _job_nodes(s)
            if n > NODE_LIMIT and not any(a in name for a in args.allow_over_limit):
                print(
                    f"  [HOLD] {name}: {n} nodes is above {NODE_LIMIT}; needs James's approval (--allow-over-limit)"
                )
                continue
            kept.append(s)
        selected_scripts = kept

    # The log goes in the results directory: refuse before submitting anything
    # if it is missing, rather than stop half way with a job unrecorded.
    if args.submit and not args.dry_run and not os.path.isdir(args.results_dir):
        print(
            f"Results directory {args.results_dir} does not exist "
            "(did generate_experiments.py write there?)"
        )
        return

    # Spread repeats over time: a shuffled order, reproducible from the seed.
    # Initialisations stay first: the runs restart from their checkpoints.
    seed = (
        args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
    )
    if not args.no_shuffle:
        inits = [s for s in selected_scripts if os.path.basename(s).startswith("init_")]
        runs = [s for s in selected_scripts if s not in inits]
        random.Random(seed).shuffle(runs)
        selected_scripts = inits + runs
        print(f"Submission order shuffled with seed {seed} (initialisations first)")

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

                dirs_to_remove = [
                    "data",
                    "analysis_output",
                    "perf",
                    "writer_timers",
                    "reader_timers",
                    # left by an interrupted reduction (#72)
                    "reduce.lock",
                    "perf.restore",
                    "reader_timers.restore",
                ]
                for d in dirs_to_remove:
                    d_path = os.path.join(result_path, d)
                    if os.path.exists(d_path):
                        print(f"    Removing dir: {d}/")
                        if not args.dry_run:
                            shutil.rmtree(d_path)

                # Logs, compressed timings, and the reduced results beside
                # the run directory: left behind, a failed rerun would look complete.
                logs = (
                    glob.glob(os.path.join(result_path, "slurm-*.out"))
                    + glob.glob(os.path.join(result_path, "slurm-*.err"))
                    + glob.glob(os.path.join(result_path, "reduce-*.out"))
                    + glob.glob(os.path.join(result_path, "reduce-*.err"))
                    + glob.glob(os.path.join(result_path, "*.tar.gz"))
                    + glob.glob(os.path.join(result_path, "*.tar.gz.tmp"))
                    + glob.glob(os.path.join(args.results_dir, f"{basename}_*.csv"))
                    + glob.glob(os.path.join(args.results_dir, f"{basename}_*.json"))
                    + glob.glob(os.path.join(args.results_dir, f"{basename}_job.sbat"))
                    + glob.glob(os.path.join(args.results_dir, f"{basename}_env.txt"))
                )

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
                has_logs = any(f.startswith("slurm-") for f in os.listdir(result_path))

                if has_logs:
                    print(f"  [SKIP] Slurm logs found in: {result_path}")
                    print("         Use --clean to overwrite.")
                    continue

            cmd = ["sbatch", "--parsable", s]
            print(f"  [SUBMIT] {' '.join(cmd)}")
            if not args.dry_run:
                out = subprocess.run(cmd, capture_output=True, text=True)
                job = out.stdout.strip().split(";")[0]
                if out.returncode != 0:
                    print(f"  [FAILED] {out.stderr.strip()}")
                    job = "FAILED"
                else:
                    print(f"  [JOB] {job}")
                # One line per submission: when, which seed, which script, which job.
                with open(
                    os.path.join(args.results_dir, "submissions.tsv"), "a"
                ) as log:
                    log.write(
                        f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{'none' if args.no_shuffle else seed}\t"
                        f"{basename}\t{_job_nodes(s)}\t{job}\n"
                    )


if __name__ == "__main__":
    main()
