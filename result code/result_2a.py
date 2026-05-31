#!/usr/bin/env python3
"""Result 2.1 mirror dumbbell plot: buffering mechanism plus realized loss."""

from __future__ import annotations

import os
import re
from pathlib import Path

OUTPUT_DIR = Path(
    "/Users/suhang/Downloads/同步空间/工作文件/0-1博后论文/4.非洲路网可达性/插图绘制/result 2.1"
)
MPLCONFIG_DIR = OUTPUT_DIR / ".mplconfig"
MPLCONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D


TAIL_GAP_CSV = Path(
    "/Users/suhang/Downloads/同步空间/工作文件/0-1博后论文/4.非洲路网可达性/过程文件/result/result2/finding1_2_country_tail_gap_p50_p90_ranking/country_p50_p90_delta_travel_time_and_tail_gap.csv"
)
BUFFERING_CSV = Path(
    "/Users/suhang/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/Suhang1995522_c823/temp/drag/country_buffering_stats.csv"
)

OUTPUT_PNG = OUTPUT_DIR / "result2_1_tailgap_buffering_mirror_dumbbell.png"
OUTPUT_PDF = OUTPUT_DIR / "result2_1_tailgap_buffering_mirror_dumbbell.pdf"
OUTPUT_LOG = OUTPUT_DIR / "result2_1_tailgap_buffering_mirror_dumbbell_checks.txt"
OUTPUT_SORTED_CSV = OUTPUT_DIR / "result2_1_tailgap_buffering_mirror_dumbbell_plot_data.csv"

FIG_WIDTH_CM = 12.5
FIG_HEIGHT_CM = 20.0
DPI = 450
FONT_SIZE = 9.5
LEFT_PANEL_DISPLAY_MAX_PCT = 60.0
LEFT_ZERO_PAD_PCT = 2.0
RIGHT_ZERO_PAD_MIN = 3.0
GRID_WIDTH_RATIOS = [2.0 / 3.0, 1.22, 1.35 * 2.0 / 3.0]

P50_COLOR = "#C9D6E3"
P50_EDGE = "#7F97B3"
P90_COLOR = "#234D76"
P90_EDGE = "#173551"
LINE_COLOR = "#A3ACB6"
GRID_COLOR = "#E5EAF0"
TEXT_COLOR = "#243241"
ANNOTATION_FACE = "#FFFFFF"
ANNOTATION_EDGE = "#C9D3DE"

EXCLUDED_COUNTRIES = {"Angola", "Algeria", "WestSahara"}
SORT_PRIMARY = "tail_gap_ratio_plot"


COUNTRY_LABEL_MAP = {
    "IvoryCoast": "Ivory Coast",
    "SouthAfrica": "South Africa",
    "BurkinaFaso": "Burkina Faso",
    "SouthSudan": "South Sudan",
    "CentralAfrican": "Central African Rep.",
    "SierraLeone": "Sierra Leone",
    "GuineaBissau": "Guinea-Bissau",
    "CongoDR": "DR Congo",
    "Equatorial": "Equatorial Guinea",
}


class Logger:
    """Simple stdout/file logger."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines: list[str] = []

    def log(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def block(self, text: str) -> None:
        for line in text.splitlines():
            self.log(line)

    def save(self) -> None:
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def format_country_label(country: str) -> str:
    if country in COUNTRY_LABEL_MAP:
        return COUNTRY_LABEL_MAP[country]
    return re.sub(r"(?<!^)(?=[A-Z])", " ", str(country)).strip()


def require_columns(df: pd.DataFrame, required: list[str], table_name: str) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"{table_name} is missing required columns: {missing}")


def load_data(logger: Logger) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load, join, validate, and prepare the 47-country plotting sample."""
    tail_df = pd.read_csv(TAIL_GAP_CSV)
    buffering_df = pd.read_csv(BUFFERING_CSV)

    require_columns(
        tail_df,
        ["country", "tail_gap_ratio_plot", "p50_delta_h", "p90_delta_h"],
        "tail-gap CSV",
    )
    require_columns(
        buffering_df,
        [
            "country",
            "pwmean_buffering_p50",
            "pwmean_buffering_p90",
            "buffering_ratio_p50_over_p90",
            "mean_degree_p50",
            "mean_degree_p90",
            "mean_direct_degradation_h_p50",
            "mean_direct_degradation_h_p90",
            "mean_actual_delta_h_p50",
            "mean_actual_delta_h_p90",
        ],
        "buffering CSV",
    )

    logger.log("Input tables")
    logger.log(f"  - Tail-gap CSV: {TAIL_GAP_CSV}")
    logger.log(f"  - Buffering CSV: {BUFFERING_CSV}")
    logger.log("")
    logger.log("1) Field names: tail-gap CSV")
    for col in tail_df.columns:
        logger.log(f"  - {col}")
    logger.log("")
    logger.log("2) Field names: buffering CSV")
    for col in buffering_df.columns:
        logger.log(f"  - {col}")
    logger.log("")
    logger.log("3) Buffering CSV preview")
    logger.block(buffering_df.head(8).to_string(index=False))
    logger.log("")

    numeric_tail_cols = ["tail_gap_ratio_plot", "p50_delta_h", "p90_delta_h"]
    numeric_buffer_cols = [
        "pwmean_buffering_p50",
        "pwmean_buffering_p90",
        "buffering_ratio_p50_over_p90",
        "mean_degree_p50",
        "mean_degree_p90",
        "mean_direct_degradation_h_p50",
        "mean_direct_degradation_h_p90",
        "mean_actual_delta_h_p50",
        "mean_actual_delta_h_p90",
    ]
    for col in numeric_tail_cols:
        tail_df[col] = pd.to_numeric(tail_df[col], errors="coerce")
    for col in numeric_buffer_cols:
        buffering_df[col] = pd.to_numeric(buffering_df[col], errors="coerce")

    tail_df = tail_df.loc[~tail_df["country"].isin(EXCLUDED_COUNTRIES)].copy()
    buffering_df = buffering_df.loc[~buffering_df["country"].isin(EXCLUDED_COUNTRIES)].copy()

    merged = tail_df.merge(buffering_df, on="country", how="inner", validate="one_to_one")
    merged["plot_country"] = merged["country"].map(format_country_label)
    merged["p50_delta_min"] = merged["p50_delta_h"] * 60.0
    merged["p90_delta_min"] = merged["p90_delta_h"] * 60.0
    merged["buffering_p50_pct"] = merged["pwmean_buffering_p50"] * 100.0
    merged["buffering_p90_pct"] = merged["pwmean_buffering_p90"] * 100.0
    merged["buffering_p50_clipped"] = merged["buffering_p50_pct"] > LEFT_PANEL_DISPLAY_MAX_PCT
    merged["buffering_p90_clipped"] = merged["buffering_p90_pct"] > LEFT_PANEL_DISPLAY_MAX_PCT
    merged["buffering_p50_pct_plot"] = merged["buffering_p50_pct"].clip(
        upper=LEFT_PANEL_DISPLAY_MAX_PCT
    )
    merged["buffering_p90_pct_plot"] = merged["buffering_p90_pct"].clip(
        upper=LEFT_PANEL_DISPLAY_MAX_PCT
    )
    merged["buffering_gap_pct"] = merged["buffering_p50_pct"] - merged["buffering_p90_pct"]
    merged["degree_gap"] = merged["mean_degree_p50"] - merged["mean_degree_p90"]
    merged["tail_gap_abs_h"] = merged["p90_delta_h"] - merged["p50_delta_h"]

    sort_cols = [SORT_PRIMARY, "tail_gap_abs_h", "p90_delta_h"]
    merged = merged.sort_values(sort_cols, ascending=[False, False, False], kind="mergesort")
    merged = merged.reset_index(drop=True)

    n_countries = len(merged)
    degenerate_buffer_mask = (
        merged["mean_direct_degradation_h_p50"].eq(0) | merged["mean_direct_degradation_h_p90"].eq(0)
    )
    p50_buffer_gt_mask = merged["pwmean_buffering_p50"] > merged["pwmean_buffering_p90"]
    degree_gt_mask = merged["mean_degree_p50"] > merged["mean_degree_p90"]
    tail_gt_mask = merged["p90_delta_h"] > merged["p50_delta_h"]

    logger.log(f"4) Countries retained for plotting: {n_countries}")
    logger.log(f"   Excluded countries: {', '.join(sorted(EXCLUDED_COUNTRIES))}")
    logger.log(
        "5) P90Δt > P50Δt in retained sample: "
        f"{int(tail_gt_mask.sum())} / {n_countries}"
    )
    logger.log(
        "6) P50 buffering > P90 buffering in retained sample: "
        f"{int(p50_buffer_gt_mask.sum())} / {n_countries}"
    )
    logger.log(
        "7) Mean degree at P50 > mean degree at P90: "
        f"{int(degree_gt_mask.sum())} / {n_countries}"
    )
    logger.log(
        "8) Median buffering ratio (country-level, population-weighted)"
    )
    logger.log(f"   - P50: {merged['buffering_p50_pct'].median():.2f}%")
    logger.log(f"   - P90: {merged['buffering_p90_pct'].median():.2f}%")
    logger.log(
        "9) Mean buffering ratio (country-level, population-weighted)"
    )
    logger.log(f"   - P50: {merged['buffering_p50_pct'].mean():.2f}%")
    logger.log(f"   - P90: {merged['buffering_p90_pct'].mean():.2f}%")
    logger.log(
        "10) Countries with zero direct degradation in at least one percentile group: "
        f"{int(degenerate_buffer_mask.sum())}"
    )
    if degenerate_buffer_mask.any():
        logger.block(
            merged.loc[
                degenerate_buffer_mask,
                [
                    "country",
                    "mean_direct_degradation_h_p50",
                    "mean_direct_degradation_h_p90",
                    "buffering_p50_pct",
                    "buffering_p90_pct",
                ],
            ].to_string(index=False)
        )
    logger.log("")
    logger.log("11) Ranges used in the plot")
    logger.log(
        f"   - Buffering P50 range: {merged['buffering_p50_pct'].min():.2f}% to {merged['buffering_p50_pct'].max():.2f}%"
    )
    logger.log(
        f"   - Buffering P90 range: {merged['buffering_p90_pct'].min():.2f}% to {merged['buffering_p90_pct'].max():.2f}%"
    )
    logger.log(
        f"   - Travel-time P50 range: {merged['p50_delta_min'].min():.2f} to {merged['p50_delta_min'].max():.2f} min"
    )
    logger.log(
        f"   - Travel-time P90 range: {merged['p90_delta_min'].min():.2f} to {merged['p90_delta_min'].max():.2f} min"
    )
    logger.log(
        "   - Left-panel display cap for buffering axis: "
        f"{LEFT_PANEL_DISPLAY_MAX_PCT:.0f}%"
    )
    logger.log(
        "   - Countries clipped in the buffering panel: "
        f"{int(merged['buffering_p50_clipped'].sum() + merged['buffering_p90_clipped'].sum())}"
    )
    if merged["buffering_p50_clipped"].any() or merged["buffering_p90_clipped"].any():
        logger.block(
            merged.loc[
                merged["buffering_p50_clipped"] | merged["buffering_p90_clipped"],
                [
                    "country",
                    "buffering_p50_pct",
                    "buffering_p90_pct",
                    "buffering_p50_clipped",
                    "buffering_p90_clipped",
                ],
            ].to_string(index=False)
        )
    logger.log("")
    logger.log("12) Sorting used for both halves of the mirror plot")
    logger.log(f"   - Primary sort: {SORT_PRIMARY} descending")
    logger.log("   - Tie-breakers: tail_gap_abs_h, p90_delta_h")
    logger.log("   - Top 10 countries after sorting")
    logger.block(
        merged[
            [
                "country",
                "tail_gap_ratio_plot",
                "buffering_p50_pct",
                "buffering_p90_pct",
                "p50_delta_min",
                "p90_delta_min",
            ]
        ].head(10).to_string(index=False)
    )

    stats = {
        "n_countries": n_countries,
        "tail_gt_count": int(tail_gt_mask.sum()),
        "p50_buffer_gt_count": int(p50_buffer_gt_mask.sum()),
        "degree_gt_count": int(degree_gt_mask.sum()),
        "median_buffer_p50": float(merged["buffering_p50_pct"].median()),
        "median_buffer_p90": float(merged["buffering_p90_pct"].median()),
    }
    return merged, stats


def build_annotation_text(stats: dict[str, object]) -> str:
    return (
        f"Median buffering ratio: P50 {stats['median_buffer_p50']:.1f}% vs P90 {stats['median_buffer_p90']:.1f}%\n"
        f"P50 buffering exceeds P90 in {stats['p50_buffer_gt_count']}/{stats['n_countries']} countries; "
        f"mean degree is higher at P50 in {stats['degree_gt_count']}/{stats['n_countries']}\n"
        f"P90Δt exceeds P50Δt in {stats['tail_gt_count']}/{stats['n_countries']} countries"
    )


def export_plot_data(df: pd.DataFrame) -> None:
    export_cols = [
        "country",
        "plot_country",
        "tail_gap_ratio_plot",
        "p50_delta_h",
        "p90_delta_h",
        "p50_delta_min",
        "p90_delta_min",
        "pwmean_buffering_p50",
        "pwmean_buffering_p90",
        "buffering_p50_pct",
        "buffering_p90_pct",
        "buffering_p50_pct_plot",
        "buffering_p90_pct_plot",
        "buffering_p50_clipped",
        "buffering_p90_clipped",
        "buffering_gap_pct",
        "buffering_ratio_p50_over_p90",
        "mean_direct_degradation_h_p50",
        "mean_direct_degradation_h_p90",
        "mean_actual_delta_h_p50",
        "mean_actual_delta_h_p90",
        "mean_degree_p50",
        "mean_degree_p90",
        "degree_gap",
    ]
    df.assign(rank=np.arange(1, len(df) + 1))[["rank"] + export_cols].to_csv(
        OUTPUT_SORTED_CSV, index=False
    )


def make_plot(df: pd.DataFrame, stats: dict[str, object]) -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman"],
            "font.size": FONT_SIZE,
            "axes.labelcolor": TEXT_COLOR,
            "xtick.color": TEXT_COLOR,
            "ytick.color": TEXT_COLOR,
        }
    )

    fig = plt.figure(figsize=(FIG_WIDTH_CM / 2.54, FIG_HEIGHT_CM / 2.54), facecolor="white")
    gs = fig.add_gridspec(1, 3, width_ratios=GRID_WIDTH_RATIOS, wspace=0.02)

    ax_left = fig.add_subplot(gs[0, 0])
    ax_labels = fig.add_subplot(gs[0, 1], sharey=ax_left)
    ax_right = fig.add_subplot(gs[0, 2], sharey=ax_left)

    y = np.arange(len(df))

    left_min = np.minimum(df["buffering_p50_pct_plot"], df["buffering_p90_pct_plot"])
    left_max = np.maximum(df["buffering_p50_pct_plot"], df["buffering_p90_pct_plot"])

    ax_left.hlines(
        y=y,
        xmin=left_min,
        xmax=left_max,
        color=LINE_COLOR,
        linewidth=1.1,
        alpha=0.95,
        zorder=1,
    )
    p50_unclipped = ~df["buffering_p50_clipped"]
    p90_unclipped = ~df["buffering_p90_clipped"]
    ax_left.scatter(
        df.loc[p50_unclipped, "buffering_p50_pct_plot"],
        y[p50_unclipped],
        s=28,
        color=P50_COLOR,
        edgecolor=P50_EDGE,
        linewidth=0.7,
        zorder=3,
    )
    ax_left.scatter(
        df.loc[p90_unclipped, "buffering_p90_pct_plot"],
        y[p90_unclipped],
        s=28,
        color=P90_COLOR,
        edgecolor=P90_EDGE,
        linewidth=0.7,
        zorder=4,
    )
    if df["buffering_p50_clipped"].any():
        ax_left.scatter(
            df.loc[df["buffering_p50_clipped"], "buffering_p50_pct_plot"],
            y[df["buffering_p50_clipped"]],
            s=44,
            marker="<",
            color=P50_COLOR,
            edgecolor=P50_EDGE,
            linewidth=0.8,
            zorder=5,
        )
    if df["buffering_p90_clipped"].any():
        ax_left.scatter(
            df.loc[df["buffering_p90_clipped"], "buffering_p90_pct_plot"],
            y[df["buffering_p90_clipped"]],
            s=44,
            marker="<",
            color=P90_COLOR,
            edgecolor=P90_EDGE,
            linewidth=0.8,
            zorder=6,
        )

    ax_right.hlines(
        y=y,
        xmin=df["p50_delta_min"],
        xmax=df["p90_delta_min"],
        color=LINE_COLOR,
        linewidth=1.1,
        alpha=0.95,
        zorder=1,
    )
    ax_right.scatter(
        df["p50_delta_min"],
        y,
        s=28,
        color=P50_COLOR,
        edgecolor=P50_EDGE,
        linewidth=0.7,
        zorder=3,
    )
    ax_right.scatter(
        df["p90_delta_min"],
        y,
        s=28,
        color=P90_COLOR,
        edgecolor=P90_EDGE,
        linewidth=0.7,
        zorder=4,
    )

    ax_left.set_ylim(-0.5, len(df) - 0.5)
    ax_left.invert_yaxis()
    ax_left.set_xlim(LEFT_PANEL_DISPLAY_MAX_PCT, -LEFT_ZERO_PAD_PCT)
    ax_right.set_xlim(-RIGHT_ZERO_PAD_MIN, max(150, float(df["p90_delta_min"].max()) + 5))

    ax_left.set_xticks([60, 40, 20, 0])
    ax_right.set_xticks([0, 50, 100, 150])

    for ax in [ax_left, ax_right]:
        ax.set_yticks(y)
        ax.tick_params(axis="y", left=False, labelleft=False, length=0)
        ax.tick_params(axis="x", labelsize=FONT_SIZE)
        ax.xaxis.grid(True, color=GRID_COLOR, linewidth=0.8)
        ax.yaxis.grid(False)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_color("#C8D0D8")

    ax_left.set_xlabel(
        "Network buffering ratio (%)\n(display capped at 60%)",
        fontsize=FONT_SIZE,
        labelpad=8,
    )
    ax_right.set_xlabel("Travel-time increase (min)", fontsize=FONT_SIZE, labelpad=8)

    ax_labels.set_xlim(0, 1)
    ax_labels.set_ylim(-0.5, len(df) - 0.5)
    ax_labels.invert_yaxis()
    ax_labels.axis("off")
    for yi, label in zip(y, df["plot_country"]):
        ax_labels.text(
            0.5,
            yi,
            label,
            ha="center",
            va="center",
            fontsize=FONT_SIZE,
            color=TEXT_COLOR,
        )

    ax_left.text(
        0.5,
        1.02,
        "Buffering of direct degradation",
        transform=ax_left.transAxes,
        ha="center",
        va="bottom",
        fontsize=FONT_SIZE,
        color=TEXT_COLOR,
    )
    ax_right.text(
        0.5,
        1.02,
        "Realized accessibility loss",
        transform=ax_right.transAxes,
        ha="center",
        va="bottom",
        fontsize=FONT_SIZE,
        color=TEXT_COLOR,
    )

    annotation = build_annotation_text(stats)
    fig.text(
        0.5,
        0.975,
        annotation,
        ha="center",
        va="top",
        fontsize=FONT_SIZE,
        color=TEXT_COLOR,
        linespacing=1.25,
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": ANNOTATION_FACE,
            "edgecolor": ANNOTATION_EDGE,
            "linewidth": 0.9,
        },
    )

    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=P50_COLOR,
            markeredgecolor=P50_EDGE,
            markersize=6.5,
            label="P50",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=P90_COLOR,
            markeredgecolor=P90_EDGE,
            markersize=6.5,
            label="P90",
        ),
    ]
    ax_right.legend(
        handles=legend_handles,
        loc="lower right",
        bbox_to_anchor=(0.98, 0.02),
        frameon=False,
        fontsize=FONT_SIZE,
        borderaxespad=0.0,
        handletextpad=0.5,
    )

    fig.subplots_adjust(left=0.05, right=0.985, top=0.885, bottom=0.07)
    fig.savefig(OUTPUT_PNG, dpi=DPI, facecolor=fig.get_facecolor())
    fig.savefig(OUTPUT_PDF, facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger = Logger(OUTPUT_LOG)
    try:
        df, stats = load_data(logger)
        export_plot_data(df)
        make_plot(df, stats)
        logger.log("")
        logger.log("Output files")
        logger.log(f"  - PNG: {OUTPUT_PNG}")
        logger.log(f"  - PDF: {OUTPUT_PDF}")
        logger.log(f"  - Log: {OUTPUT_LOG}")
        logger.log(f"  - Plot data CSV: {OUTPUT_SORTED_CSV}")
    finally:
        logger.save()


if __name__ == "__main__":
    main()
