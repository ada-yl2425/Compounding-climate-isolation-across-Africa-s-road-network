#!/usr/bin/env python3
"""Generate the Result 2.2 isochrone contraction curve figure."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

OUTPUT_DIR = Path(
    "/Users/suhang/Downloads/同步空间/工作文件/0-1博后论文/4.非洲路网可达性/插图绘制/result 2.2"
)
INPUT_CSV = Path(
    "/Users/suhang/Downloads/同步空间/工作文件/0-1博后论文/4.非洲路网可达性/过程文件/result/result2/"
    "finding3_isochrone_coverage_drop_by_threshold/"
    "country_isochrone_coverage_normal_vs_extreme_all_thresholds.csv"
)
PNG_PATH = OUTPUT_DIR / "result2_2_isochrone_contraction_curve.png"
PDF_PATH = OUTPUT_DIR / "result2_2_isochrone_contraction_curve.pdf"
CHECK_CSV_PATH = OUTPUT_DIR / "result2_2_isochrone_contraction_curve_checks.csv"
LOG_PATH = OUTPUT_DIR / "result2_2_isochrone_contraction_curve_log.txt"

AGGREGATION_MODE = "country_mean"
POPULATION_WEIGHT_COL = "total_population"
KEY_THRESHOLDS_MIN = [30.0, 60.0, 120.0, 240.0]
EXPECTED_1H = {"normal_pct": 88.0, "extreme_pct": 81.7, "loss_pp": 6.3}
MATCH_TOLERANCE_MIN = 0.51
USE_SMOOTH_CURVE = True

FIG_SIZE = (6.0 / 2.54, 6.0 / 2.54)
PNG_DPI = 500
FONT_SIZE = 9.5
TITLE_SIZE = 9.5
LINE_WIDTH = 1.7
COUNTRY_TRACE_WIDTH = 0.42
COUNTRY_TRACE_ALPHA = 0.13
MARKER_SIZE = 18
POINT_SIZE = 6
POINT_ALPHA = 0.28
POINT_JITTER_HALF_WIDTH = 1.05
SCENARIO_OFFSET = 2.2
JITTER_SEED = 20260429
NORMAL_COLOR = "#4C78A8"
EXTREME_COLOR = "#D97A3A"
LOSS_FILL_COLOR = "#E6D4CC"
SHORT_WINDOW_FILL = "#F1F3F5"
TEXT_COLOR = "#222222"
MUTED_TEXT_COLOR = "#5B6169"
GRID_COLOR = "#D7DBE0"
CM_TO_POINTS = 72.0 / 2.54

ANNOTATION_POSITIONS = {
    30.0: (42.0, 74.0),
    60.0: (68.0, 84.8),
    120.0: (156.0, 90.2),
    240.0: (208.0, 99.2),
}
ANNOTATION_OFFSETS_POINTS = {
    30.0: (0.0, -CM_TO_POINTS),
    60.0: (0.0, -CM_TO_POINTS),
    120.0: (0.0, 0.0),
    240.0: (0.0, -CM_TO_POINTS),
}

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(OUTPUT_DIR / ".mplconfig"))
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator

try:
    from scipy.interpolate import PchipInterpolator
except Exception:  # pragma: no cover - fallback only if scipy is unavailable
    PchipInterpolator = None

LOG_LINES: List[str] = []


def log(message: str = "") -> None:
    print(message)
    LOG_LINES.append(message)


def normalise_unit_to_minutes(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit.startswith("h"):
        return value * 60.0
    return value


def infer_coverage_scale(values: Iterable[float]) -> Tuple[str, float]:
    finite_values = np.asarray([v for v in values if pd.notna(v)], dtype=float)
    if finite_values.size == 0:
        raise ValueError("No finite coverage values were found.")
    min_value = float(np.nanmin(finite_values))
    max_value = float(np.nanmax(finite_values))
    if min_value >= -1e-6 and max_value <= 1.000001:
        return "proportion_0_to_1", 100.0
    if min_value >= -1e-6 and max_value <= 100.000001:
        return "percent_0_to_100", 1.0
    raise ValueError(
        f"Coverage values appear out of range: min={min_value:.4f}, max={max_value:.4f}"
    )


def detect_threshold_columns(
    df: pd.DataFrame,
) -> Tuple[Dict[float, str], Dict[float, str], str]:
    normal_cols: Dict[float, str] = {}
    extreme_cols: Dict[float, str] = {}
    seen_units = set()
    duplicates = []

    unit_pattern = re.compile(
        r"t(?P<value>\d+(?:\.\d+)?)(?P<unit>min|mins|minute|minutes|h|hr|hrs|hour|hours)\b",
        re.IGNORECASE,
    )

    for column in df.columns:
        column_lower = column.lower()
        if "isochrone" not in column_lower:
            continue
        if not any(token in column_lower for token in ("pct", "coverage")):
            continue
        scenario = None
        if "normal" in column_lower:
            scenario = "normal"
        elif "extreme" in column_lower:
            scenario = "extreme"
        if scenario is None:
            continue

        match = unit_pattern.search(column_lower)
        if match is None:
            continue

        raw_value = float(match.group("value"))
        unit = match.group("unit")
        threshold_min = normalise_unit_to_minutes(raw_value, unit)
        seen_units.add(unit)

        target = normal_cols if scenario == "normal" else extreme_cols
        if threshold_min in target:
            duplicates.append((scenario, threshold_min, target[threshold_min], column))
            continue
        target[threshold_min] = column

    if duplicates:
        duplicate_text = "; ".join(
            f"{scenario} {threshold_min:g} min -> {first} / {second}"
            for scenario, threshold_min, first, second in duplicates
        )
        raise ValueError(f"Duplicate threshold columns detected: {duplicate_text}")

    if not normal_cols or not extreme_cols:
        raise ValueError(
            "Failed to detect wide-format threshold-specific coverage columns for both scenarios."
        )

    if set(normal_cols) != set(extreme_cols):
        raise ValueError(
            "Normal and extreme threshold sets do not match: "
            f"normal={sorted(normal_cols)}, extreme={sorted(extreme_cols)}"
        )

    if all(unit.startswith("h") for unit in seen_units):
        unit_summary = "hours encoded in column names"
    elif all(unit.startswith("min") for unit in seen_units):
        unit_summary = "minutes encoded in column names"
    else:
        unit_summary = "mixed units encoded in column names; converted to minutes"

    return dict(sorted(normal_cols.items())), dict(sorted(extreme_cols.items())), unit_summary


def candidate_long_format_fields(df: pd.DataFrame) -> Tuple[List[str], List[str], List[str]]:
    threshold_fields = [
        column
        for column in df.columns
        if re.search(r"(threshold|travel.*time|time.*threshold)", column, flags=re.IGNORECASE)
    ]
    normal_fields = [
        column
        for column in df.columns
        if "normal" in column.lower()
        and any(token in column.lower() for token in ("coverage", "pct"))
        and "isochrone" not in column.lower()
    ]
    extreme_fields = [
        column
        for column in df.columns
        if "extreme" in column.lower()
        and any(token in column.lower() for token in ("coverage", "pct"))
        and "isochrone" not in column.lower()
    ]
    return threshold_fields, normal_fields, extreme_fields


def aggregate_series(
    df: pd.DataFrame,
    columns: Dict[float, str],
    scale_factor: float,
    mode: str,
) -> pd.Series:
    values = {}
    if mode == "country_mean":
        for threshold_min, column in columns.items():
            values[threshold_min] = float(df[column].mean() * scale_factor)
        return pd.Series(values)

    if mode == "population_weighted":
        if POPULATION_WEIGHT_COL not in df.columns:
            raise ValueError(
                f"Population weight column '{POPULATION_WEIGHT_COL}' is missing from the CSV."
            )
        weights = df[POPULATION_WEIGHT_COL].astype(float)
        if (weights <= 0).any():
            raise ValueError("Population weights contain non-positive values.")
        for threshold_min, column in columns.items():
            values[threshold_min] = float(np.average(df[column].astype(float), weights=weights) * scale_factor)
        return pd.Series(values)

    raise ValueError(f"Unsupported aggregation mode: {mode}")


def build_summary_table(
    df: pd.DataFrame,
    normal_cols: Dict[float, str],
    extreme_cols: Dict[float, str],
    scale_factor: float,
    mode: str,
) -> pd.DataFrame:
    normal_pct = aggregate_series(df, normal_cols, scale_factor, mode)
    extreme_pct = aggregate_series(df, extreme_cols, scale_factor, mode)
    thresholds = sorted(normal_pct.index.tolist())

    summary = pd.DataFrame(
        {
            "threshold_min": thresholds,
            "normal_coverage_pct": [normal_pct[t] for t in thresholds],
            "extreme_coverage_pct": [extreme_pct[t] for t in thresholds],
        }
    )
    summary["change_extreme_minus_normal_pp"] = (
        summary["extreme_coverage_pct"] - summary["normal_coverage_pct"]
    )
    summary["loss_normal_minus_extreme_pp"] = (
        summary["normal_coverage_pct"] - summary["extreme_coverage_pct"]
    )
    summary["threshold_label"] = summary["threshold_min"].map(format_threshold_label)
    return summary


def build_point_cloud_table(
    df: pd.DataFrame,
    normal_cols: Dict[float, str],
    extreme_cols: Dict[float, str],
    scale_factor: float,
) -> pd.DataFrame:
    rng = np.random.default_rng(JITTER_SEED)
    country_offsets = {
        country: float(offset)
        for country, offset in zip(
            sorted(df["country"].tolist()),
            rng.uniform(-POINT_JITTER_HALF_WIDTH, POINT_JITTER_HALF_WIDTH, size=len(df)),
        )
    }
    rows = []
    for threshold_min in sorted(normal_cols):
        for scenario, columns, offset in (
            ("normal", normal_cols, -SCENARIO_OFFSET),
            ("extreme", extreme_cols, SCENARIO_OFFSET),
        ):
            values = df[columns[threshold_min]].astype(float) * scale_factor
            for country, coverage_pct in zip(df["country"], values):
                rows.append(
                    {
                        "country": country,
                        "threshold_min": threshold_min,
                        "scenario": scenario,
                        "coverage_pct": float(coverage_pct),
                        "x_plot": float(threshold_min + offset + country_offsets[country]),
                    }
                )
    return pd.DataFrame(rows)


def format_threshold_label(minutes: float) -> str:
    if abs(minutes - 30.0) < 1e-9:
        return "30 min"
    if abs(minutes - 60.0) < 1e-9:
        return "1 h"
    if minutes % 60 == 0 and minutes >= 60:
        return f"{int(minutes / 60)} h"
    return f"{int(minutes)} min"


def format_axis_tick_label(minutes: float) -> str:
    if abs(minutes - 30.0) < 1e-9:
        return "30m"
    if minutes % 60 == 0 and minutes >= 60:
        return f"{int(minutes / 60)}h"
    return f"{int(minutes)}m"


def match_threshold(available_minutes: Iterable[float], requested_min: float) -> float | None:
    available = np.asarray(list(available_minutes), dtype=float)
    if available.size == 0:
        return None
    idx = int(np.argmin(np.abs(available - requested_min)))
    matched = float(available[idx])
    if abs(matched - requested_min) <= MATCH_TOLERANCE_MIN:
        return matched
    return None


def smooth_curve(x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    if (
        USE_SMOOTH_CURVE
        and PchipInterpolator is not None
        and len(x) >= 3
        and np.all(np.diff(x) > 0)
    ):
        x_dense = np.linspace(x.min(), x.max(), 400)
        interpolator = PchipInterpolator(x, y)
        y_dense = interpolator(x_dense)
        return x_dense, y_dense
    return x, y


def write_outputs(summary_df: pd.DataFrame) -> None:
    log(f"Saved check table: {CHECK_CSV_PATH}")
    log(f"Saved log file: {LOG_PATH}")
    summary_df.to_csv(CHECK_CSV_PATH, index=False)
    LOG_PATH.write_text("\n".join(LOG_LINES) + "\n", encoding="utf-8")


def plot_figure(
    summary_df: pd.DataFrame,
    one_hour_row: pd.Series,
    point_cloud_df: pd.DataFrame,
) -> None:
    plt.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.size": FONT_SIZE,
            "axes.titlesize": TITLE_SIZE,
            "axes.labelsize": FONT_SIZE,
            "xtick.labelsize": FONT_SIZE,
            "ytick.labelsize": FONT_SIZE,
            "legend.fontsize": FONT_SIZE,
            "axes.edgecolor": "#5F6770",
            "axes.linewidth": 0.8,
            "xtick.color": TEXT_COLOR,
            "ytick.color": TEXT_COLOR,
            "text.color": TEXT_COLOR,
            "axes.labelcolor": TEXT_COLOR,
            "legend.frameon": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    x = summary_df["threshold_min"].to_numpy(dtype=float)
    y_normal = summary_df["normal_coverage_pct"].to_numpy(dtype=float)
    y_extreme = summary_df["extreme_coverage_pct"].to_numpy(dtype=float)
    x_smooth, y_normal_smooth = smooth_curve(x, y_normal)
    _, y_extreme_smooth = smooth_curve(x, y_extreme)

    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    ax.axvspan(max(x.min() - 6, 0), 60, color=SHORT_WINDOW_FILL, alpha=0.65, zorder=0)
    ax.fill_between(
        x_smooth,
        y_extreme_smooth,
        y_normal_smooth,
        color=LOSS_FILL_COLOR,
        alpha=0.13,
        zorder=1,
    )
    for scenario, color in (("normal", NORMAL_COLOR), ("extreme", EXTREME_COLOR)):
        scenario_points = point_cloud_df.loc[point_cloud_df["scenario"] == scenario]
        for _, country_df in scenario_points.groupby("country", sort=False):
            country_df = country_df.sort_values("threshold_min")
            ax.plot(
                country_df["x_plot"],
                country_df["coverage_pct"],
                color=color,
                alpha=COUNTRY_TRACE_ALPHA,
                linewidth=COUNTRY_TRACE_WIDTH,
                zorder=2,
            )
        ax.scatter(
            scenario_points["x_plot"],
            scenario_points["coverage_pct"],
            s=POINT_SIZE,
            color=color,
            alpha=POINT_ALPHA,
            linewidths=0,
            zorder=2.2,
        )
    ax.plot(
        x_smooth,
        y_normal_smooth,
        color=NORMAL_COLOR,
        linewidth=LINE_WIDTH,
        label="Normal weather",
        zorder=3,
    )
    ax.plot(
        x_smooth,
        y_extreme_smooth,
        color=EXTREME_COLOR,
        linewidth=LINE_WIDTH,
        label="Extreme weather",
        zorder=4,
    )
    ax.scatter(x, y_normal, s=MARKER_SIZE, color=NORMAL_COLOR, zorder=5)
    ax.scatter(x, y_extreme, s=MARKER_SIZE, color=EXTREME_COLOR, zorder=6)

    for _, row in summary_df.iterrows():
        threshold = float(row["threshold_min"])
        if threshold not in KEY_THRESHOLDS_MIN:
            continue
        label_x, label_y = ANNOTATION_POSITIONS[threshold]
        offset_x, offset_y = ANNOTATION_OFFSETS_POINTS.get(threshold, (0.0, 0.0))
        ax.annotate(
            f"{row['change_extreme_minus_normal_pp']:+.1f}",
            xy=(label_x, label_y),
            xytext=(offset_x, offset_y),
            textcoords="offset points",
            ha="center",
            va="center",
            fontsize=FONT_SIZE,
            bbox={"boxstyle": "round,pad=0.18", "fc": "white", "ec": "none", "alpha": 0.93},
            color=TEXT_COLOR,
            zorder=7,
        )

    headline_text = (
        f"1h: {one_hour_row['normal_coverage_pct']:.1f}% vs {one_hour_row['extreme_coverage_pct']:.1f}%\n"
        f"{one_hour_row['loss_normal_minus_extreme_pp']:.1f}%"
    )
    ax.text(
        240.0,
        73.7,
        headline_text,
        ha="right",
        va="bottom",
        fontsize=FONT_SIZE,
        linespacing=1.05,
        bbox={"boxstyle": "round,pad=0.22", "fc": "white", "ec": "#D6DADF", "lw": 0.8},
        zorder=8,
    )

    y_min = 65.0
    y_max = 100.5

    ax.set_xlim(max(x.min() - 6, 0), x.max() + 12)
    ax.set_ylim(y_min, y_max)
    ax.set_xticks(x)
    ax.set_xticklabels([format_axis_tick_label(value) for value in x])
    ax.set_yticks([70, 80, 90, 100])

    ax.set_xlabel("Travel-time threshold")
    ax.set_ylabel("Population covered (%)")
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7, alpha=0.8)
    ax.grid(axis="x", visible=False)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.subplots_adjust(left=0.22, right=0.985, bottom=0.20, top=0.985)
    fig.savefig(PNG_PATH, dpi=PNG_DPI, facecolor="white")
    fig.savefig(PDF_PATH, facecolor="white")
    plt.close(fig)

    log(f"Saved figure: {PNG_PATH}")
    log(f"Saved figure: {PDF_PATH}")


def main() -> None:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Input CSV not found: {INPUT_CSV}")

    df = pd.read_csv(INPUT_CSV)

    threshold_field_candidates, normal_field_candidates, extreme_field_candidates = (
        candidate_long_format_fields(df)
    )
    normal_cols, extreme_cols, threshold_unit_summary = detect_threshold_columns(df)

    relevant_columns = list(normal_cols.values()) + list(extreme_cols.values())
    coverage_scale_name, scale_factor = infer_coverage_scale(
        df[relevant_columns].to_numpy().ravel()
    )

    missing_values = int(df[relevant_columns].isna().sum().sum())
    duplicate_thresholds = False

    raw_min = float(np.nanmin(df[relevant_columns].to_numpy()))
    raw_max = float(np.nanmax(df[relevant_columns].to_numpy()))
    scaled_min = raw_min * scale_factor
    scaled_max = raw_max * scale_factor
    abnormal_mask = (df[relevant_columns] < 0) | (df[relevant_columns] > (1.0 if scale_factor == 100.0 else 100.0))
    abnormal_count = int(abnormal_mask.sum().sum())

    summary_df = build_summary_table(
        df, normal_cols, extreme_cols, scale_factor, mode=AGGREGATION_MODE
    )
    point_cloud_df = build_point_cloud_table(df, normal_cols, extreme_cols, scale_factor)
    if summary_df.empty:
        raise ValueError("Summary table is empty after aggregation.")

    alt_mode = "population_weighted" if AGGREGATION_MODE == "country_mean" else "country_mean"
    alt_summary_df = build_summary_table(
        df, normal_cols, extreme_cols, scale_factor, mode=alt_mode
    )

    available_thresholds = summary_df["threshold_min"].tolist()
    key_matches = {
        requested: match_threshold(available_thresholds, requested)
        for requested in KEY_THRESHOLDS_MIN
    }
    if any(match is None for match in key_matches.values()):
        raise ValueError(f"Failed to match one or more key thresholds: {key_matches}")

    one_hour_row = summary_df.loc[
        summary_df["threshold_min"] == key_matches[60.0]
    ].iloc[0]

    log("=== Result 2.2 Isochrone Contraction Curve Check ===")
    log(f"Input CSV: {INPUT_CSV}")
    log("")
    log("1) CSV fields")
    for column in df.columns:
        log(f"   - {column}")
    log("")
    log("2) Structure and field detection")
    log(f"   - Detected table layout: wide format (thresholds encoded in coverage column names)")
    log(
        "   - Candidate long-format threshold fields: "
        + (", ".join(threshold_field_candidates) if threshold_field_candidates else "none")
    )
    log(
        "   - Candidate long-format normal coverage fields: "
        + (", ".join(normal_field_candidates) if normal_field_candidates else "none")
    )
    log(
        "   - Candidate long-format extreme coverage fields: "
        + (", ".join(extreme_field_candidates) if extreme_field_candidates else "none")
    )
    log(f"   - Threshold interpretation: {threshold_unit_summary}")
    log(f"   - Detected normal coverage columns: {list(normal_cols.values())}")
    log(f"   - Detected extreme coverage columns: {list(extreme_cols.values())}")
    log(f"   - Coverage scale interpretation: {coverage_scale_name} -> plotted as percentages")
    log(f"   - Aggregation mode used for the figure: {AGGREGATION_MODE}")
    if POPULATION_WEIGHT_COL in df.columns:
        log(f"   - Population weight field available: {POPULATION_WEIGHT_COL}")
    log("")
    log("3) Threshold coverage overview")
    log(f"   - Number of countries (rows): {len(df)}")
    log(f"   - Total threshold count: {len(summary_df)}")
    log(f"   - Country-level background points plotted: {len(point_cloud_df)}")
    log(
        "   - Threshold range after unit normalization: "
        f"{summary_df['threshold_min'].min():.0f} to {summary_df['threshold_min'].max():.0f} minutes"
    )
    log(
        "   - Normal coverage range: "
        f"{summary_df['normal_coverage_pct'].min():.1f}% to {summary_df['normal_coverage_pct'].max():.1f}%"
    )
    log(
        "   - Extreme coverage range: "
        f"{summary_df['extreme_coverage_pct'].min():.1f}% to {summary_df['extreme_coverage_pct'].max():.1f}%"
    )
    log(
        "   - Raw relevant coverage value range in CSV: "
        f"{raw_min:.4f} to {raw_max:.4f}"
    )
    log(
        "   - Raw range expressed in plotted percent units: "
        f"{scaled_min:.1f}% to {scaled_max:.1f}%"
    )
    log("")
    log("4) Data quality checks")
    log(f"   - Missing values in relevant coverage fields: {missing_values}")
    log(f"   - Duplicate thresholds detected: {duplicate_thresholds}")
    log(f"   - Abnormal coverage values (<0 or >100% after scaling): {abnormal_count}")
    log("")
    log("5) Key threshold matching")
    for requested, matched in key_matches.items():
        log(
            f"   - Requested {format_threshold_label(requested)} -> "
            f"{format_threshold_label(matched) if matched is not None else 'NOT FOUND'}"
        )
    log("")
    log("6) Key threshold values (country mean across countries)")
    for requested in KEY_THRESHOLDS_MIN:
        matched = key_matches[requested]
        row = summary_df.loc[summary_df["threshold_min"] == matched].iloc[0]
        log(
            "   - "
            f"{row['threshold_label']}: "
            f"normal={row['normal_coverage_pct']:.1f}%, "
            f"extreme={row['extreme_coverage_pct']:.1f}%, "
            f"change(extreme-normal)={row['change_extreme_minus_normal_pp']:+.1f} pp, "
            f"loss={row['loss_normal_minus_extreme_pp']:.1f} pp"
        )
    log("")
    log("7) One-hour headline check")
    log(
        "   - Observed 1 h values: "
        f"{one_hour_row['normal_coverage_pct']:.1f}% -> "
        f"{one_hour_row['extreme_coverage_pct']:.1f}%, "
        f"loss={one_hour_row['loss_normal_minus_extreme_pp']:.1f} pp"
    )
    log(
        "   - Expected reference: "
        f"{EXPECTED_1H['normal_pct']:.1f}% -> "
        f"{EXPECTED_1H['extreme_pct']:.1f}%, "
        f"loss={EXPECTED_1H['loss_pp']:.1f} pp"
    )
    log(
        "   - Difference from expected: "
        f"normal={one_hour_row['normal_coverage_pct'] - EXPECTED_1H['normal_pct']:+.2f} pp, "
        f"extreme={one_hour_row['extreme_coverage_pct'] - EXPECTED_1H['extreme_pct']:+.2f} pp, "
        f"loss={one_hour_row['loss_normal_minus_extreme_pp'] - EXPECTED_1H['loss_pp']:+.2f} pp"
    )
    log("")
    log("8) Aggregation cross-check")
    merged = summary_df.merge(
        alt_summary_df,
        on="threshold_min",
        suffixes=(f"_{AGGREGATION_MODE}", f"_{alt_mode}"),
    )
    for _, row in merged.iterrows():
        log(
            f"   - {format_threshold_label(row['threshold_min'])}: "
            f"{AGGREGATION_MODE} normal/extreme="
            f"{row[f'normal_coverage_pct_{AGGREGATION_MODE}']:.1f}%/"
            f"{row[f'extreme_coverage_pct_{AGGREGATION_MODE}']:.1f}%; "
            f"{alt_mode} normal/extreme="
            f"{row[f'normal_coverage_pct_{alt_mode}']:.1f}%/"
            f"{row[f'extreme_coverage_pct_{alt_mode}']:.1f}%"
        )

    plot_figure(summary_df, one_hour_row, point_cloud_df)
    write_outputs(summary_df)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"ERROR: {exc}")
        LOG_PATH.write_text("\n".join(LOG_LINES) + "\n", encoding="utf-8")
        raise
