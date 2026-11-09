#!/usr/bin/env python3
"""Turn Gray-Scott run directories into tables and plots.

Each run directory is what the miniapp writes under settings.perf_dir
(metadata.json, summary.json and, with timers on, steps/rank_*.jsonl; see
README.md, Performance). Pass run directories or any directories above
them:

    python3 scripts/perf_report.py perf/ --out perf_report

Writes to --out:
    summary.md, summary.csv   one row per run: problem, ranks, ms/step and
                              the mean per-step time of each phase
    phases.png                per-phase stacked bars, one bar per run
                              (runs built with ENABLE_TIMERS only)
    scaling.png               loop ms/step against ranks, one line per
                              backend and grid size, with ideal scaling
    captions.md               the metadata behind both figures

Needs matplotlib for the plots; the tables need only the standard library.
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

SCHEMA_VERSIONS = {1, 2}  # 2 adds the allocation counters (#25); 1 still reads fine

# Phases stacked in the bar chart, bottom to top. "other" is total_step minus
# their sum: barriers, logging and anything not yet timed.
PHASES = ["stencil", "halo", "wrap", "execute", "io"]
# Okabe-Ito, a colour-blind safe categorical palette, in fixed order.
COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#999999"]


def find_runs(paths):
    runs = []
    for p in paths:
        p = Path(p)
        if (p / "metadata.json").is_file():
            runs.append(p)
        else:
            runs.extend(sorted(m.parent for m in p.rglob("metadata.json")))
    return runs


def load_run(d):
    """One run directory, or None if its files cannot be read (a run killed
    while writing summary.json leaves it truncated)."""
    try:
        meta = json.loads((d / "metadata.json").read_text())
        summ_path = d / "summary.json"
        summ = json.loads(summ_path.read_text()) if summ_path.is_file() else {}
    except (OSError, ValueError) as e:
        print(f"warning: {d}: skipped, cannot read its metadata or summary ({e})", file=sys.stderr)
        return None
    v = meta.get("schema_version")
    if v not in SCHEMA_VERSIONS:
        print(f"warning: {d}: schema_version {v} not understood (knows {sorted(SCHEMA_VERSIONS)})",
              file=sys.stderr)
    return {"dir": d, "meta": meta, "summary": summ}


def row_for(run):
    m, s = run["meta"], run["summary"]
    prob, mpi, backend = m.get("problem", {}), m.get("mpi", {}), m.get("backend", {})
    timers = s.get("timers", {})

    def per_step(name):
        return timers.get(name, {}).get("per_step_ms_mean", "")

    row = {
        "run": run["dir"].name,
        "backend": backend.get("output_type", "?"),
        "backend_version": backend.get("version", ""),
        "ranks": mpi.get("ranks", s.get("ranks", "")),
        "decomposition": "x".join(str(x) for x in mpi.get("decomposition", [])),
        "L": prob.get("L", ""),
        "steps": s.get("steps_run", prob.get("steps", "")),
        "plotgap": prob.get("plotgap", ""),
        "ms_per_step": s.get("loop_wall_per_step_ms", ""),
        "timers": s.get("timers_enabled", False),
    }
    for ph in PHASES + ["total_step"]:
        row[f"{ph}_ms"] = per_step(ph)
    row["step_imbalance"] = timers.get("total_step", {}).get("imbalance", "")
    halo = s.get("counters", {}).get("halo_bytes", {}).get("per_rank_max")
    steps = s.get("steps_run") or 0
    row["halo_MB_per_step_max_rank"] = halo / steps / 1e6 if halo and steps else ""
    row["rss_MB_max"] = s.get("rss_high_water_MB", {}).get("max", "")
    row["commit"] = m.get("git", {}).get("describe", "")
    return row


def fmt(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def write_tables(rows, out):
    cols = list(rows[0].keys())
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    show = ["run", "backend", "ranks", "decomposition", "L", "steps", "ms_per_step",
            "stencil_ms", "halo_ms", "wrap_ms", "execute_ms", "io_ms", "step_imbalance"]
    lines = ["| " + " | ".join(show) + " |", "|" + "---|" * len(show)]
    for r in rows:
        lines.append("| " + " | ".join(fmt(r[c]) for c in show) + " |")
    text = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(text)
    return text


def common_caption(runs):
    """Metadata shared by every run, and what differs, for figure captions."""
    def keyset(run):
        m = run["meta"]
        return {
            "host": ", ".join(m.get("host", {}).get("hostnames", [])[:3]),
            "cpu": m.get("host", {}).get("cpu_model", "?"),
            "compiler": f'{m.get("build", {}).get("compiler_id", "?")} '
                        f'{m.get("build", {}).get("compiler_version", "")} '
                        f'{m.get("build", {}).get("cxx_flags", "")}',
            "mpi": m.get("mpi", {}).get("library_version", "?").split(",")[0],
            "commit": m.get("git", {}).get("describe", "?"),
        }
    sets = [keyset(r) for r in runs]
    parts = []
    for k in sets[0]:
        vals = sorted({s[k] for s in sets})
        parts.append(f"{k}: {vals[0]}" if len(vals) == 1 else f"{k}: {len(vals)} values ({'; '.join(vals)})")
    return "; ".join(parts)


def plot_phases(runs, rows, out, caption):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    timed = [(r, row) for r, row in zip(runs, rows) if row["timers"] and row["total_step_ms"] != ""]
    if not timed:
        return None
    labels = [f'{row["backend"]}\n{row["ranks"]} ranks\nL={row["L"]}' for _, row in timed]
    fig, ax = plt.subplots(figsize=(max(6, 1.3 * len(timed) + 2), 5))
    bottom = [0.0] * len(timed)
    for i, ph in enumerate(PHASES + ["other"]):
        if ph == "other":
            vals = [max(0.0, row["total_step_ms"] - sum(row[f"{p}_ms"] or 0 for p in PHASES))
                    for _, row in timed]
        else:
            vals = [row[f"{ph}_ms"] or 0.0 for _, row in timed]
        if not any(vals):
            continue
        ax.bar(range(len(timed)), vals, bottom=bottom, color=COLORS[i], label=ph,
               edgecolor="white", linewidth=1)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_xticks(range(len(timed)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("mean time per step per rank (ms)")
    ax.set_title("Where a step's time goes")
    ax.legend(frameon=False, fontsize=8, ncol=3)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    fig.text(0.01, 0.01, caption, fontsize=6, wrap=True, va="bottom")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    path = out / "phases.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_scaling(rows, out, caption):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    groups = defaultdict(dict)
    for row in rows:
        if row["ms_per_step"] == "" or row["ranks"] == "":
            continue
        # Runs with a different plotgap or step count do different output
        # work per step; only like runs share a line.
        key = (row["backend"], row["L"], row["plotgap"], row["steps"])
        # Several runs at one rank count: keep the fastest (least noise).
        prev = groups[key].get(row["ranks"])
        groups[key][row["ranks"]] = min(prev, row["ms_per_step"]) if prev else row["ms_per_step"]
    groups = {k: v for k, v in groups.items() if len(v) >= 2}
    if not groups:
        return None
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for i, ((backend, L, plotgap, steps), pts) in enumerate(sorted(groups.items(), key=lambda kv: tuple(map(str, kv[0])))):
        ranks = sorted(pts)
        ms = [pts[r] for r in ranks]
        color = COLORS[i % len(COLORS)]
        ax.plot(ranks, ms, marker="o", color=color, linewidth=2, label=f"{backend}, L={L}, plotgap {plotgap}, {steps} steps")
        ax.plot(ranks, [ms[0] * ranks[0] / r for r in ranks], linestyle="--", color=color,
                alpha=0.5, linewidth=1)
    from matplotlib.ticker import LogLocator, NullFormatter, ScalarFormatter
    all_ranks = sorted({r for pts in groups.values() for r in pts})
    ax.set_xscale("log", base=2)
    ax.set_xticks(all_ranks)
    ax.set_xticklabels([str(r) for r in all_ranks])
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(LogLocator(subs=(1.0, 2.0, 5.0)))
    ax.yaxis.set_major_formatter(ScalarFormatter())
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("MPI ranks")
    ax.set_ylabel("loop wall time per step (ms)")
    ax.set_title("Strong scaling (dashed: ideal)")
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.3, which="both")
    fig.text(0.01, 0.01, caption, fontsize=6, wrap=True, va="bottom")
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    path = out / "scaling.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="run directories, or directories containing them")
    ap.add_argument("--out", default="perf_report", help="output directory (default perf_report)")
    ap.add_argument("--no-plots", action="store_true", help="tables only")
    args = ap.parse_args()

    dirs = find_runs(args.paths)
    if not dirs:
        sys.exit("no run directories (with metadata.json) found")
    runs = [r for r in (load_run(d) for d in dirs) if r is not None]
    if not runs:
        sys.exit("no readable run directories found")
    runs.sort(key=lambda r: (r["meta"].get("backend", {}).get("output_type", ""),
                             r["meta"].get("problem", {}).get("L", 0),
                             r["meta"].get("mpi", {}).get("ranks", 0), r["dir"].name))
    rows = [row_for(r) for r in runs]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(write_tables(rows, out))

    if not args.no_plots:
        try:
            import matplotlib  # noqa: F401  (only the plots need it)
        except ImportError:
            print("matplotlib not found: tables written, plots skipped (install it, or pass --no-plots)",
                  file=sys.stderr)
            args.no_plots = True
    if not args.no_plots:
        caption = common_caption(runs)
        made = [p for p in (plot_phases(runs, rows, out, caption), plot_scaling(rows, out, caption)) if p]
        (out / "captions.md").write_text(
            "Runs: " + ", ".join(str(r["dir"]) for r in runs) + "\n\n" + caption + "\n")
        for p in made:
            print(f"wrote {p}")
    print(f"wrote {out / 'summary.md'}, {out / 'summary.csv'}")


if __name__ == "__main__":
    main()
