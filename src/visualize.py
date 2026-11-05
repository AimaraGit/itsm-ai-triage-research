"""Scientific figures for the ITSM benchmark."""

from pathlib import Path
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from src.process_data import bootstrap_ci


def _save_figure(fig: plt.Figure, output_path: Path) -> Tuple[Path, Path]:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path = output_path.with_suffix(".pdf")
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return pdf_path, output_path


def plot_latency_vs_load(
    summary: pd.DataFrame,
    output_path: Path = Path("reports/figures/fig1_latency_vs_load.png"),
) -> Tuple[Path, Path]:
    """Plot latency percentiles and bootstrap CIs against input size."""
    if "workload_kind" not in summary or "load_bin" not in summary:
        raise ValueError("Summary must include workload_kind and load_bin")
    data = summary.loc[
        summary["workload_kind"].eq("pareto") & summary["load_bin"].gt(0)
    ].sort_values("n_rows_median")
    if data.empty:
        raise ValueError("No Pareto workload summaries are available for the load plot")

    sns.set_theme(style="whitegrid", font_scale=1.1)
    fig, ax = plt.subplots(figsize=(7.2, 4.6), constrained_layout=True)
    colors = sns.color_palette("colorblind", 3)
    series = (
        ("latency_p50_ms", "latency_p50_ci95_low_ms", "latency_p50_ci95_high_ms",
         "p50", "-", "o"),
        ("latency_p95_ms", "latency_p95_ci95_low_ms", "latency_p95_ci95_high_ms",
         "p95", "--", "s"),
        ("latency_p99_ms", "latency_p99_ci95_low_ms", "latency_p99_ci95_high_ms",
         "p99", ":", "^"),
    )
    x = data["n_rows_median"].to_numpy(dtype=float)
    for color, (value, low, high, label, linestyle, marker) in zip(colors, series):
        y = data[value].to_numpy(dtype=float)
        lower = data[low].to_numpy(dtype=float)
        upper = data[high].to_numpy(dtype=float)
        ax.fill_between(x, lower, upper, color=color, alpha=0.14, linewidth=0)
        ax.plot(
            x, y, color=color, linestyle=linestyle, marker=marker,
            markersize=6, linewidth=1.8, label=label,
        )

    ax.set_xlabel("Input size (cases per analysis call)")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Analysis latency by workload size")
    ax.set_xticks(x)
    ax.tick_params(axis="x", labelrotation=25)
    ax.legend(title="Latency percentile")
    ax.text(
        0.01, 0.98,
        "Bands: 95% percentile-bootstrap CI; p99 is indicative (<1,000 runs).",
        transform=ax.transAxes, ha="left", va="top", fontsize=8,
    )
    values = data[["latency_p50_ms", "latency_p95_ms", "latency_p99_ms"]].to_numpy()
    positive = values[np.isfinite(values) & (values > 0)]
    if len(positive) and positive.max() / positive.min() >= 100:
        ax.set_yscale("log")
    else:
        ax.set_ylim(bottom=0)
    return _save_figure(fig, Path(output_path))


def plot_latency_distribution(
    evaluation_runs: pd.DataFrame,
    output_path: Path = Path("reports/figures/fig2_distribution_boxplot.png"),
    bootstrap_samples: int = 2000,
    seed: int = 42,
) -> Tuple[Path, Path]:
    """Show successful-run distributions and median CIs by workload shape."""
    required = {"status", "latency_ms", "workload_kind"}
    missing = required - set(evaluation_runs.columns)
    if missing:
        raise ValueError(f"Evaluation data is missing fields: {sorted(missing)}")
    data = evaluation_runs.loc[
        evaluation_runs["status"].eq("success")
        & np.isfinite(evaluation_runs["latency_ms"])
    ].copy()
    if data.empty:
        raise ValueError("No successful evaluation latencies are available to plot")

    categories = sorted(data["workload_kind"].unique())
    palette = sns.color_palette("colorblind", len(categories))
    sns.set_theme(style="whitegrid", font_scale=1.05)
    fig, ax = plt.subplots(figsize=(8.4, 4.8), constrained_layout=True)
    grouped_values = [
        data.loc[data["workload_kind"].eq(kind), "latency_ms"].to_numpy()
        for kind in categories
    ]
    positions = np.arange(1, len(categories) + 1)
    boxes = ax.boxplot(
        grouped_values,
        positions=positions,
        widths=0.58,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "black", "linewidth": 1.4},
        whiskerprops={"color": "0.35"},
        capprops={"color": "0.35"},
    )
    for box, color in zip(boxes["boxes"], palette):
        box.set_facecolor(color)
        box.set_alpha(0.65)
    for index, values in enumerate(grouped_values, start=1):
        jitter = np.random.default_rng(seed + index).uniform(-0.10, 0.10, len(values))
        ax.scatter(
            np.full(len(values), index) + jitter, values,
            color="black", marker="o", s=20, alpha=0.55,
            label="Successful runs" if index == 1 else None,
            zorder=3,
        )

    centers = []
    medians = []
    lows = []
    highs = []
    for index, values in enumerate(grouped_values):
        low, high = bootstrap_ci(
            values, resamples=bootstrap_samples, seed=seed + index
        )
        centers.append(index + 1)
        medians.append(float(np.median(values)))
        lows.append(max(0.0, medians[-1] - low))
        highs.append(max(0.0, high - medians[-1]))
    ax.errorbar(
        centers, medians, yerr=np.asarray([lows, highs]),
        fmt="D", color="black", markerfacecolor="white", markeredgewidth=1.2,
        capsize=3, linewidth=1.2, label="Median, 95% bootstrap CI",
    )
    counts = {kind: len(values) for kind, values in zip(categories, grouped_values)}
    ax.set_xticks(positions)
    ax.set_xticklabels(
        [f"{kind}\n(n={counts[kind]})" for kind in categories],
        rotation=20, ha="right",
    )
    ax.set_xlabel("Synthetic workload shape")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Successful analysis latency distributions")
    ax.set_ylim(bottom=0)
    ax.legend(loc="best")
    ax.text(
        0.01, 0.98,
        "Boxes: p25–p75; whiskers: 1.5×IQR; diamonds: median and 95% bootstrap CI.\n"
        "Expected and unexpected failures are retained in the guardrail table, not plotted.",
        transform=ax.transAxes, ha="left", va="top", fontsize=8,
    )
    return _save_figure(fig, Path(output_path))


def generate_figures(
    evaluation_runs: pd.DataFrame,
    summary: pd.DataFrame,
    output_dir: Path = Path("reports/figures"),
    bootstrap_samples: int = 2000,
    seed: int = 42,
) -> Tuple[Tuple[Path, Path], Tuple[Path, Path]]:
    """Write both required figures as vector PDF and 300-DPI PNG."""
    output_dir = Path(output_dir)
    latency = plot_latency_vs_load(
        summary, output_dir / "fig1_latency_vs_load.png"
    )
    distribution = plot_latency_distribution(
        evaluation_runs, output_dir / "fig2_distribution_boxplot.png",
        bootstrap_samples, seed,
    )
    return latency, distribution
