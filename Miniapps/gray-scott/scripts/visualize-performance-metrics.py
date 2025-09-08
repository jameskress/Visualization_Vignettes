#!/usr/bin/env python3
import os, glob
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import argparse


def main(timer_dir, output_file):
    # Collect CSVs
    csv_files = glob.glob(os.path.join(timer_dir, "*.csv"))
    if not csv_files:
        print(f"Error: No CSV files found in directory '{timer_dir}'.")
        return

    dfs = []
    for f in csv_files:
        df = pd.read_csv(f)
        dfs.append(df)

    # Concatenate
    df_all = pd.concat(dfs, ignore_index=True)

    # Identify columns
    all_cols = df_all.columns.tolist()
    # This logic dynamically finds all timers by excluding known stat columns
    timer_cols = [
        c
        for c in all_cols
        if c
        not in ["step", "rank", "hostname", "rss_MB", "user_s", "sys_s", "total_step"]
    ]
    stat_cols = ["rss_MB", "user_s", "sys_s"]

    # Compute per-step CPU deltas
    df_all = df_all.sort_values(["rank", "step"]).copy()
    for col in ["user_s", "sys_s"]:
        df_all[col + "_delta"] = df_all.groupby("rank")[col].diff().fillna(df_all[col])

    # -----------------------------
    # 1) Timer line plot with min/max shading
    # -----------------------------
    fig, axs = plt.subplots(4, 1, figsize=(12, 18), constrained_layout=True)
    fig.suptitle(f"Performance Analysis from: {timer_dir}", fontsize=16)

    colors = plt.get_cmap("tab10")
    color_map = {name: colors(i) for i, name in enumerate(timer_cols)}

    ax = axs[0]
    for i, t in enumerate(timer_cols):
        grouped = df_all.groupby("step")[t]
        mean_vals = grouped.mean()
        min_vals = grouped.min()
        max_vals = grouped.max()
        ax.plot(
            mean_vals.index.to_numpy(),
            mean_vals.to_numpy(),
            label=t,
            color=color_map[t],
            marker="o",
            markersize=3,
        )
        ax.fill_between(
            mean_vals.index.to_numpy(),
            min_vals.to_numpy(),
            max_vals.to_numpy(),
            color=color_map[t],
            alpha=0.2,
        )

    ax.set_ylabel("Time (s)")
    ax.set_title("Timers per Step (mean ± min/max across ranks)")
    ax.legend()
    ax.grid(True)

    # -----------------------------
    # 2) Stacked bar chart (mean only)
    # -----------------------------
    ax = axs[1]
    bottom = np.zeros(len(mean_vals))
    for t in timer_cols:
        mean_vals = df_all.groupby("step")[t].mean()
        ax.bar(
            mean_vals.index.to_numpy(),
            mean_vals.to_numpy(),
            bottom=bottom,
            color=color_map[t],
            label=t,
        )
        bottom += mean_vals.to_numpy()

    ax.set_ylabel("Time (s)")
    ax.set_title("Timers (stacked, mean across ranks)")
    ax.legend()
    ax.grid(True)

    # -----------------------------
    # 3) System stats with two y-axes
    # -----------------------------
    ax_rss = axs[2]
    ax_cpu = axs[2].twinx()

    # RSS
    rss_mean = df_all.groupby("step")["rss_MB"].mean()
    ax_rss.plot(
        rss_mean.index.to_numpy(),
        rss_mean.to_numpy(),
        label="RSS (MB)",
        color="tab:blue",
        marker="o",
        markersize=3,
    )
    ax_rss.set_ylabel("RSS (MB)", color="tab:blue")
    ax_rss.tick_params(axis="y", labelcolor="tab:blue")

    # CPU deltas
    user_mean = df_all.groupby("step")["user_s_delta"].mean()
    sys_mean = df_all.groupby("step")["sys_s_delta"].mean()
    ax_cpu.plot(
        user_mean.index.to_numpy(),
        user_mean.to_numpy(),
        label="user_s",
        color="tab:orange",
        marker="s",
        markersize=3,
    )
    ax_cpu.plot(
        sys_mean.index.to_numpy(),
        sys_mean.to_numpy(),
        label="sys_s",
        color="tab:green",
        marker="^",
        markersize=3,
    )
    ax_cpu.set_ylabel("CPU Time (s)", color="black")
    ax_cpu.tick_params(axis="y", labelcolor="black")

    lines_rss, labels_rss = ax_rss.get_legend_handles_labels()
    lines_cpu, labels_cpu = ax_cpu.get_legend_handles_labels()
    ax_rss.legend(lines_rss + lines_cpu, labels_rss + labels_cpu, loc="upper left")
    ax_rss.set_xlabel("Step")
    ax_rss.set_title("System Stats per Step")
    ax_rss.grid(True)

    # -----------------------------
    # 4) Total step time by rank
    # -----------------------------
    ax = axs[3]
    for rank, grp in df_all.groupby("rank"):
        ax.plot(
            grp["step"].to_numpy(),
            grp["total_step"].to_numpy(),
            label=f"Rank {rank}",
            marker="o",
            markersize=2,
        )
    ax.set_xlabel("Step")
    ax.set_ylabel("Total Step Time (s)")
    ax.set_title("Total Step Time by Rank")
    if (
        len(df_all["rank"].unique()) <= 10
    ):  # Only show legend if there aren't too many ranks
        ax.legend()
    ax.grid(True)

    # Save the final figure
    fig.savefig(output_file, dpi=300)
    print(f"Successfully generated performance plot: {output_file}")

    # Show the interactive plot window
    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Visualize performance timer data from Gray-Scott simulation or reader."
    )
    parser.add_argument(
        "-i",
        "--input-dir",
        default="writer_timers",
        help="Directory containing the timer CSV files (e.g., 'writer_timers' for sim, 'reader_timers' for reader).",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        default="timers_summary.png",
        help="Name of the output PNG image file.",
    )
    args = parser.parse_args()

    main(args.input_dir, args.output_file)
