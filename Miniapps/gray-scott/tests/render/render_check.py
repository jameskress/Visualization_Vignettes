#!/usr/bin/env python3
"""Backend render check (#24): the same picture on every rank count.

Runs the seeded 64^3 problem to step 2000 with one backend on 1 rank and
on N ranks (default 4), renders the same views with the same camera and
fixed colour ranges, and compares the images pixel by pixel. A seam, crack,
internal face or shading line at a rank boundary shows up as pixels that
differ from the 1-rank image. The images are kept in <workdir>/<backend>/
so a person can look at them.

    render_check.py --backend catalyst --exe build/gray-scott --workdir ... [--catalyst-lib ...]

Views per backend:
  catalyst  in situ: volume of v straight from the producer, and a contour
            of v (0.15) on GhostCells(producer); the ParaView rule from
            docs/in-situ-backends.md
  ascent    in situ: volume of v (samples 1000) and a contour of v
  pvti      the .pvti output rendered in pvpython: volume and contour
  kombyne   in situ: Kombyne's iso surface of V rendered by Kombyne

Rendering is headless: ParaView uses EGL (VTK_DEFAULT_OPENGL_WINDOW), so no
X display is needed.

Pass when, for every view, at most --max-fraction of pixels (default 0.1%)
differ by more than --tolerance (default 24 of 255) from the 1-rank image.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

STEP = 2000
HERE = Path(__file__).resolve().parent
CAMERA = dict(position=[16.2, 13.2, 17.6], focus=[3.2, 3.2, 3.2], up=[-0.476, 0.863, -0.166])

PARAVIEW_VIEWS = r'''
def setup(source, contour_input):
    view = CreateView("RenderView"); view.ViewSize = [1200, 900]
    view.OrientationAxesVisibility = 0
    view.UseColorPaletteForBackground = 0; view.Background = [1, 1, 1]
    view.CameraPosition = %(position)r; view.CameraFocalPoint = %(focus)r
    view.CameraViewUp = %(up)r; view.CameraViewAngle = 30
    vd = Show(source, view); vd.Representation = "Volume"; vd.ColorArrayName = ["POINTS", "v"]
    lut = GetColorTransferFunction("v"); lut.ApplyPreset("Cool to Warm", True)
    lut.AutomaticRescaleRangeMode = "Never"; lut.RescaleTransferFunction(0.0, 0.45)
    pwf = GetOpacityTransferFunction("v"); pwf.Points = [0.0, 0.0, 0.5, 0.0, 0.45, 1.0, 0.5, 0.0]
    vd.LookupTable = lut; vd.ScalarOpacityFunction = pwf
    ct = Contour(Input=contour_input, ContourBy=["POINTS", "v"], Isosurfaces=[0.15])
    cd = Show(ct, view); cd.DiffuseColor = [0.85, 0.55, 0.2]; cd.ColorArrayName = ["POINTS", ""]
    return view, vd, cd

def save(view, vd, cd, prefix=""):
    cd.Visibility = 0; vd.Visibility = 1
    SaveScreenshot(prefix + "volume.png", view, ImageResolution=[1200, 900])
    vd.Visibility = 0; cd.Visibility = 1
    SaveScreenshot(prefix + "contour.png", view, ImageResolution=[1200, 900])
''' % CAMERA

CATALYST_SCRIPT = r'''
from paraview.simple import *
%(views)s
producer = TrivialProducer(registrationName="grid")
view, vd, cd = setup(producer, GhostCells(Input=producer))
def catalyst_execute(info):
    if info.cycle == %(step)d:
        save(view, vd, cd)
'''

PVTI_SCRIPT = r'''
import sys
from paraview.simple import *
%(views)s
r = OpenDataFile(sys.argv[1])
view, vd, cd = setup(r, GhostCells(Input=r))
save(view, vd, cd, sys.argv[2] + "/")
'''

ASCENT_ACTIONS = '''
- action: "add_pipelines"
  pipelines:
    iso:
      f1:
        type: "contour"
        params:
          field: "v"
          iso_values: 0.15
- action: "add_scenes"
  scenes:
    vol:
      plots:
        p1:
          type: "volume"
          field: "v"
          samples: 1000
          min_value: 0.0
          max_value: 0.45
          color_table:
            name: "Cool to Warm"
            control_points:
              - type: "alpha"
                position: 0.0
                alpha: 0.0
              - type: "alpha"
                position: 1.0
                alpha: 1.0
      renders:
        r1:
          image_width: 1200
          image_height: 900
          annotations: "false"
          bg_color: [1.0, 1.0, 1.0]
          image_name: "volume"
          camera:
            position: %(position)s
            look_at: %(focus)s
            up: %(up)s
            fov: 30.0
    con:
      plots:
        p1:
          type: "pseudocolor"
          pipeline: "iso"
          field: "v"
          min_value: 0.0
          max_value: 0.45
      renders:
        r1:
          image_width: 1200
          image_height: 900
          annotations: "false"
          bg_color: [1.0, 1.0, 1.0]
          image_name: "contour"
          camera:
            position: %(position)s
            look_at: %(focus)s
            up: %(up)s
            fov: 30.0
''' % CAMERA

KOMBYNE_SCRIPT = '''
pipelines:
  - type: "iso"
    enabled: "true"
    frequency: 1
    attributes:
      variable: "V"
      value: 0.15
    outputs:
      - type: "render"
        enabled: true
        file_pattern: "contour_%%ts"
        file_format: "png"
        attributes:
          width: 1200
          height: 900
          scene:
            camera:
              position: %(position)s
              focus: %(focus)s
              up: %(up)s
              fov: 30.0
            lights:
              - type: ambient
                intensity: 0.7
              - type: directional
                direction: [-1, -1, -1]
                intensity: 0.8
            pseudocolor:
              variable: "V"
              minimum: 0.0
              maximum: 0.45
              color_table: "cool to warm"
''' % CAMERA

VIEWS = {"catalyst": ["volume", "contour"], "ascent": ["volume", "contour"],
         "pvti": ["volume", "contour"], "kombyne": ["contour"]}


def headless_env():
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    env["VTK_DEFAULT_OPENGL_WINDOW"] = "vtkEGLRenderWindow"
    env["OMP_NUM_THREADS"] = env.get("OMP_NUM_THREADS", "2")
    return env


def is_open_mpi(launcher):
    try:
        v = subprocess.run([launcher, "--version"], capture_output=True, text=True, timeout=30)
        return "Open MPI" in v.stdout + v.stderr or "OpenRTE" in v.stdout + v.stderr
    except (OSError, subprocess.TimeoutExpired):
        return False


def run_group(cmd, cwd, env, timeout):
    """Run cmd in its own process group. On timeout, kill the whole group
    (mpirun and any ranks it left behind) and return (None, output)."""
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, _ = p.communicate()
        return None, out


def run(args, np_):
    d = Path(args.workdir) / args.backend / f"np{np_}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    s = json.loads((HERE.parent.parent / "configs/miniapp-settings/settings-none.json").read_text())
    s.update(steps=STEP + 1, plotgap=STEP, perf_dir="perf", checkpoint=False)
    b = args.backend
    if b == "catalyst":
        (d / "render.py").write_text(CATALYST_SCRIPT % {"views": PARAVIEW_VIEWS, "step": STEP})
        s.update(output_type="catalyst_insitu", catalyst_script_path="render.py", catalyst_lib_path=args.catalyst_lib)
    elif b == "ascent":
        (d / "ascent_actions.yaml").write_text(ASCENT_ACTIONS)
        (d / "ascent_options.yaml").write_text('runtime:\n  type: "ascent"\n  vtkm:\n    backend: "serial"\n'
                                               'actions_file: "ascent_actions.yaml"\nmessages: "quiet"\n')
        s.update(output_type="ascent")
    elif b == "pvti":
        s.update(output_type="pvti", output_file_name="rc-%04ts.vti")
    elif b == "kombyne":
        (d / "render.yaml").write_text(KOMBYNE_SCRIPT)
        s.update(output_type="kombyne", kombynelite_script_path="render.yaml")
    (d / "settings.json").write_text(json.dumps(s, indent=1))
    env = headless_env()
    cmd = [args.mpiexec, "-np", str(np_)] + args.mpiexec_preflags.split()
    # -x (forward an environment variable) is Open MPI's option; MPICH and
    # Intel MPI reject it. Local ranks inherit env either way.
    if is_open_mpi(args.mpiexec):
        cmd += ["-x", "VTK_DEFAULT_OPENGL_WINDOW", "-x", "OMP_NUM_THREADS"]
    rc, out = run_group(cmd + [args.exe, "--settings-file=settings.json"], d, env, 1200)
    (d / "run.log").write_text(out)
    if rc is None:
        sys.exit(f"{b} np{np_}: miniapp timed out after 1200 s; killed (see {d}/run.log)")
    if rc != 0:
        sys.exit(f"{b} np{np_}: miniapp failed (see {d}/run.log)")
    if b == "pvti":
        (d / "render.py").write_text(PVTI_SCRIPT % {"views": PARAVIEW_VIEWS})
        q = subprocess.run([args.pvpython, str(d / "render.py"), str(d / f"rc-{STEP:04d}.pvti"), str(d)],
                           env=env, capture_output=True, text=True, timeout=600)
        (d / "render.log").write_text(q.stdout + q.stderr)
        if q.returncode != 0:
            sys.exit(f"{b} np{np_}: pvpython render failed (see {d}/render.log)")
    # Normalise names: <view>.png for the output step. Catalyst, Ascent and
    # PVTI write <view>.png at the output step only; Kombyne writes one file
    # per output step, so take the one named for STEP and nothing else.
    for v in VIEWS[b]:
        if not (d / f"{v}.png").exists():
            hits = sorted(h for h in d.glob(f"{v}_*.png") if h.stem.split("_")[-1].lstrip("0") == str(STEP))
            if len(hits) != 1:
                sys.exit(f"{b} np{np_}: no {v} image for step {STEP} (see {d})")
            shutil.copy(hits[0], d / f"{v}.png")
    return d


def compare(a, b, tol):
    from PIL import Image
    import numpy as np
    x = np.asarray(Image.open(a).convert("RGB")).astype(int)
    y = np.asarray(Image.open(b).convert("RGB")).astype(int)
    if x.shape != y.shape:
        return 1.0, 255, 0.0
    diff = np.abs(x - y).max(axis=2)
    filled = float((x.min(axis=2) < 245).mean() if x.mean() > 128 else (x.max(axis=2) > 10).mean())
    return float((diff > tol).mean()), int(diff.max()), filled


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", required=True, choices=sorted(VIEWS))
    ap.add_argument("--exe", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--ranks", type=int, default=4)
    ap.add_argument("--mpiexec", default="mpirun")
    ap.add_argument("--mpiexec-preflags", default="--oversubscribe")
    ap.add_argument("--pvpython", default="pvpython")
    ap.add_argument("--catalyst-lib", default="")
    ap.add_argument("--tolerance", type=int, default=24)
    ap.add_argument("--max-fraction", type=float, default=0.001)
    args = ap.parse_args()
    d1 = run(args, 1)
    dn = run(args, args.ranks)
    ok = True
    for v in VIEWS[args.backend]:
        frac, mx, filled = compare(d1 / f"{v}.png", dn / f"{v}.png", args.tolerance)
        bad = frac > args.max_fraction or filled < 0.05
        print(f"{'FAIL ' if bad else ''}{args.backend} {v}: np{args.ranks} vs np1 {100 * frac:.3f}% of pixels "
              f"differ by more than {args.tolerance}/255 (max {mx}); image {100 * filled:.0f}% covered")
        ok &= not bad
    print("PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
