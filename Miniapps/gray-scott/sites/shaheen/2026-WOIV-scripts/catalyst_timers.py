#!/usr/bin/env python3
"""Named Catalyst stage timers from ParaView's per-rank scoped logs.

The reader's Vis_Time covers all of catalyst_execute. With GS_CATALYST_TIMERS=1
each reader rank writes ParaView's own log to catalyst_timers/rank_<r>.log
(generate_experiments.py, CATALYST_TIMERS_PROLOGUE). This script turns the
timed scopes in those logs into one row per step:

  execute     catalyst_execute_paraview: all of it (the reader's Vis_Time)
  overhead    execute minus co-processing: the Blueprint check and Catalyst's
              bookkeeping. The conversion to VTK is not here: it is zero-copy
              and runs inside co-processing, as part of update.
  update      RenderView update: the filters (slices, contour) and geometry
  render      RenderView StillRender: the whole render
  icet_pass   IceT's composite pass, which draws the local image inside it
  icet_render ICET_RENDER_TIME: the local (OSPRay) render inside IceT
  icet_composite ICET_COMPOSITE_TIME: the composite, waits for peers included
  capture     Capture image: update, render and the read back
  png_write   Save captured image (rank 0 only)

Each timer is reported as its mean and maximum over the ranks that logged
it. Step numbers are Catalyst's timestep (the reader's output step). The
log opens while the script is imported, inside the first step and after
ParaView has logged that step's number, so scopes before the first number in
the file are counted to the step before it. That first step's row is partial
(only the scopes that closed after the log opened) and also holds the
pipeline's start-up; compare steps 1 and up. A log with no step number at
all (a run with one output) reports its scopes as step -1.

usage: catalyst_timers.py LOG_DIR OUTPUT_CSV
"""
import csv
import re
import sys
from pathlib import Path

SCOPES = [
    ("execute", re.compile(r"\} ([0-9.]+) s: catalyst_execute_paraview$")),
    ("coprocess", re.compile(r"\} ([0-9.]+) s: co-processing for timestep=")),
    ("update", re.compile(r"\} ([0-9.]+) s: \S+: update view$")),
    ("render", re.compile(r"\} ([0-9.]+) s: \S+: StillRender$")),
    ("icet_pass", re.compile(r"\} ([0-9.]+) s: vtkIceTCompositePass \(\S+\): Render$")),
    ("icet_render", re.compile(r"ICET_RENDER_TIME: ([0-9.]+)$")),
    ("icet_composite", re.compile(r"ICET_COMPOSITE_TIME: ([0-9.]+)$")),
    ("capture", re.compile(r"\} ([0-9.]+) s: Capture image$")),
    ("png_write", re.compile(r"\} ([0-9.]+) s: Save captured image")),
]
STEP = re.compile(r"'timestep' set to (\d+)")
TIMERS = [
    "execute",
    "overhead",
    "update",
    "render",
    "icet_pass",
    "icet_render",
    "icet_composite",
    "capture",
    "png_write",
]


def parse(path):
    """{step: {timer: seconds}} for one rank. Scopes repeated within a step
    (one update per view, say) are summed."""
    steps, step = {}, None
    pending = {}  # scopes logged before the first step number in the file
    with open(path, errors="replace") as f:
        for line in f:
            line = line.rstrip()
            m = STEP.search(line)
            if m:
                step = int(m.group(1))
                if pending and not steps and step > 0:
                    steps[step - 1] = pending
                steps.setdefault(step, {})
                continue
            for name, pat in SCOPES:
                m = pat.search(line)
                if m:
                    t = pending if step is None else steps[step]
                    t[name] = t.get(name, 0.0) + float(m.group(1))
                    break
    if pending and not steps:
        # No step number after the log opened (a run with one output): the
        # step is unknown, so report its scopes as step -1.
        steps[-1] = pending
    for t in steps.values():
        if "execute" in t and "coprocess" in t:
            t["overhead"] = t["execute"] - t["coprocess"]
    return steps


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    logs = sorted(Path(sys.argv[1]).glob("rank_*.log"))
    if not logs:
        sys.exit(f"{sys.argv[1]}: no rank_*.log files")
    per_step = {}
    for log in logs:
        for step, t in parse(log).items():
            for name, v in t.items():
                per_step.setdefault(step, {}).setdefault(name, []).append(v)
    if not per_step:
        sys.exit(
            f"{sys.argv[1]}: no timed steps (were the PARAVIEW_LOG_*_VERBOSITY categories on?)"
        )
    cols = ["step", "ranks"] + [f"{n}_{s}" for n in TIMERS for s in ("mean", "max")]
    with open(sys.argv[2], "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for step in sorted(per_step):
            t = per_step[step]
            row = [step, len(t.get("execute", []))]
            for n in TIMERS:
                v = t.get(n)
                row += [f"{sum(v) / len(v):.6f}", f"{max(v):.6f}"] if v else ["", ""]
            w.writerow(row)
    print(f"{len(logs)} rank logs, {len(per_step)} steps -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
