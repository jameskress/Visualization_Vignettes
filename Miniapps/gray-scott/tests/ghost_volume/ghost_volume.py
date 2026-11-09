#!/usr/bin/env python3
"""Backend ghost volume test (#24).

Runs the seeded 64^3 problem to step 100 with one backend on 1, 2, 4 and 8
ranks. The backend's own pipeline (or the reader of its output) counts the
cells where every corner has u <= 0.3 and integrates their volume. A cell
counted twice at a rank boundary (bad ghosts) or missing (a gap) changes
the count, so the count must equal the 1-rank count exactly and the volume
must agree within 1e-12 relative. The result is written to
<workdir>/<backend>.json for the cross-backend comparison (--compare).

    ghost_volume.py --backend catalyst --exe build/gray-scott --pvpython ... --workdir ...
    ghost_volume.py --compare <workdir>

Backends and how they count:
  catalyst  in situ: a Catalyst script runs Threshold (all points u <= 0.3),
            then counts non-ghost cells and integrates the volume
            (IntegrateVariables skips DUPLICATECELL cells)
  pvti      the .pvti output read by pvpython, same pipeline; the files
            carry vtkGhostType
  kombyne   Kombyne's VTK export read by pvpython; its mask is __ghostCells
            (1 = real), applied before counting
  ascent    in situ: an Ascent threshold pipeline (u <= 0.3) saved with a
            relay extract, counted with h5py. Ascent's threshold keeps a cell
            if ANY corner is in range (this Ascent has no all-corners option),
            and its pipelines keep ghost cells (Ascent strips them only
            before rendering), so the count is of cells with ascent_ghosts
            == 0. Compared with the ADIOS2 reference under the same rule.
  adios     the BP5 output read with bpls; U holds every global point once,
            so the count is computed directly on the periodic global array
            (the reference: no ghost handling involved). It records both the
            all-corners and the any-corner count.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

STEP = 100
THRESHOLD = 0.3
SPACING = 0.1
RANKS = [1, 2, 4, 8]
HERE = Path(__file__).resolve().parent

CATALYST_SCRIPT = r'''
from paraview.simple import *
from paraview import servermanager as sm
producer = TrivialProducer(registrationName="grid")
th = Threshold(Input=producer, Scalars=["POINTS", "u"], LowerThreshold=-1e30, UpperThreshold=%(t)r,
               ThresholdMethod="Between", AllScalars=1)
iv = IntegrateVariables(Input=th)
def owned_cells(d):
    # Leaves of a composite dataset (Catalyst gives partitioned data).
    leaves = []
    if d.IsA("vtkCompositeDataSet"):
        it = d.NewIterator(); it.InitTraversal()
        while not it.IsDoneWithTraversal():
            leaves.append(it.GetCurrentDataObject()); it.GoToNextItem()
    else:
        leaves = [d]
    n = 0
    for b in leaves:
        g = b.GetCellData().GetArray("vtkGhostType")
        m = b.GetNumberOfCells()
        n += m if g is None else sum(1 for i in range(m) if g.GetValue(i) == 0)
    return n
def catalyst_execute(info):
    if info.cycle != %(step)d:
        return
    th.UpdatePipeline(info.time)
    d = sm.Fetch(th)            # collective: every rank calls it
    v = sm.Fetch(iv)
    owned = owned_cells(d)
    vol = v.GetCellData().GetArray("Volume")
    from vtkmodules.vtkParallelCore import vtkMultiProcessController
    c = vtkMultiProcessController.GetGlobalController()
    if (c is None or c.GetLocalProcessId() == 0) and vol is not None:
        print("GHOSTVOL %%d %%.17g" %% (owned, vol.GetValue(0)))
'''

ASCENT_ACTIONS = r'''
- action: "add_pipelines"
  pipelines:
    th:
      f1:
        type: "threshold"
        params:
          field: "u"
          min_value: -1.0e30
          max_value: %(t)r
- action: "add_extracts"
  extracts:
    e1:
      type: "relay"
      pipeline: "th"
      params:
        path: "gv_ascent"
        protocol: "blueprint/mesh/hdf5"
'''

READER_SCRIPT = r'''
import sys
from paraview.simple import *
from paraview import servermanager as sm
kind, path = sys.argv[1], sys.argv[2]
r = OpenDataFile(path)
field, mask = ("u", None) if kind == "pvti" else ("U", "__ghostCells")
src = r
if mask:  # Kombyne: keep real cells only (mask 1 = real)
    src = Threshold(Input=r, Scalars=["CELLS", mask], LowerThreshold=1, UpperThreshold=255,
                    ThresholdMethod="Between")
th = Threshold(Input=src, Scalars=["POINTS", field], LowerThreshold=-1e30, UpperThreshold=%(t)r,
               ThresholdMethod="Between", AllScalars=1)
def owned_cells(d):
    # Leaves of a composite dataset (Catalyst gives partitioned data).
    leaves = []
    if d.IsA("vtkCompositeDataSet"):
        it = d.NewIterator(); it.InitTraversal()
        while not it.IsDoneWithTraversal():
            leaves.append(it.GetCurrentDataObject()); it.GoToNextItem()
    else:
        leaves = [d]
    n = 0
    for b in leaves:
        g = b.GetCellData().GetArray("vtkGhostType")
        m = b.GetNumberOfCells()
        n += m if g is None else sum(1 for i in range(m) if g.GetValue(i) == 0)
    return n
d = sm.Fetch(th)
owned = owned_cells(d)
vol = sm.Fetch(IntegrateVariables(Input=th)).GetCellData().GetArray("Volume")
print("GHOSTVOL %%d %%.17g" %% (owned, vol.GetValue(0) if vol is not None else 0.0))
'''


def settings_for(backend, args, d):
    s = json.loads((HERE.parent.parent / "configs/miniapp-settings/settings-none.json").read_text())
    s.update(steps=STEP + 1, plotgap=STEP, perf_dir="perf", checkpoint=False)
    if backend == "catalyst":
        (d / "ghost_volume_catalyst.py").write_text(CATALYST_SCRIPT % {"t": THRESHOLD, "step": STEP})
        s.update(output_type="catalyst_insitu", catalyst_script_path="ghost_volume_catalyst.py",
                 catalyst_lib_path=args.catalyst_lib)
    elif backend == "pvti":
        s.update(output_type="pvti", output_file_name="gv-%04ts.vti")
    elif backend == "kombyne":
        shutil.copy(HERE.parent.parent / "configs/kombyne_scripts/kombyne-save-data.yaml", d)
        s.update(output_type="kombyne", kombynelite_script_path="kombyne-save-data.yaml")
    elif backend == "ascent":
        (d / "ascent_actions.yaml").write_text(ASCENT_ACTIONS % {"t": THRESHOLD})
        (d / "ascent_options.yaml").write_text(
            'runtime:\n  type: "ascent"\n  vtkm:\n    backend: "serial"\n'
            'actions_file: "ascent_actions.yaml"\nmessages: "quiet"\n')
        s.update(output_type="ascent")
    elif backend == "adios":
        shutil.copy(HERE.parent.parent / "configs/adios2_configs/adios2.xml", d)
        s.update(output_type="adios", output_file_name="gv.bp", adios_config="adios2.xml",
                 adios_memory_selection=True)
    (d / "settings.json").write_text(json.dumps(s, indent=1))


def parse(text):
    for line in text.splitlines():
        if line.startswith("GHOSTVOL "):
            _, n, v = line.split()
            return int(n), float(v)
    raise RuntimeError("no GHOSTVOL line in output")


def ascent_count(d):
    """Owned cells (ascent_ghosts == 0) in Ascent's threshold extract."""
    import h5py
    files = sorted(d.glob(f"gv_ascent.cycle_{STEP:06d}/*.hdf5")) or [d / f"gv_ascent.cycle_{STEP:06d}.root"]
    owned = 0
    def domains(g, out):
        if "fields/ascent_ghosts/values" in g:  # a domain (the .root index has no values)
            out.append(g)
            return
        for k in g:
            if isinstance(g[k], h5py.Group):
                domains(g[k], out)
    for f in files:
        with h5py.File(f, "r") as h:
            doms = []
            domains(h, doms)
            for g in doms:
                owned += int((g["fields/ascent_ghosts/values"][()] == 0).sum())
    return owned, owned * SPACING ** 3


def adios_count(d, bpls):
    out = subprocess.run([bpls, "-d", str(d / "gv.bp"), "U", "-s", "1,0,0,0", "-c", "1,64,64,64",
                          "-f", "%.17g"], capture_output=True, text=True, check=True).stdout
    vals = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("("):
            vals.extend(float(x) for x in line.split(")", 1)[1].split())
    L = 64
    assert len(vals) == L ** 3, len(vals)
    u = lambda x, y, z: vals[(z % L) * L * L + (y % L) * L + (x % L)]  # U is [z][y][x]
    below = [v <= THRESHOLD for v in vals]
    b = lambda x, y, z: below[(z % L) * L * L + (y % L) * L + (x % L)]
    n = n_any = 0
    for z in range(L):  # periodic: L^3 cells, each owned once
        for y in range(L):
            for x in range(L):
                corners = [b(x + i, y + j, z + k) for i in (0, 1) for j in (0, 1) for k in (0, 1)]
                n += all(corners)
                n_any += any(corners)
    adios_count.any = n_any
    return n, n * SPACING ** 3


def run_backend(args):
    work = Path(args.workdir)
    # A record from an earlier run must not stand in for this one.
    (work / f"{args.backend}.json").unlink(missing_ok=True)
    results = {}
    for np_ in RANKS:
        d = work / f"{args.backend}_np{np_}"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        settings_for(args.backend, args, d)
        cmd = [args.mpiexec, "-np", str(np_)] + args.mpiexec_preflags.split() + [
            args.exe, "--settings-file=settings.json"]
        p = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=600)
        (d / "run.log").write_text(p.stdout + p.stderr)
        if p.returncode != 0:
            sys.exit(f"{args.backend} np{np_}: miniapp failed (see {d}/run.log)")
        if args.backend == "catalyst":
            n, v = parse(p.stdout + p.stderr)
        elif args.backend == "adios":
            n, v = adios_count(d, args.bpls)
        elif args.backend == "ascent":
            n, v = ascent_count(d)
        else:
            path = d / (f"gv-{STEP:04d}.pvti" if args.backend == "pvti" else f"extracts/full_grid.{STEP:06d}.vtm")
            (d / "reader.py").write_text(READER_SCRIPT % {"t": THRESHOLD})
            q = subprocess.run([args.pvpython, str(d / "reader.py"), args.backend, str(path)],
                               capture_output=True, text=True, timeout=600)
            (d / "reader.log").write_text(q.stdout + q.stderr)
            if q.returncode != 0:
                sys.exit(f"{args.backend} np{np_}: pvpython reader failed (see {d}/reader.log)")
            n, v = parse(q.stdout + q.stderr)
        results[np_] = (n, v)
        print(f"{args.backend} np{np_}: {n} cells, volume {v:.12g}")

    n1, v1 = results[1]
    ok = n1 > 0
    for np_, (n, v) in results.items():
        if n != n1 or abs(v - v1) > 1e-12 * abs(v1):
            print(f"FAIL {args.backend} np{np_}: {n} cells / {v!r} vs 1 rank {n1} / {v1!r}")
            ok = False
    if n1 == 0:
        print("FAIL: no cells below the threshold; the test would prove nothing")
    method = "analytic" if args.backend in ("adios", "ascent") else "vtk_integrate"
    rec = {"cells": n1, "volume": v1, "method": method, "rule": "any" if args.backend == "ascent" else "all"}
    if args.backend == "adios":
        rec["cells_any"] = adios_count.any
    if ok:  # only a passing run leaves a record for --compare
        (work / f"{args.backend}.json").write_text(json.dumps(rec))
    print("PASSED" if ok else "FAILED")
    return 0 if ok else 1


def compare(workdir, expect):
    """Cell counts must be equal exactly. Volumes must agree within 1e-12
    between backends integrated the same way. ParaView's integration runs
    on the threshold output, whose points are float32, so against the
    analytic count * 0.1^3 (ADIOS2) the tolerance is 1e-6."""
    res = {}
    ok = True
    if not expect:  # by hand: compare whatever records are there
        expect = sorted(p.stem for p in Path(workdir).glob("*.json"))
    for b in expect:
        p = Path(workdir) / f"{b}.json"
        if p.exists():
            res[b] = json.loads(p.read_text())
        else:
            print(f"FAIL {b}: no result record (its ghost volume test did not pass)")
            ok = False
    if len(expect) < 2:
        print(f"only {expect} configured; nothing to compare")
    # Ascent counts under the any-corner rule; check it against the ADIOS2
    # reference under the same rule, then leave it out of the all-corners table.
    if "ascent" in res:
        a = res.pop("ascent")
        print(f"ascent: {a['cells']} cells (any-corner rule)")
        if "adios" in res:
            same = a["cells"] == res["adios"]["cells_any"]
            print(("" if same else "FAIL ") + f"ascent vs adios (any corner): {a['cells']} / {res['adios']['cells_any']}")
            ok &= same
    names = sorted(res)
    for a in names:
        print(f"{a}: {res[a]['cells']} cells, volume {res[a]['volume']:.12g} ({res[a].get('method')})")
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ra, rb = res[a], res[b]
            tol = 1e-12 if ra.get("method") == rb.get("method") else 1e-6
            rel = abs(ra["volume"] - rb["volume"]) / abs(ra["volume"])
            same = ra["cells"] == rb["cells"] and rel <= tol
            if not same:
                print(f"FAIL {a} vs {b}: cells {ra['cells']} / {rb['cells']}, volume rel {rel:.3g} > {tol:g}")
            ok &= same
    print("PASSED" if ok else "FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", choices=["catalyst", "pvti", "kombyne", "adios", "ascent"])
    ap.add_argument("--compare", metavar="WORKDIR")
    ap.add_argument("--expect", default="", help="with --compare: comma-separated backends that must have results")
    ap.add_argument("--exe")
    ap.add_argument("--workdir")
    ap.add_argument("--mpiexec", default="mpirun")
    ap.add_argument("--mpiexec-preflags", default="--oversubscribe")
    ap.add_argument("--pvpython", default="pvpython")
    ap.add_argument("--catalyst-lib", default="")
    ap.add_argument("--bpls", default="bpls")
    args = ap.parse_args()
    # The miniapp runs inside a per-run directory, so relative paths given
    # on the command line must be made absolute first. Bare command names
    # (looked up on PATH) are left alone.
    for name in ("exe", "catalyst_lib", "pvpython", "bpls", "workdir"):
        v = getattr(args, name, None)
        if v and (name in ("exe", "catalyst_lib", "workdir") or "/" in v):
            setattr(args, name, os.path.abspath(v))
    if args.compare:
        return compare(args.compare, [b for b in args.expect.split(",") if b])
    if not (args.backend and args.exe and args.workdir):
        ap.error("--backend, --exe and --workdir are required")
    return run_backend(args)


if __name__ == "__main__":
    sys.exit(main())
