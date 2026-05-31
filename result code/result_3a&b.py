#!/usr/bin/env python3
"""Generate the Result 3 two-panel figure for bottleneck stability and recovery."""

from __future__ import annotations

import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

OUTPUT_DIR = Path(
    "/Users/suhang/Downloads/同步空间/工作文件/0-1博后论文/4.非洲路网可达性/插图绘制/result 3"
)

PANEL_A_REPORT_CANDIDATES = [
    Path(
        "/Users/suhang/Library/Containers/com.tencent.xinWeChat/Data/Documents/"
        "xwechat_files/Suhang1995522_c823/temp/drag/bottleneck_stability_report.csv"
    ),
    Path(
        "/Users/suhang/Downloads/Synchronous Space/Working Documents/0-1 Post-PhD Papers/"
        "4. African Road Network Accessibility/Process Files/result/result3/"
        "finding1_future_bottleneck_stability/bottleneck_stability_report.csv"
    ),
    Path(
        "/Users/suhang/Downloads/同步空间/工作文件/0-1博后论文/4.非洲路网可达性/过程文件/result/result3/"
        "finding1_future_bottleneck_stability/bottleneck_stability_report.csv"
    ),
    Path(
        "/Users/suhang/Downloads/result/result3/finding1_future_bottleneck_stability/"
        "bottleneck_stability_report.csv"
    ),
]

PANEL_B_CSV_CANDIDATES = [
    Path(
        "/Users/suhang/Library/Containers/com.tencent.xinWeChat/Data/Documents/"
        "xwechat_files/Suhang1995522_c823/temp/drag/04_paving_experiment.csv"
    ),
    Path(
        "/Users/suhang/Downloads/同步空间/工作文件/0-1博后论文/4.非洲路网可达性/过程文件/result/result3/"
        "finding4_5_paving_strategy_recovery_curves/paving_fraction_vs_recovery_NI_CV_guided_random.csv"
    ),
]
NETWORK_TOTAL_STATS_JSON_CANDIDATES = [
    Path(
        "/Users/suhang/Downloads/同步空间/工作文件/0-1博后论文/4.非洲路网可达性/过程文件/result/result3/"
        "finding3_NI_CV_quadrant_share/network_total_stats.json"
    )
]
QUADRANT_COUNTS_CSV_CANDIDATES = [
    Path(
        "/Users/suhang/Downloads/同步空间/工作文件/0-1博后论文/4.非洲路网可达性/过程文件/result/result3/"
        "finding3_NI_CV_quadrant_share/NI_CV_2x2_quadrant_edge_counts.csv"
    )
]
RESULT_NOTES_DOCX = Path(
    "/Users/suhang/Downloads/同步空间/工作文件/0-1博后论文/4.非洲路网可达性/过程文件/"
    "result 构思(数据补全版).docx"
)

FIGURE_STEM = "result3_bottleneck_stability_and_recovery"
LOG_PATH = OUTPUT_DIR / f"{FIGURE_STEM}_log.txt"
PANEL_A_CURVE_CSV = OUTPUT_DIR / f"{FIGURE_STEM}_panel_a_curve_data.csv"
PANEL_B_KEYPOINT_CSV = OUTPUT_DIR / f"{FIGURE_STEM}_panel_b_key_points.csv"
PANEL_A_STEM = "result3_panel_a_bottleneck_stability"
PANEL_A_PNG_PATH = OUTPUT_DIR / f"{PANEL_A_STEM}.png"
PANEL_A_PDF_PATH = OUTPUT_DIR / f"{PANEL_A_STEM}.pdf"
PANEL_B_STEM = "result3_panel_b_paving_strategy_recovery"
PANEL_B_PNG_PATH = OUTPUT_DIR / f"{PANEL_B_STEM}.png"
PANEL_B_PDF_PATH = OUTPUT_DIR / f"{PANEL_B_STEM}.pdf"

TARGET_PANEL_A_QUANTILES = [1.0, 3.0, 5.0, 10.0]
TARGET_PANEL_B_PAVING_PCTS = [0.1, 1.0, 2.0, 5.0]
PANEL_B_FOCUS_XMAX = 10.0

CM_TO_INCH = 1.0 / 2.54
FIG_SIZE = (7.0 * CM_TO_INCH, 6.0 * CM_TO_INCH)
PNG_DPI = 600
BASE_FONT_SIZE = 9.5
LABEL_SIZE = BASE_FONT_SIZE
TICK_SIZE = BASE_FONT_SIZE
TEXT_SIZE = BASE_FONT_SIZE

PANEL_A_STYLES = {
    2045: {
        "color": "#36586B",
        "linestyle": "-",
        "linewidth": 2.8,
        "line_alpha": 0.96,
        "marker_alpha": 1.00,
        "marker": "o",
        "markersize": 6.8,
        "zorder": 5.2,
    },
    2065: {
        "color": "#4E6F81",
        "linestyle": "-",
        "linewidth": 5.4,
        "line_alpha": 0.42,
        "marker_alpha": 0.95,
        "marker": "s",
        "markersize": 9.4,
        "zorder": 4.2,
    },
    2085: {
        "color": "#7F99A7",
        "linestyle": "-",
        "linewidth": 8.2,
        "line_alpha": 0.24,
        "marker_alpha": 0.90,
        "marker": "^",
        "markersize": 12.0,
        "zorder": 3.2,
    },
}
PANEL_B_COLORS = {
    "guided": "#0F5C63",
    "cv_only": "#B07A4F",
    "random": "#8E959A",
    "random_fill": "#D5D9DC",
}
GRID_COLOR = "#D7DBE0"
SPINE_COLOR = "#3A3F44"
TEXT_COLOR = "#1D1F21"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(OUTPUT_DIR / ".mplconfig"))
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator, PercentFormatter

plt.rcParams.update(
    {
        "font.family": "Times New Roman",
        "font.size": BASE_FONT_SIZE,
        "axes.labelsize": BASE_FONT_SIZE,
        "xtick.labelsize": BASE_FONT_SIZE,
        "ytick.labelsize": BASE_FONT_SIZE,
        "legend.fontsize": BASE_FONT_SIZE,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)

LOG_LINES: List[str] = []


def log(message: str = "") -> None:
    print(message)
    LOG_LINES.append(message)


def first_existing_path(paths: Sequence[Path], label: str) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"Could not locate {label}. Checked:\n" + "\n".join(str(path) for path in paths)
    )


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing required {label}: {path}")


def first_existing_optional(paths: Sequence[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def infer_scale(values: pd.Series, label: str) -> Tuple[float, str]:
    numeric = pd.to_numeric(values, errors="coerce")
    finite = numeric[np.isfinite(numeric)]
    if finite.empty:
        raise ValueError(f"{label} contains no finite values.")

    min_value = float(finite.min())
    max_value = float(finite.max())
    if min_value >= -1e-9 and max_value <= 1.000001:
        return 100.0, "0-1 proportion"
    if min_value >= -1e-9 and max_value <= 100.000001:
        return 1.0, "0-100 percent"
    raise ValueError(
        f"{label} is out of expected range: min={min_value:.6f}, max={max_value:.6f}"
    )


def find_column(columns: Sequence[str], include_patterns: Sequence[str], exclude_patterns: Sequence[str] = ()) -> str | None:
    for column in columns:
        lower = column.lower()
        if all(pattern in lower for pattern in include_patterns) and not any(
            pattern in lower for pattern in exclude_patterns
        ):
            return column
    return None


def read_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = re.sub(r"</w:(?:p|tr)>", "\n", xml)
    text = re.sub(r"<[^>]+>", " ", xml)
    text = re.sub(r"\s+", " ", text)
    return text


def extract_panel_a_curve_from_notes(path: Path, n_total: int) -> pd.DataFrame:
    require_file(path, "Result 3 notes DOCX")
    text = read_docx_text(path)
    pattern = re.compile(r"前\s*([0-9]+(?:\.[0-9]+)?)%\s*([\d,]+)\s*([0-9]+(?:\.[0-9]+)?)\s*%")
    rows = []
    seen_quantiles = set()
    for quantile_text, k_text, jaccard_text in pattern.findall(text):
        quantile_pct = float(quantile_text)
        if quantile_pct in seen_quantiles:
            continue
        if quantile_pct not in TARGET_PANEL_A_QUANTILES:
            continue
        seen_quantiles.add(quantile_pct)
        k_edges = int(k_text.replace(",", ""))
        expected_k_floor = int(np.floor(n_total * quantile_pct / 100.0))
        rows.append(
            {
                "quantile_pct": quantile_pct,
                "k_edges": k_edges,
                "jaccard_pct": float(jaccard_text),
                "expected_k_edges_floor": expected_k_floor,
                "k_matches_expected_floor": k_edges == expected_k_floor,
                "curve_source": "project_notes_docx_fallback",
            }
        )

    if not rows:
        raise ValueError(
            f"Failed to extract Panel A quantile-overlap rows from fallback notes: {path}"
        )

    curve_df = pd.DataFrame(rows).sort_values("quantile_pct").reset_index(drop=True)
    missing = sorted(set(TARGET_PANEL_A_QUANTILES) - set(curve_df["quantile_pct"]))
    if missing:
        raise ValueError(
            "Fallback notes did not provide all required Panel A quantiles. Missing: "
            + ", ".join(f"{value:g}%" for value in missing)
        )
    return curve_df


def prepare_panel_a(panel_a_path: Path, network_stats: Dict[str, int] | None = None) -> Dict[str, object]:
    report_df = pd.read_csv(panel_a_path)
    columns = list(report_df.columns)
    period_col = find_column(columns, ["period"]) or find_column(columns, ["horizon"])
    spearman_col = find_column(columns, ["spearman"])
    cv_change_col = find_column(columns, ["cv", "change"])
    summary_jaccard_col = find_column(columns, ["jaccard"])
    direct_quantile_col = find_column(columns, ["quantile"]) or find_column(columns, ["top", "pct"])
    direct_top_k_col = find_column(columns, ["top_k"], ["pct"]) or find_column(
        columns, ["top", "k"], ["pct"]
    )

    log("Panel A checks")
    log(f"1) bottleneck_stability_report.csv fields: {columns}")
    if period_col is None:
        raise ValueError("Could not identify the future-period field in Panel A report.")

    periods = sorted(int(value) for value in pd.to_numeric(report_df[period_col], errors="coerce").dropna().unique())
    log(f"2) Future horizons found: {periods}")

    direct_curve_available = False
    if direct_quantile_col is not None and len(report_df) > len(periods):
        direct_curve_available = True

    log(
        "3) Quantile/Jaccard field detection: "
        f"direct_quantile_field={direct_quantile_col!r}, jaccard_field={summary_jaccard_col!r}, "
        f"direct_curve_available={direct_curve_available}"
    )

    curve_source_note = "primary_csv_direct"
    if direct_curve_available:
        quantile_scale, _ = infer_scale(report_df[direct_quantile_col], direct_quantile_col)
        jaccard_scale, _ = infer_scale(report_df[summary_jaccard_col], summary_jaccard_col)
        curve_df = pd.DataFrame(
            {
                "period": pd.to_numeric(report_df[period_col], errors="coerce").astype(int),
                "quantile_pct": pd.to_numeric(report_df[direct_quantile_col], errors="coerce")
                * quantile_scale,
                "jaccard_pct": pd.to_numeric(report_df[summary_jaccard_col], errors="coerce")
                * jaccard_scale,
                "curve_source": "primary_csv_direct",
                "horizon_specific_curve": True,
            }
        )
        if direct_top_k_col is not None:
            curve_df["k_edges"] = pd.to_numeric(report_df[direct_top_k_col], errors="coerce").astype(int)
        elif network_stats is not None and "n_total" in network_stats:
            curve_df["k_edges"] = (
                np.floor(int(network_stats["n_total"]) * curve_df["quantile_pct"] / 100.0)
                .astype(int)
            )
        else:
            curve_df["k_edges"] = np.nan
        curve_df = (
            curve_df[curve_df["quantile_pct"].isin(TARGET_PANEL_A_QUANTILES)]
            .sort_values(["period", "quantile_pct"])
            .reset_index(drop=True)
        )
    else:
        if direct_quantile_col is None:
            log(
                "   Primary Panel A CSV does not contain a quantile field. "
                "Falling back to project notes to recover the 1/3/5/10% overlap table."
            )
        else:
            log(
                "   Primary Panel A CSV appears to be summary-only, not a quantile curve table. "
                "Falling back to project notes."
            )
        curve_source_note = "fallback_notes_docx"
        if network_stats is None or "n_total" not in network_stats:
            raise ValueError(
                "Fallback Panel A extraction requires network_stats['n_total'], "
                "but no compatible network stats were available."
            )
        curve_template = extract_panel_a_curve_from_notes(
            RESULT_NOTES_DOCX, n_total=int(network_stats["n_total"])
        )
        curve_rows = []
        for period in periods:
            for _, row in curve_template.iterrows():
                curve_rows.append(
                    {
                        "period": period,
                        "quantile_pct": float(row["quantile_pct"]),
                        "k_edges": int(row["k_edges"]),
                        "expected_k_edges_floor": int(row["expected_k_edges_floor"]),
                        "k_matches_expected_floor": bool(row["k_matches_expected_floor"]),
                        "jaccard_pct": float(row["jaccard_pct"]),
                        "curve_source": row["curve_source"],
                        "horizon_specific_curve": False,
                    }
                )
        curve_df = pd.DataFrame(curve_rows)

    log("4) Top quantile -> Jaccard values used for Panel A:")
    if direct_curve_available:
        for period in periods:
            log(f"   Period {period}:")
            period_sample = (
                curve_df[curve_df["period"] == period][["quantile_pct", "k_edges", "jaccard_pct"]]
                .sort_values("quantile_pct")
                .reset_index(drop=True)
            )
            for _, row in period_sample.iterrows():
                k_text = f"{int(row['k_edges']):,}" if pd.notna(row["k_edges"]) else "NA"
                log(
                    f"      Top {row['quantile_pct']:.0f}% (K={k_text}) -> "
                    f"Jaccard {row['jaccard_pct']:.1f}%"
                )
    else:
        curve_sample = (
            curve_df[curve_df["period"] == periods[0]][["quantile_pct", "k_edges", "jaccard_pct"]]
            .sort_values("quantile_pct")
            .reset_index(drop=True)
        )
        for _, row in curve_sample.iterrows():
            log(
                f"   Top {row['quantile_pct']:.0f}% (K={int(row['k_edges']):,}) -> "
                f"Jaccard {row['jaccard_pct']:.1f}%"
            )

    if spearman_col is None:
        raise ValueError("Could not identify the Spearman column in Panel A report.")
    summary_rows = (
        report_df.sort_values([period_col])
        .drop_duplicates(subset=[period_col])
        .reset_index(drop=True)
    )

    spearman_pairs = []
    for _, row in summary_rows.iterrows():
        spearman_pairs.append((int(row[period_col]), float(row[spearman_col])))
    log(
        "5) Spearman rho values: "
        + ", ".join(f"{period}={value:.4f}" for period, value in spearman_pairs)
    )

    if cv_change_col is None:
        raise ValueError("Could not identify the CV change column in Panel A report.")
    cv_change_pairs = []
    for _, row in summary_rows.iterrows():
        cv_change_pairs.append((int(row[period_col]), float(row[cv_change_col])))
    log(
        "6) CV change values: "
        + ", ".join(f"{period}={value:.2f}%" for period, value in cv_change_pairs)
    )

    if direct_curve_available or len(report_df) != len(periods):
        log("7) Panel A head rows:")
        log(report_df.head(10).to_string(index=False))
    else:
        log(
            "7) Panel A structure is summary-only (one row per future period). "
            "Head rows shown below for confirmation:"
        )
        log(report_df.head(10).to_string(index=False))

    annotation_rho = float(np.mean([value for _, value in spearman_pairs]))
    annotation_jaccard_5 = float(
        curve_df.loc[curve_df["quantile_pct"] == 5.0, "jaccard_pct"].mean()
    )
    annotation_cv_changes = [value for _, value in cv_change_pairs]

    return {
        "report_df": report_df,
        "curve_df": curve_df,
        "periods": periods,
        "curve_source_note": curve_source_note,
        "annotation_rho": annotation_rho,
        "annotation_jaccard_5": annotation_jaccard_5,
        "annotation_cv_changes": annotation_cv_changes,
    }


def match_fraction_row(
    df: pd.DataFrame,
    fraction_col: str,
    target_pct: float,
    fraction_scale: float,
) -> pd.Series:
    target_value = target_pct / fraction_scale if fraction_scale == 100.0 else target_pct
    distances = (pd.to_numeric(df[fraction_col], errors="coerce") - target_value).abs()
    idx = distances.idxmin()
    best_distance = float(distances.loc[idx])
    tolerance = 1e-8 if fraction_scale == 100.0 else 1e-4
    if best_distance > tolerance:
        log(
            f"   Warning: target paving fraction {target_pct:.3f}% matched to "
            f"{float(df.loc[idx, fraction_col]) * fraction_scale:.3f}% with distance {best_distance:.6g}"
        )
    return df.loc[idx]


def infer_n_unpaved_from_table(
    panel_b_df: pd.DataFrame,
    fraction_col: str,
    edges_col: str,
    fraction_scale: float,
) -> Tuple[int, str]:
    fraction_pct = pd.to_numeric(panel_b_df[fraction_col], errors="coerce") * fraction_scale
    edges = pd.to_numeric(panel_b_df[edges_col], errors="coerce")
    valid = np.isfinite(fraction_pct) & np.isfinite(edges) & (fraction_pct > 0) & (edges > 0)
    if not valid.any():
        raise ValueError("Cannot infer n_unpaved because Panel B table has no positive paving rows.")

    preferred_pcts = [1.0, 2.0, 5.0, 0.1]
    for preferred_pct in preferred_pcts:
        mask = valid & np.isclose(fraction_pct, preferred_pct, atol=1e-9)
        if mask.any():
            row = panel_b_df.loc[mask].iloc[0]
            actual_pct = float(row[fraction_col]) * fraction_scale
            n_unpaved = int(round(float(row[edges_col]) * 100.0 / actual_pct))
            return n_unpaved, f"exact row at {actual_pct:.3f}%"

    estimates = np.round(edges[valid] * 100.0 / fraction_pct[valid]).astype(int)
    return int(np.median(estimates)), "median across positive paving rows"


def format_pct_for_label(value: float, decimals_if_small: int = 2, default_decimals: int = 1) -> str:
    if abs(value) < 0.1:
        return f"{value:.{decimals_if_small}f}%"
    return f"{value:.{default_decimals}f}%"


def prepare_panel_b(
    panel_b_path: Path,
    network_stats_path: Path | None = None,
    quadrant_path: Path | None = None,
) -> Dict[str, object]:
    panel_b_df = pd.read_csv(panel_b_path)
    columns = list(panel_b_df.columns)
    log("")
    log("Panel B checks")
    log(f"8) {panel_b_path.name} fields: {columns}")

    fraction_col = find_column(columns, ["paving", "fraction"])
    edges_col = find_column(columns, ["n_edges", "paved"]) or find_column(columns, ["edges", "paved"])
    guided_col = "recovery_guided" if "recovery_guided" in columns else find_column(columns, ["recovery", "guided"])
    ni_only_col = "recovery_ni_only" if "recovery_ni_only" in columns else find_column(columns, ["recovery", "ni"])
    cv_only_col = "recovery_cv_only" if "recovery_cv_only" in columns else find_column(columns, ["recovery", "cv"])
    random_mean_col = (
        "recovery_rand_mean" if "recovery_rand_mean" in columns else find_column(columns, ["recovery", "rand"])
    )
    random_std_col = "recovery_rand_std" if "recovery_rand_std" in columns else find_column(columns, ["std"])

    required = {
        "paving fraction": fraction_col,
        "n_edges_paved": edges_col,
        "guided recovery": guided_col,
        "NI-only recovery": ni_only_col,
        "CV-only recovery": cv_only_col,
        "random recovery": random_mean_col,
    }
    missing = [label for label, column in required.items() if column is None]
    if missing:
        raise ValueError("Missing Panel B fields: " + ", ".join(missing))

    fraction_scale, fraction_unit = infer_scale(panel_b_df[fraction_col], "paving_fraction")
    guided_scale, guided_unit = infer_scale(panel_b_df[guided_col], guided_col)
    cv_scale, cv_unit = infer_scale(panel_b_df[cv_only_col], cv_only_col)
    random_scale, random_unit = infer_scale(panel_b_df[random_mean_col], random_mean_col)
    ni_scale, ni_unit = infer_scale(panel_b_df[ni_only_col], ni_only_col)

    log(
        "9) Field mapping: "
        f"fraction={fraction_col}, edges={edges_col}, guided={guided_col}, "
        f"ni_only={ni_only_col}, cv_only={cv_only_col}, random_mean={random_mean_col}, "
        f"random_std={random_std_col}"
    )
    log(f"10) Paving fraction unit inference: {fraction_unit} (scale factor to % = {fraction_scale:.1f})")

    inferred_n_unpaved, inference_note = infer_n_unpaved_from_table(
        panel_b_df, fraction_col, edges_col, fraction_scale
    )
    network_stats: Dict[str, int] = {"n_unpaved": inferred_n_unpaved}
    quadrant_df: pd.DataFrame | None = None

    log(
        "12) network stats source: "
        f"inferred n_unpaved={inferred_n_unpaved:,} from {inference_note}"
    )
    if network_stats_path is not None:
        external_stats = json.loads(network_stats_path.read_text(encoding="utf-8"))
        log(f"   Auxiliary network_total_stats.json candidate: {json.dumps(external_stats, ensure_ascii=False)}")
        external_n_unpaved = external_stats.get("n_unpaved")
        if external_n_unpaved is not None:
            external_n_unpaved = int(external_n_unpaved)
            diff = abs(external_n_unpaved - inferred_n_unpaved)
            tolerance = max(50, int(round(external_n_unpaved * 0.005)))
            if diff <= tolerance:
                network_stats.update({k: int(v) for k, v in external_stats.items() if isinstance(v, (int, float))})
                network_stats["n_unpaved"] = external_n_unpaved
                log(
                    f"   Auxiliary n_unpaved={external_n_unpaved:,} is consistent with the current paving table; "
                    "using auxiliary stats where available."
                )
                if quadrant_path is not None:
                    quadrant_df = pd.read_csv(quadrant_path)
                    quadrant_sum = int(pd.to_numeric(quadrant_df["n_edges"], errors="coerce").sum())
                    high_ni_unpaved = int(
                        pd.to_numeric(
                            quadrant_df.loc[
                                quadrant_df["quadrant"].astype(str).str.contains("High NI", na=False), "n_edges"
                            ],
                            errors="coerce",
                        ).sum()
                    )
                    log(
                        f"   Quadrant edge count sum = {quadrant_sum:,} "
                        f"(should equal n_unpaved={int(network_stats['n_unpaved']):,})"
                    )
                    if "n_ni_positive" in network_stats:
                        log(
                            f"   High-NI unpaved edges from quadrant table = {high_ni_unpaved:,}; "
                            f"n_ni_positive from JSON = {int(network_stats['n_ni_positive']):,}"
                        )
            else:
                log(
                    f"   Auxiliary n_unpaved={external_n_unpaved:,} is inconsistent with the current paving table "
                    f"(inferred {inferred_n_unpaved:,}); ignoring auxiliary stats for this redraw."
                )
    else:
        log("   No auxiliary network_total_stats.json candidate was found for this data version.")

    max_guided_vs_ni_gap_pp = float(
        (panel_b_df[guided_col] * guided_scale - panel_b_df[ni_only_col] * ni_scale).abs().max()
    )
    log(
        f"   Guided vs NI-only maximum absolute gap = {max_guided_vs_ni_gap_pp:.3f} percentage points; "
        "the guided curve is therefore effectively NI-led."
    )

    key_rows = []
    log("11) Target paving fractions 0.1%, 1%, 2%, 5% availability:")
    for target_pct in TARGET_PANEL_B_PAVING_PCTS:
        row = match_fraction_row(panel_b_df, fraction_col, target_pct, fraction_scale)
        actual_pct = float(row[fraction_col]) * fraction_scale
        n_edges_data = int(row[edges_col])
        expected_edges = int(round(int(network_stats["n_unpaved"]) * target_pct / 100.0))
        guided_pct = float(row[guided_col]) * guided_scale
        cv_pct = float(row[cv_only_col]) * cv_scale
        random_pct = float(row[random_mean_col]) * random_scale
        random_pct_rounded_1dp = round(random_pct, 1)
        leverage_raw = np.nan if random_pct <= 0 else guided_pct / random_pct
        leverage_rounded = (
            np.nan if random_pct_rounded_1dp <= 0 else guided_pct / random_pct_rounded_1dp
        )
        key_rows.append(
            {
                "target_paving_fraction_pct": target_pct,
                "matched_paving_fraction_pct": actual_pct,
                "n_edges_paved_from_data": n_edges_data,
                "n_edges_paved_from_n_unpaved": expected_edges,
                "guided_recovery_pct": guided_pct,
                "ni_only_recovery_pct": float(row[ni_only_col]) * ni_scale,
                "cv_only_recovery_pct": cv_pct,
                "random_recovery_pct_raw": random_pct,
                "random_recovery_pct_rounded_1dp": random_pct_rounded_1dp,
                "leverage_vs_random_raw": leverage_raw,
                "leverage_vs_random_rounded_1dp": leverage_rounded,
            }
        )
        log(
            f"   {target_pct:.1f}% -> matched {actual_pct:.3f}%, data edges={n_edges_data:,}, "
            f"computed edges={expected_edges:,}"
        )

    key_points_df = pd.DataFrame(key_rows)
    log("13) n_unpaved-based edge counts for 0.1%, 1%, 2%, 5%:")
    for _, row in key_points_df.iterrows():
        log(
            f"   {row['target_paving_fraction_pct']:.1f}% -> "
            f"{int(row['n_edges_paved_from_n_unpaved']):,} edges"
        )

    log("14) Guided recovery and leverage ratios at key points:")
    for _, row in key_points_df.iterrows():
        log(
            f"   {row['target_paving_fraction_pct']:.1f}% -> guided={row['guided_recovery_pct']:.1f}%, "
            f"CV-only={row['cv_only_recovery_pct']:.1f}%, random(raw)={row['random_recovery_pct_raw']:.3f}%, "
            f"leverage(raw)={row['leverage_vs_random_raw']:.1f}x, "
            f"leverage(rounded-random)={row['leverage_vs_random_rounded_1dp']:.1f}x"
        )

    warnings = []
    if fraction_unit != "0-1 proportion":
        warnings.append(f"paving_fraction inferred as {fraction_unit}, not the expected 0-1 scale")
    if guided_unit != "0-1 proportion":
        warnings.append(f"{guided_col} inferred as {guided_unit}")
    if random_unit != "0-1 proportion":
        warnings.append(f"{random_mean_col} inferred as {random_unit}")

    if warnings:
        log("15) Warnings / mismatches:")
        for warning in warnings:
            log(f"   {warning}")
    else:
        random_01_row = key_points_df.loc[
            np.isclose(key_points_df["target_paving_fraction_pct"], 0.1, atol=1e-9)
        ].iloc[0]
        log(
            "15) No missing values or field-name mismatches blocked extraction. "
            "Display note: very small random-recovery labels should not be rounded too aggressively; "
            f"at 0.1% paving the raw random mean is {float(random_01_row['random_recovery_pct_raw']):.3f}%."
        )

    return {
        "panel_b_df": panel_b_df,
        "fraction_col": fraction_col,
        "edges_col": edges_col,
        "guided_col": guided_col,
        "ni_only_col": ni_only_col,
        "cv_only_col": cv_only_col,
        "random_mean_col": random_mean_col,
        "random_std_col": random_std_col,
        "fraction_scale": fraction_scale,
        "guided_scale": guided_scale,
        "cv_scale": cv_scale,
        "random_scale": random_scale,
        "network_stats": network_stats,
        "quadrant_df": quadrant_df,
        "key_points_df": key_points_df,
        "guided_vs_ni_gap_pp": max_guided_vs_ni_gap_pp,
    }


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor("white")
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.8, alpha=0.9)
    ax.grid(axis="x", visible=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(SPINE_COLOR)
    ax.spines["bottom"].set_color(SPINE_COLOR)
    ax.tick_params(axis="both", labelsize=TICK_SIZE, colors=SPINE_COLOR)


def plot_panel_a(ax: plt.Axes, panel_a: Dict[str, object]) -> None:
    curve_df = panel_a["curve_df"]
    periods = panel_a["periods"]
    legend_handles = []

    reference_curve = curve_df[curve_df["period"] == periods[0]].sort_values("quantile_pct")
    ax.plot(
        reference_curve["quantile_pct"],
        reference_curve["jaccard_pct"],
        color="#C4D0D7",
        linewidth=10.5,
        alpha=0.18,
        solid_capstyle="round",
        zorder=2.0,
    )

    # Draw the widest, most transparent line first so the overlap itself becomes visible.
    for period in sorted(periods, reverse=True):
        period_curve = curve_df[curve_df["period"] == period].sort_values("quantile_pct")
        style = PANEL_A_STYLES.get(
            int(period),
            {
                "color": "#657786",
                "linestyle": "-",
                "linewidth": 2.3,
                "line_alpha": 0.9,
                "marker_alpha": 1.0,
                "marker": "o",
                "markersize": 6.0,
                "zorder": 3.0,
            },
        )
        ax.plot(
            period_curve["quantile_pct"],
            period_curve["jaccard_pct"],
            color=style["color"],
            linestyle=style["linestyle"],
            linewidth=style["linewidth"],
            alpha=style["line_alpha"],
            solid_capstyle="round",
            zorder=style["zorder"],
        )
        ax.plot(
            period_curve["quantile_pct"],
            period_curve["jaccard_pct"],
            linestyle="",
            marker=style["marker"],
            markersize=style["markersize"],
            markerfacecolor="white",
            markeredgewidth=1.35,
            markeredgecolor=style["color"],
            alpha=style["marker_alpha"],
            zorder=style["zorder"] + 0.1,
        )
        legend_handles.append(
            Line2D(
                [0],
                [0],
                color=style["color"],
                linestyle=style["linestyle"],
                linewidth=min(style["linewidth"], 3.6),
                marker=style["marker"],
                markersize=max(6.0, style["markersize"] * 0.78),
                markerfacecolor="white",
                markeredgewidth=1.2,
                markeredgecolor=style["color"],
                label=str(period),
            )
        )

    ax.set_xlim(0.7, 10.3)
    ax.set_ylim(48, 95.3)
    ax.set_xticks(TARGET_PANEL_A_QUANTILES)
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.set_xlabel("Top-k quantile (%)", fontsize=LABEL_SIZE, color=TEXT_COLOR)
    ax.set_ylabel("Jaccard overlap (%)", fontsize=LABEL_SIZE, color=TEXT_COLOR)
    style_axis(ax)

    cv_change_text = ", ".join(f"{value:.1f}" for value in panel_a["annotation_cv_changes"])
    annotation = (
        f"ρ = {panel_a['annotation_rho']:.3f}"
        "\n"
        f"J@5% = {panel_a['annotation_jaccard_5']:.0f}%"
        "\n"
        f"ΔCV = {cv_change_text}%"
    )
    ax.text(
        0.065,
        0.997,
        annotation,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=TEXT_SIZE * 0.92,
        color=TEXT_COLOR,
        linespacing=1.0,
        bbox=dict(boxstyle="round,pad=0.22", facecolor="white", edgecolor="#C9CED3", linewidth=0.8),
    )
    ax.legend(
        handles=sorted(legend_handles, key=lambda handle: int(handle.get_label())),
        frameon=False,
        fontsize=TEXT_SIZE,
        loc="lower right",
        handlelength=1.6,
        handletextpad=0.55,
        labelspacing=0.3,
        borderpad=0.2,
    )


def plot_panel_b(ax: plt.Axes, panel_b: Dict[str, object]) -> None:
    df = panel_b["panel_b_df"].copy()
    fraction_col = panel_b["fraction_col"]
    guided_col = panel_b["guided_col"]
    cv_only_col = panel_b["cv_only_col"]
    random_mean_col = panel_b["random_mean_col"]
    random_std_col = panel_b["random_std_col"]

    x_pct = pd.to_numeric(df[fraction_col], errors="coerce") * float(panel_b["fraction_scale"])
    guided_pct = pd.to_numeric(df[guided_col], errors="coerce") * float(panel_b["guided_scale"])
    cv_pct = pd.to_numeric(df[cv_only_col], errors="coerce") * float(panel_b["cv_scale"])
    random_pct = pd.to_numeric(df[random_mean_col], errors="coerce") * float(panel_b["random_scale"])
    random_std_pct = (
        pd.to_numeric(df[random_std_col], errors="coerce") * float(panel_b["random_scale"])
        if random_std_col is not None
        else pd.Series(np.zeros(len(df)), index=df.index)
    )

    focus_mask = x_pct <= PANEL_B_FOCUS_XMAX
    x_focus = x_pct[focus_mask]
    guided_focus = guided_pct[focus_mask]
    cv_focus = cv_pct[focus_mask]
    random_focus = random_pct[focus_mask]
    random_std_focus = random_std_pct[focus_mask]

    ax.fill_between(
        x_focus,
        np.maximum(0, random_focus - random_std_focus),
        random_focus + random_std_focus,
        color=PANEL_B_COLORS["random_fill"],
        alpha=0.55,
        linewidth=0,
        zorder=1,
    )
    ax.plot(
        x_focus,
        random_focus,
        color=PANEL_B_COLORS["random"],
        linewidth=1.9,
        linestyle=(0, (1.5, 1.8)),
        label="Random",
        zorder=2,
    )
    ax.plot(
        x_focus,
        cv_focus,
        color=PANEL_B_COLORS["cv_only"],
        linewidth=2.1,
        linestyle=(0, (5, 2)),
        marker="o",
        markersize=4.0,
        markerfacecolor="white",
        markeredgewidth=0.9,
        label="CV-guided",
        zorder=3,
    )
    ax.plot(
        x_focus,
        guided_focus,
        color=PANEL_B_COLORS["guided"],
        linewidth=2.8,
        marker="o",
        markersize=4.8,
        markerfacecolor="white",
        markeredgewidth=1.0,
        label="NI-led guided",
        zorder=4,
    )

    key_points_df = panel_b["key_points_df"]
    label_positions = {
        0.1: (1.30, 56.8),
        1.0: (2.40, 81.9),
        2.0: (2.55, 103.2),
        5.0: (5.15, 93.3),
    }
    for _, row in key_points_df.iterrows():
        x_value = float(row["matched_paving_fraction_pct"])
        y_value = float(row["guided_recovery_pct"])
        target_pct = float(row["target_paving_fraction_pct"])
        ax.scatter(
            x_value,
            y_value,
            s=26,
            color=PANEL_B_COLORS["guided"],
            zorder=5,
        )
        if target_pct not in label_positions:
            continue
        label_x, label_y = label_positions[target_pct]
        ax.annotate(
            f"{target_pct:.1f}% -> {y_value:.1f}%",
            xy=(x_value, y_value),
            xytext=(label_x, label_y),
            textcoords="data",
            fontsize=TEXT_SIZE,
            color=TEXT_COLOR,
            ha="left",
            va="center",
            bbox=dict(
                boxstyle="round,pad=0.16",
                facecolor="white",
                edgecolor="#D3D7DB",
                linewidth=0.7,
                alpha=0.96,
            ),
            arrowprops=dict(
                arrowstyle="-",
                color="#9AA3AA",
                lw=0.9,
                shrinkA=4,
                shrinkB=4,
            ),
        )

    random_point = key_points_df.loc[
        np.isclose(key_points_df["target_paving_fraction_pct"], 0.1, atol=1e-9)
    ]
    if not random_point.empty:
        random_row = random_point.iloc[0]
        rnd_x = float(random_row["matched_paving_fraction_pct"])
        rnd_y = float(random_row["random_recovery_pct_raw"])
        ax.scatter(
            rnd_x,
            rnd_y,
            s=24,
            facecolor="white",
            edgecolor=PANEL_B_COLORS["random"],
            linewidth=1.0,
            zorder=5,
        )
        ax.annotate(
            f"Rnd 0.1% -> {format_pct_for_label(rnd_y)}",
            xy=(rnd_x, rnd_y),
            xytext=(1.05, 10.8),
            textcoords="data",
            fontsize=TEXT_SIZE,
            color=TEXT_COLOR,
            ha="left",
            va="center",
            bbox=dict(
                boxstyle="round,pad=0.16",
                facecolor="white",
                edgecolor="#D3D7DB",
                linewidth=0.7,
                alpha=0.96,
            ),
            arrowprops=dict(
                arrowstyle="-",
                color="#A4ABB2",
                lw=0.9,
                shrinkA=4,
                shrinkB=4,
            ),
        )

    ax.set_xlim(0, PANEL_B_FOCUS_XMAX)
    ax.set_ylim(0, 106.8)
    ax.set_xticks([0, 1, 2, 5, 10])
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    ax.yaxis.set_major_locator(MultipleLocator(20))
    ax.set_xlabel("Paving fraction of\nunpaved roads (%)", fontsize=LABEL_SIZE, color=TEXT_COLOR)
    ax.set_ylabel("Network recovery rate (%)", fontsize=LABEL_SIZE, color=TEXT_COLOR)
    style_axis(ax)
    ax.text(
        6.55,
        100.8,
        "NI",
        fontsize=TEXT_SIZE,
        color=PANEL_B_COLORS["guided"],
        ha="left",
        va="bottom",
    )
    ax.text(
        6.18,
        12.0,
        "Rnd",
        fontsize=TEXT_SIZE,
        color=PANEL_B_COLORS["random"],
        ha="left",
        va="bottom",
    )
    ax.text(
        6.18,
        5.8,
        "CV",
        fontsize=TEXT_SIZE,
        color=PANEL_B_COLORS["cv_only"],
        ha="left",
        va="bottom",
    )


def build_panel_a_figure(panel_a: Dict[str, object]) -> None:
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    plot_panel_a(ax, panel_a)
    fig.subplots_adjust(left=0.21, right=0.98, bottom=0.19, top=0.97)
    fig.savefig(PANEL_A_PNG_PATH, dpi=PNG_DPI, facecolor="white")
    fig.savefig(PANEL_A_PDF_PATH, facecolor="white")
    plt.close(fig)


def build_panel_b_figure(panel_b: Dict[str, object]) -> None:
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    plot_panel_b(ax, panel_b)
    fig.subplots_adjust(left=0.22, right=0.98, bottom=0.25, top=0.97)
    fig.savefig(PANEL_B_PNG_PATH, dpi=PNG_DPI, facecolor="white")
    fig.savefig(PANEL_B_PDF_PATH, facecolor="white")
    plt.close(fig)


def main() -> int:
    panel_a_path = first_existing_path(PANEL_A_REPORT_CANDIDATES, "Panel A report CSV")
    panel_b_path = first_existing_path(PANEL_B_CSV_CANDIDATES, "Panel B CSV")
    network_stats_path = first_existing_optional(NETWORK_TOTAL_STATS_JSON_CANDIDATES)
    quadrant_path = first_existing_optional(QUADRANT_COUNTS_CSV_CANDIDATES)

    log(f"Using Panel A report: {panel_a_path}")
    log(f"Using Panel B curve table: {panel_b_path}")
    if network_stats_path is not None:
        log(f"Using auxiliary stats candidate: {network_stats_path}")
    else:
        log("Using auxiliary stats candidate: none")
    if quadrant_path is not None:
        log(f"Using auxiliary quadrant candidate: {quadrant_path}")
    else:
        log("Using auxiliary quadrant candidate: none")

    panel_a = prepare_panel_a(panel_a_path)
    panel_b = prepare_panel_b(panel_b_path, network_stats_path, quadrant_path)

    panel_a["curve_df"].to_csv(PANEL_A_CURVE_CSV, index=False)
    panel_b["key_points_df"].to_csv(PANEL_B_KEYPOINT_CSV, index=False)

    log("")
    log("Creating separate panel figures...")
    build_panel_a_figure(panel_a)
    build_panel_b_figure(panel_b)
    log(f"Saved Panel A PNG: {PANEL_A_PNG_PATH}")
    log(f"Saved Panel A PDF: {PANEL_A_PDF_PATH}")
    log(f"Saved Panel B PNG: {PANEL_B_PNG_PATH}")
    log(f"Saved Panel B PDF: {PANEL_B_PDF_PATH}")
    log(f"Saved Panel A curve CSV: {PANEL_A_CURVE_CSV}")
    log(f"Saved Panel B key-point CSV: {PANEL_B_KEYPOINT_CSV}")
    log(f"Panel A curve source note: {panel_a['curve_source_note']}")
    log(
        "Panel B note: legend uses the NI-led guided curve from 'recovery_guided' because "
        "it matches the manuscript headline values and differs from NI-only by at most "
        f"{panel_b['guided_vs_ni_gap_pp']:.3f} percentage points."
    )

    LOG_PATH.write_text("\n".join(LOG_LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        message = f"ERROR: {exc}"
        print(message, file=sys.stderr)
        if LOG_LINES:
            LOG_LINES.append(message)
            LOG_PATH.write_text("\n".join(LOG_LINES) + "\n", encoding="utf-8")
        raise
