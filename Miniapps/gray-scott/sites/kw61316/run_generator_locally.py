#!/usr/bin/env python3
"""Run the Shaheen experiment generator's jobs on this workstation (#76).

Loads sites/shaheen/2026-WOIV-scripts/generate_experiments.py itself, changes
only the sizes (64^3 grid, one "node" of --ranks ranks, a short initialisation
and short runs), generates every Paper 1 job and the smallest Paper 2 strong,
weak and in transit set, and runs each one the way its sbatch script would:
inline as one mpirun, in transit as an MPMD mpirun of the simulation and the
analysis reader over SST. The settings, adios2.xml and pipeline files are the
generator's own, so what passes here is what runs on Shaheen III.

With several --ranks values, the images of each job are compared between
rank counts against the render check's budget: at most 0.1% of pixels may
differ by more than 24/255 (README.md, Testing).

    run_generator_locally.py --aac <build> [--akc <kombyne build>] --work <dir>
                             [--ranks 2 4] [--only <substring>] [--adios-matrix]

--aac is a build with ADIOS2, Ascent, Catalyst and the analysis reader;
--akc a build with Kombyne (its jobs are skipped without one). Exits 1 if a
job fails or an image comparison is over budget.
"""
import argparse
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
GSDIR = HERE.parent.parent
GENERATOR = GSDIR / "sites/shaheen/2026-WOIV-scripts/generate_experiments.py"
PIXEL_TOL = 24        # out of 255
PIXEL_BUDGET = 0.001  # fraction of pixels allowed above PIXEL_TOL
# Over budget for a known reason: reported, not failed. In transit Catalyst
# slices change with the reader's rank count (the reader's overlap plane is
# not marked as ghost, #42).
KNOWN_OVER = {r"transit.*catalyst_render": "#42"}

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--aac", required=True, help="build dir with ADIOS2 + Ascent + Catalyst + analysis reader")
ap.add_argument("--akc", default="", help="build dir with Kombyne (Kombyne jobs are skipped without it)")
ap.add_argument("--work", required=True, help="scratch directory (emptied first)")
ap.add_argument("--ranks", type=int, nargs="+", default=[2, 4], help="rank counts to run (default 2 4)")
ap.add_argument("--only", default="", help="run only jobs whose id contains this")
ap.add_argument("--adios-matrix", action="store_true",
                help="also run inline ADIOS2 data with every adios_span / adios_memory_selection combination")
ap.add_argument("--catalyst-lib", default=os.environ.get("CATALYST_IMPLEMENTATION_PATHS", ""),
                help="ParaView's lib/catalyst (default: $CATALYST_IMPLEMENTATION_PATHS)")
args = ap.parse_args()
if not args.catalyst_lib:
    sys.exit("Set --catalyst-lib or CATALYST_IMPLEMENTATION_PATHS to ParaView's lib/catalyst.")

work = pathlib.Path(args.work).resolve()
MARKER = ".run_generator_locally"
if work.exists() and any(work.iterdir()):
    # Only ever empty a directory this script made.
    if not (work / MARKER).exists():
        sys.exit(f"{work} is not empty and was not made by this script; pick another --work.")
    shutil.rmtree(work)
work.mkdir(parents=True, exist_ok=True)
(work / MARKER).touch()

env = dict(os.environ)
env.pop("DISPLAY", None)
env.update(VTK_DEFAULT_OPENGL_WINDOW="vtkEGLRenderWindow", OMP_NUM_THREADS="2",
           CATALYST_IMPLEMENTATION_PATHS=args.catalyst_lib, CATALYST_IMPLEMENTATION_NAME="paraview",
           SST_VERBOSE="0", ADIOS2_LOG_LEVEL="1")
MPI = ["mpirun", "--oversubscribe", "-x", "VTK_DEFAULT_OPENGL_WINDOW", "-x", "OMP_NUM_THREADS",
       "-x", "CATALYST_IMPLEMENTATION_PATHS", "-x", "CATALYST_IMPLEMENTATION_NAME"]


def generate(results, ranks):
    """Generate every job with the generator's code and only the sizes changed."""
    src = GENERATOR.read_text()
    sizing = "p1_nodes, p1_grid, p1_stage = 64, 2048, 4"
    if sizing not in src:
        sys.exit(f"Paper 1 sizing line not found in {GENERATOR}")
    src = src.replace(sizing, "p1_nodes, p1_grid, p1_stage = 1, 64, 1")
    ns = {"__name__": "generate_experiments"}
    exec(compile(src, str(GENERATOR), "exec"), ns)
    ns["SYSTEM_CONFIG"]["mpi_per_node"] = ranks
    ns["GLOBAL_SETTINGS"].update(init_steps=300, run_steps=61, paper1_run_steps=61, plotgap=20)
    ns["INIT_NODE_MAP"][64] = 1
    ns["STRONG_SCALING_NODES"], ns["STRONG_GRID"] = [1], 64
    ns["WEAK_SCALING_CONFIGS"] = [(1, 64)]
    ns["TRANSIT_CONFIGS"] = [("small", 1, 64, 1)]
    ns["TRANSIT_SWEEP_CONFIGS"] = []
    ns["CATALYST_LIB_PATH"] = args.catalyst_lib
    gargs = argparse.Namespace(repo_path=str(GSDIR.parent.parent), bin_path=args.aac,
                               results_dir=str(results), output_dir=str(results.parent / "scripts"),
                               account="local", perf_env="/nonexistent")
    cwd = os.getcwd()
    os.chdir(results.parent)
    try:
        ns["generate_scripts"](gargs)
    finally:
        os.chdir(cwd)


def add_adios_matrix(results):
    """Copies of inline ADIOS2 data for every span / memory-selection pair."""
    base = next(results.glob("paper2_strong_*_adios_data"), None)
    if base is None:
        return
    for span in (False, True):
        for mem in (False, True):
            d = results / f"{base.name}_span{int(span)}_mem{int(mem)}"
            shutil.copytree(base, d)
            s = json.loads((d / "settings.json").read_text())
            s.update(adios_span=span, adios_memory_selection=mem,
                     output_file_name=str(d / "data/grayScott"), adios_config=str(d / "adios2.xml"))
            (d / "settings.json").write_text(json.dumps(s, indent=4))


def run(d, ranks):
    stage = d / "settings-stage.json"
    s = json.loads((d / "settings.json").read_text())
    st = json.loads(stage.read_text())["output_type"] if stage.exists() else ""
    build = args.akc if "kombyne" in (s["output_type"], st) else args.aac
    (d / "data").mkdir(exist_ok=True)
    for f in (d / "data").glob("*.sst"):
        f.unlink()
    cmd = MPI + ["-np", str(ranks), str(pathlib.Path(build) / "gray-scott"), "--logging-level=WARNING",
                 f"--settings-file={d}/settings.json"]
    if stage.exists():
        cmd += [":", "-np", str(ranks), str(pathlib.Path(args.aac) / "analysis" / "analysis-reader"),
                "--settings", str(stage), "--file", f"{d}/data/grayScott",
                "--block-mode", "repartition", "--engine", "SST", "--mpi-split-color=1", "--adios-verbose", "0"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=d, env=env, capture_output=True, text=True, timeout=1800)
        rc, out = p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out = 124, f"timed out after 1800 s\n{e.stdout or ''}{e.stderr or ''}"
    (d / "run.log").write_text(" ".join(cmd) + "\n\n" + out)
    return rc, time.time() - t0, s["output_type"]


def run_all(ranks):
    tag = f"np{ranks}"
    results = work / tag / "results"
    results.mkdir(parents=True)
    generate(results, ranks)
    if args.adios_matrix:
        add_adios_matrix(results)
    ids = sorted(p.name for p in results.iterdir() if p.is_dir())
    jobs = [i for i in ids if i.startswith("init_")]
    jobs += [i for i in ids if i.startswith(("paper1_", "paper2_strong", "paper2_transit")) and args.only in i]
    ok = True
    print(f"== {ranks} ranks", flush=True)
    for i in jobs:
        d = results / i
        if "kombyne" in i and not args.akc:
            print(f"SKIP {i:52s} (no --akc build)")
            continue
        rc, dt, otype = run(d, ranks)
        outs = [p for p in (d / "data").rglob("*") if p.is_file() and not p.name.endswith(".sst")]
        imgs = [p for p in outs if p.suffix in (".png", ".jpg")]
        perf = sorted(d.glob("perf/*/summary.json"))
        ms = f"{json.loads(perf[-1].read_text()).get('loop_wall_per_step_ms', 0):.1f}" if perf else "-"
        # A render job that exits 0 without images has still failed.
        no_images = rc == 0 and re.search(r"render|volume|isosurface", i) and not imgs
        passed = rc == 0 and not no_images
        ok &= passed
        print(f"{'OK  ' if passed else 'FAIL'} {i:52s} {otype:16s} rc={rc:<3d} {dt:5.0f}s "
              f"files={len(outs):3d} images={len(imgs):2d} ms/step={ms}{'  (no images)' if no_images else ''}", flush=True)
    return results, ok


def compare_images(dirs):
    """Pixel differences of each job's images between the first and each other rank count."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        print("Image comparison needs numpy and Pillow; run with one --ranks value to skip it.")
        return False
    ok = True
    ref_tag, ref = dirs[0]
    print(f"== images against {ref_tag} (budget {PIXEL_BUDGET:.1%} of pixels above {PIXEL_TOL}/255)")
    def images(d):
        return {pathlib.Path(f).name for f in glob.glob(str(d / "data" / "*.png")) + glob.glob(str(d / "data" / "*.jpg"))}

    names = sorted({p.name for _, d in dirs for p in d.iterdir() if p.is_dir()})
    for name in names:
        job = ref / name
        for tag, other in dirs[1:]:
            mine, theirs = images(job), images(pathlib.Path(other) / name)
            imgs = sorted(mine | theirs)
            worst = 0.0
            for n in imgs:
                f, g = job / "data" / n, pathlib.Path(other) / name / "data" / n
                if n not in mine or n not in theirs:
                    worst = 1.0  # an image one rank count wrote and the other did not
                    continue
                a = np.asarray(Image.open(f).convert("RGB"), dtype=int)
                b = np.asarray(Image.open(g).convert("RGB"), dtype=int)
                worst = 1.0 if a.shape != b.shape else max(worst, float((np.abs(a - b).max(axis=2) > PIXEL_TOL).mean()))
            if imgs:
                over = worst > PIXEL_BUDGET
                known = next((v for k, v in KNOWN_OVER.items() if re.search(k, job.name)), None)
                ok &= not over or known is not None
                label = "ok  " if not over else (f"KNOWN ({known})" if known else "OVER")
                print(f"{label} {job.name:52s} vs {tag}: {worst:.3%}")
    return ok


all_ok = True
dirs = []
for r in args.ranks:
    results, ok = run_all(r)
    all_ok &= ok
    dirs.append((f"np{r}", results))
if len(dirs) > 1:
    all_ok &= compare_images(dirs)
print("PASSED" if all_ok else "FAILED")
sys.exit(0 if all_ok else 1)
