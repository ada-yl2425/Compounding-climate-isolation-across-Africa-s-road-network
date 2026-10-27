#!/usr/bin/env python3
"""
Result 1.2 split figures:
1) pair-level scatter as the main figure
2) ECDF as a separate figure

Both figures inherit the same color palette and typography as the latest
scatter version, and are exported with transparent backgrounds.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MPLCONFIG_DIR = Path(__file__).resolve().parent / "_mplconfig"
MPLCONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator, PercentFormatter

FONT_SIZE = 9.0
THRESHOLD = 50.0
PNG_DPI = 600

SCATTER_WIDTH_CM = 5.0
SCATTER_HEIGHT_CM = 6.4
ECDF_WIDTH_CM = 5.0
ECDF_HEIGHT_CM = 4.2

PAIR_COLOR = "#4e79a7"
MEAN_COLOR = "#c45d4f"
FIT_COLOR = "#7b3f3f"
ONE_TO_ONE_COLOR = "#8d8d8d"
ECDF_COLOR = "#1f5a92"
GRID_COLOR = "#dadada"
TEXT_COLOR = "#222222"


SCRIPT_PATH = Path(__file__).resolve()
OUT_DIR = SCRIPT_PATH.parent
PROJECT_ROOT = SCRIPT_PATH.parents[2]
RESULT1_DIR = PROJECT_ROOT / "process_files" / "result" / "result1"

PAIR_CSV = (
    RESULT1_DIR
    / "finding3_4_city_pair_travel_time_cumulative"
    / "within_country_city_pairs_travel_time_normal_vs_extreme.csv"
)
COUNTRY_STATS_CSV = (
    RESULT1_DIR
    / "finding5_city_district_speed_efficiency_spatial"
    / "city_district_stats_by_country.csv"
)

SCATTER_PNG = OUT_DIR / "result1_2_pair_scatter_transparent.png"
SCATTER_PDF = OUT_DIR / "result1_2_pair_scatter_transparent.pdf"
ECDF_PNG = OUT_DIR / "result1_2_pair_ecdf_transparent.png"
ECDF_PDF = OUT_DIR / "result1_2_pair_ecdf_transparent.pdf"
CHECKS_PATH = OUT_DIR / "result1_2_pair_scatter_ecdf_split_checks.txt"
PAIR_JOIN_PATH = OUT_DIR / "result1_2_pair_scatter_joined.csv"
COUNTRY_MEAN_PATH = OUT_DIR / "result1_2_pair_scatter_country_means.csv"


class Logger:
    def __init__(self, path: Path) -> None:
        self.handle = path.open("w", encoding="utf-8")

    def log(self, msg: str = "") -> None:
        print(msg)
        self.handle.write(f"{msg}\n")
        self.handle.flush()

    def close(self) -> None:
        self.handle.close()


def cm_to_inch(value_cm: float) -> float:
    return value_cm / 2.54


def set_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "font.size": FONT_SIZE,
            "axes.labelsize": FONT_SIZE,
            "xtick.labelsize": FONT_SIZE,
            "ytick.labelsize": FONT_SIZE,
            "legend.fontsize": FONT_SIZE - 0.7,
            "axes.linewidth": 0.85,
            "xtick.major.width": 0.8,
            "ytick.major.width": 0.8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.facecolor": "none",
            "axes.unicode_minus": False,
        }
    )


def load_data(logger: Logger) -> tuple[pd.DataFrame, pd.DataFrame]:
    pairs = pd.read_csv(PAIR_CSV)
    stats = pd.read_csv(COUNTRY_STATS_CSV)

    logger.log("[Inputs]")
    logger.log(f"Pair table rows: {len(pairs):,}")
    logger.log(f"Country stats rows: {len(stats):,}")

    if "increase_pct" not in pairs.columns:
        raise KeyError("Pair table lacks increase_pct.")
    if "road_deg_mean" not in stats.columns:
        raise KeyError("Country stats table lacks road_deg_mean.")

    pairs["increase_pct"] = pd.to_numeric(pairs["increase_pct"], errors="coerce")
    stats["road_deg_mean"] = pd.to_numeric(stats["road_deg_mean"], errors="coerce")
    return pairs, stats


def prepare_data(
    logger: Logger, pairs: pd.DataFrame, stats: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    valid_pairs = pairs.loc[pairs["increase_pct"].notna()].copy()
    joined = valid_pairs.merge(
        stats[["country", "road_deg_mean"]], on="country", how="inner"
    )
    joined = joined.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["increase_pct", "road_deg_mean"]
    )

    country_means = joined.groupby("country", as_index=False).agg(
        road_deg_mean=("road_deg_mean", "first"),
        mean_increase_pct=("increase_pct", "mean"),
        n_pairs=("increase_pct", "size"),
    )

    severe_share = float((joined["increase_pct"] > THRESHOLD).mean() * 100.0)
    pooled_mean_inc = float(joined["increase_pct"].mean())
    pooled_mean_road = float(joined["road_deg_mean"].mean())

    logger.log("\n[Summary values]")
    logger.log(f"Final pair-level sample: {len(joined):,}")
    logger.log(f"Country means sample: {len(country_means):,}")
    logger.log(f"Pooled mean travel-time increase: {pooled_mean_inc:.4f}%")
    logger.log(f"Pooled mean road-speed loss: {pooled_mean_road:.4f}%")
    logger.log(f"Amplification factor: {pooled_mean_inc / pooled_mean_road:.4f}x")
    logger.log(f"Share of pairs > 50% increase: {severe_share:.4f}%")

    joined.to_csv(PAIR_JOIN_PATH, index=False)
    country_means.to_csv(COUNTRY_MEAN_PATH, index=False)
    logger.log(f"Saved joined pair data: {PAIR_JOIN_PATH}")
    logger.log(f"Saved country means: {COUNTRY_MEAN_PATH}")
    return joined, country_means


def size_scale(n_pairs: pd.Series) -> np.ndarray:
    root = np.sqrt(n_pairs.to_numpy(dtype=float))
    return np.interp(root, (root.min(), root.max()), (35, 160))


def style_axes(ax: plt.Axes) -> None:
    ax.set_facecolor("none")
    ax.grid(color=GRID_COLOR, lw=0.6, alpha=0.72)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(length=3.2, pad=1.5)


def save_figure(fig: plt.Figure, png_path: Path, pdf_path: Path) -> None:
    fig.savefig(
        png_path, dpi=PNG_DPI, transparent=True, bbox_inches="tight", pad_inches=0.03
    )
    fig.savefig(pdf_path, transparent=True, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


def plot_scatter(
    joined: pd.DataFrame, country_means: pd.DataFrame, logger: Logger
) -> None:
    fig, ax = plt.subplots(
        figsize=(cm_to_inch(SCATTER_WIDTH_CM), cm_to_inch(SCATTER_HEIGHT_CM))
    )
    fig.patch.set_alpha(0.0)
    fig.subplots_adjust(left=0.24, right=0.985, bottom=0.31, top=0.98)
    style_axes(ax)

    x = joined["road_deg_mean"].to_numpy()
    y = joined["increase_pct"].to_numpy()

    ax.scatter(
        x,
        y,
        s=4.5,
        color=PAIR_COLOR,
        alpha=0.15,
        linewidths=0,
        rasterized=True,
        zorder=1,
    )

    one_to_one_x = np.linspace(0, max(20, float(np.nanmax(x)) * 1.05), 100)
    ax.plot(
        one_to_one_x,
        one_to_one_x,
        color=ONE_TO_ONE_COLOR,
        lw=1.45,
        linestyle=(0, (4, 3)),
        zorder=2,
    )

    cm_x = country_means["road_deg_mean"].to_numpy()
    cm_y = country_means["mean_increase_pct"].to_numpy()
    weights = np.sqrt(country_means["n_pairs"].to_numpy())
    slope, intercept = np.polyfit(cm_x, cm_y, 1, w=weights)
    fit_x = np.linspace(0, float(np.nanmax(cm_x)) * 1.05, 100)
    ax.plot(fit_x, slope * fit_x + intercept, color=FIT_COLOR, lw=1.95, zorder=3)

    ax.scatter(
        country_means["road_deg_mean"],
        country_means["mean_increase_pct"],
        s=size_scale(country_means["n_pairs"]) * 0.29,
        color=MEAN_COLOR,
        edgecolor="white",
        linewidth=0.75,
        alpha=0.95,
        zorder=4,
    )

    ax.set_xlim(0, max(20, float(np.nanmax(x)) * 1.05))
    ax.set_ylim(0, max(135, float(np.nanmax(y)) * 1.03))
    ax.set_xlabel("Mean road loss (%)", labelpad=2.0)
    ax.set_ylabel("Travel-time increase (%)", labelpad=2.0)
    ax.xaxis.set_major_locator(MultipleLocator(10))
    ax.yaxis.set_major_locator(MultipleLocator(50))

    x_max = float(ax.get_xlim()[1])
    fit_sample_x0 = x_max * 0.78
    fit_sample_x1 = x_max * 0.88
    fit_label_x = x_max * 0.96
    fit_label_y = slope * fit_sample_x1 + intercept + 2.0
    ax.plot(
        [fit_sample_x0, fit_sample_x1],
        [fit_label_y, fit_label_y],
        color=FIT_COLOR,
        lw=1.95,
        zorder=5,
    )
    ax.text(
        fit_label_x,
        fit_label_y,
        "Fit",
        color=FIT_COLOR,
        fontsize=FONT_SIZE - 0.4,
        ha="right",
        va="center",
        bbox={"facecolor": (1, 1, 1, 0.72), "edgecolor": "none", "pad": 0.15},
        zorder=6,
    )

    one_label_y = x_max * 0.88 + 1.0
    one_sample_x0 = x_max * 0.78
    one_sample_x1 = x_max * 0.88
    ax.plot(
        [one_sample_x0, one_sample_x1],
        [one_label_y, one_label_y],
        color=ONE_TO_ONE_COLOR,
        lw=1.45,
        linestyle=(0, (4, 3)),
        zorder=5,
    )
    ax.text(
        fit_label_x,
        one_label_y,
        "1:1",
        color="#6f6f6f",
        fontsize=FONT_SIZE - 0.4,
        ha="right",
        va="center",
        bbox={"facecolor": (1, 1, 1, 0.72), "edgecolor": "none", "pad": 0.15},
        zorder=6,
    )

    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=PAIR_COLOR,
            alpha=0.35,
            markersize=4.8,
            label="Pairs",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=MEAN_COLOR,
            markeredgecolor="white",
            markersize=5.8,
            label="Means",
        ),
    ]
    fig.legend(
        handles=legend_handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.03),
        ncol=2,
        frameon=False,
        handlelength=1.0,
        borderpad=0.2,
    )

    save_figure(fig, SCATTER_PNG, SCATTER_PDF)
    logger.log("\n[Scatter output]")
    logger.log(f"Saved PNG: {SCATTER_PNG}")
    logger.log(f"Saved PDF: {SCATTER_PDF}")
    logger.log(
        f"Scatter figure size: {SCATTER_WIDTH_CM:.1f} cm x {SCATTER_HEIGHT_CM:.1f} cm"
    )


def plot_ecdf(joined: pd.DataFrame, logger: Logger) -> None:
    fig, ax = plt.subplots(
        figsize=(cm_to_inch(ECDF_WIDTH_CM), cm_to_inch(ECDF_HEIGHT_CM))
    )
    fig.patch.set_alpha(0.0)
    fig.subplots_adjust(left=0.33, right=0.985, bottom=0.24, top=0.98)
    style_axes(ax)

    y = joined["increase_pct"].to_numpy()
    sorted_y = np.sort(y)
    ecdf = np.arange(1, len(sorted_y) + 1) / len(sorted_y) * 100.0
    severe_share = float((y > THRESHOLD).mean() * 100.0)
    cdf_at_threshold = float((y <= THRESHOLD).mean() * 100.0)

    ax.plot(sorted_y, ecdf, color=ECDF_COLOR, lw=2.0, zorder=2)
    ax.axvline(THRESHOLD, color=MEAN_COLOR, lw=1.4, linestyle=(0, (4, 3)), zorder=1)
    ax.scatter([THRESHOLD], [cdf_at_threshold], s=16, color=MEAN_COLOR, zorder=3)

    ax.text(
        0.53,
        0.16,
        f"{severe_share:.1f}% > 50%",
        transform=ax.transAxes,
        fontsize=FONT_SIZE - 0.3,
        ha="left",
        va="center",
        color=TEXT_COLOR,
    )
    ax.text(
        0.37,
        0.80,
        "50%",
        transform=ax.transAxes,
        fontsize=FONT_SIZE - 1.0,
        ha="center",
        va="bottom",
        color=MEAN_COLOR,
    )

    ax.set_xlim(0, max(120, float(np.nanmax(sorted_y)) * 1.02))
    ax.set_ylim(0, 100)
    ax.set_xlabel("Travel-time increase (%)", labelpad=2.0)
    ax.set_ylabel("Cumulative share (%)", labelpad=2.0)
    ax.xaxis.set_major_locator(MultipleLocator(50))
    ax.yaxis.set_major_locator(MultipleLocator(25))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))

    save_figure(fig, ECDF_PNG, ECDF_PDF)
    logger.log("\n[ECDF output]")
    logger.log(f"Saved PNG: {ECDF_PNG}")
    logger.log(f"Saved PDF: {ECDF_PDF}")
    logger.log(f"ECDF figure size: {ECDF_WIDTH_CM:.1f} cm x {ECDF_HEIGHT_CM:.1f} cm")


def main() -> int:
    logger = Logger(CHECKS_PATH)
    try:
        logger.log("Result 1.2 split figures: pair-level scatter + ECDF")
        set_style()
        pairs, stats = load_data(logger)
        joined, country_means = prepare_data(logger, pairs, stats)
        plot_scatter(joined, country_means, logger)
        plot_ecdf(joined, logger)
        logger.log("\nCompleted successfully.")
        return 0
    except Exception as exc:
        logger.log("\nERROR")
        logger.log(str(exc))
        return 1
    finally:
        logger.close()


if __name__ == "__main__":
    sys.exit(main())
