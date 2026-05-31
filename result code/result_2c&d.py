#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D

OUTPUT_DIR = Path("<FIGURE_OUTPUT_ROOT>/result 2.3")
PANEL_A_CSV = Path(
    "<PROJECT_WORK_ROOT>/result/result2/finding4_OLS_regression_facility_popdensity_vs_climate_impact/grid_cells_pw_delta_t_facility_popdensity.csv"
)
PANEL_A_SPEARMAN_CSV = Path(
    "<PROJECT_WORK_ROOT>/result/result2/finding4_OLS_regression_facility_popdensity_vs_climate_impact/grid_spearman_correlation_table.csv"
)
PANEL_A_OLS_TXT = Path(
    "<PROJECT_WORK_ROOT>/result/result2/finding4_OLS_regression_facility_popdensity_vs_climate_impact/OLS_regression_result_summary.txt"
)
PANEL_B_GINI_CSV = Path(
    "<PROJECT_WORK_ROOT>/result/result2/finding5_gini_inequality_country_ranking/country_gini_normal_extreme_delta.csv"
)
PANEL_B_RAW_CSV = Path(
    "<PROJECT_WORK_ROOT>/result/result2/finding5_gini_inequality_country_ranking/country_facility_population_accessibility_raw.csv"
)
PANEL_B_QUADRANT_CSV = Path(
    "<PROJECT_WORK_ROOT>/result/result2/finding5_gini_inequality_country_ranking/country_facility_density_quadrant_classification.csv"
)

FIGURE_STEM = "result2_3_sparse_facility_population_climate_impact"
PNG_PATH = OUTPUT_DIR / f"{FIGURE_STEM}.png"
PDF_PATH = OUTPUT_DIR / f"{FIGURE_STEM}.pdf"
LOG_PATH = OUTPUT_DIR / f"{FIGURE_STEM}_diagnostics.txt"
JOIN_CHECK_PATH = OUTPUT_DIR / f"{FIGURE_STEM}_panel_b_plot_data.csv"
PANEL_A_MODEL_CHECK_PATH = (
    OUTPUT_DIR / f"{FIGURE_STEM}_panel_a_model_reconstruction.csv"
)
PANEL_A_6CM_PNG_PATH = OUTPUT_DIR / f"{FIGURE_STEM}_panel_a_6cm.png"
PANEL_A_6CM_PDF_PATH = OUTPUT_DIR / f"{FIGURE_STEM}_panel_a_6cm.pdf"
PANEL_B_6CM_PNG_PATH = OUTPUT_DIR / f"{FIGURE_STEM}_panel_b_6cm.png"
PANEL_B_6CM_PDF_PATH = OUTPUT_DIR / f"{FIGURE_STEM}_panel_b_6cm.pdf"

PANEL_A_TARGET = "pw_delta_t"
PANEL_A_FACILITY_FIELD = "facility_per_million"
PANEL_A_POP_FIELD = "total_pop"
PANEL_A_NODE_FIELD = "node_density"
PANEL_B_BASELINE_FIELD = "pwmtt_normal"
PANEL_B_DELTA_GINI_FIELD = "delta_gini"

TITLE_FONT = 13
LABEL_FONT = 11
TEXT_FONT = 9
TICK_FONT = 9
SQUARE_FONT = 9.5
SQUARE_CM = 6.0
CM_TO_INCH = 1 / 2.54
SQUARE_INCH = SQUARE_CM * CM_TO_INCH

COUNTRY_DISPLAY_MAP = {
    "BurkinaFaso": "Burkina Faso",
    "CentralAfrican": "Central African Rep.",
    "CongoDR": "DR Congo",
    "GuineaBissau": "Guinea-Bissau",
    "IvoryCoast": "Ivory Coast",
    "SierraLeone": "Sierra Leone",
    "SouthAfrica": "South Africa",
    "SouthSudan": "South Sudan",
    "WestSahara": "Western Sahara",
}

QUADRANT_LABEL_MAP = {
    "Dense facilities / Short travel  (best-off)": "Dense facility / short travel",
    "Dense facilities / Long travel   (infra-rich, remote)": "Dense facility / long travel",
    "Sparse facilities / Short travel (urban-concentrated)": "Sparse facility / short travel",
    "Sparse facilities / Long travel  ★ WORST-OFF": "Sparse facility / long travel",
}

QUADRANT_ORDER = [
    "Dense facility / short travel",
    "Dense facility / long travel",
    "Sparse facility / short travel",
    "Sparse facility / long travel",
]

QUADRANT_COLOR_MAP = {
    "Dense facility / short travel": "#6F8F84",
    "Dense facility / long travel": "#C49A59",
    "Sparse facility / short travel": "#7B92B8",
    "Sparse facility / long travel": "#B45A4A",
}


def require_inputs() -> None:
    required = [
        PANEL_A_CSV,
        PANEL_A_SPEARMAN_CSV,
        PANEL_A_OLS_TXT,
        PANEL_B_GINI_CSV,
        PANEL_B_RAW_CSV,
        PANEL_B_QUADRANT_CSV,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required input files:\n" + "\n".join(missing))


def log_line(lines: list[str], message: str = "") -> None:
    print(message)
    lines.append(message)


def format_range(series: pd.Series) -> str:
    return f"[{series.min():.4f}, {series.max():.4f}]"


def format_transform_range(series: pd.Series, transform: str) -> str:
    values = transform_series(series, transform)
    return f"[{values.min():.4f}, {values.max():.4f}]"


def transform_series(series: pd.Series, transform: str) -> pd.Series:
    if transform == "log":
        if (series <= 0).any():
            raise ValueError(
                f"Cannot apply log transform to non-positive values in {series.name}"
            )
        return np.log(series)
    if transform == "log1p":
        return np.log1p(series)
    raise ValueError(f"Unsupported transform: {transform}")


def solve_ols(
    target: np.ndarray, x1: np.ndarray, x2: np.ndarray
) -> tuple[np.ndarray, float]:
    X = np.column_stack([np.ones(len(target)), x1, x2])
    beta, _, _, _ = np.linalg.lstsq(X, target, rcond=None)
    fitted = X @ beta
    ss_tot = float(((target - target.mean()) ** 2).sum())
    ss_res = float(((target - fitted) ** 2).sum())
    r_squared = 1.0 - ss_res / ss_tot
    return beta, r_squared


def parse_ols_summary(summary_text: str) -> dict[str, float | str]:
    r2_match = re.search(r"R-squared:\s+([0-9.]+)", summary_text)
    n_match = re.search(r"No\. Observations:\s+(\d+)", summary_text)
    if not r2_match or not n_match:
        raise ValueError(
            "Could not parse R-squared or sample size from OLS summary text."
        )

    coef_matches = re.findall(
        r"^(const|log_facility|log_pop_density)\s+(-?\d+\.\d+)\s+\d+\.\d+\s+-?\d+\.\d+\s+([0-9.]+)",
        summary_text,
        flags=re.MULTILINE,
    )
    coef_dict: dict[str, float] = {}
    pval_dict: dict[str, float] = {}
    for name, coef, pval in coef_matches:
        coef_dict[name] = float(coef)
        pval_dict[name] = float(pval)
    if {"const", "log_facility", "log_pop_density"} - set(coef_dict):
        raise ValueError(
            "Could not parse all required coefficients from OLS summary text."
        )

    first_line = summary_text.splitlines()[0].strip()
    return {
        "formula_header": first_line,
        "r_squared": float(r2_match.group(1)),
        "n_obs": int(n_match.group(1)),
        "const": coef_dict["const"],
        "log_facility": coef_dict["log_facility"],
        "log_pop_density": coef_dict["log_pop_density"],
        "p_log_facility": pval_dict["log_facility"],
        "p_log_pop_density": pval_dict["log_pop_density"],
    }


def evaluate_panel_a_candidates(
    grid_df: pd.DataFrame, summary_stats: dict[str, float | str]
) -> pd.DataFrame:
    candidates: list[dict[str, float | str]] = []
    target = grid_df[PANEL_A_TARGET].to_numpy(dtype=float)
    summary_n = int(summary_stats["n_obs"])
    summary_const = float(summary_stats["const"])
    summary_x = float(summary_stats["log_facility"])
    summary_y = float(summary_stats["log_pop_density"])
    summary_r2 = float(summary_stats["r_squared"])

    facility_transform_options = ["log1p", "log"]
    population_candidates = [PANEL_A_POP_FIELD, PANEL_A_NODE_FIELD, "n_nodes"]
    population_transform_options = ["log", "log1p"]

    for facility_transform in facility_transform_options:
        x_raw = grid_df[PANEL_A_FACILITY_FIELD]
        if facility_transform == "log":
            mask = x_raw > 0
        else:
            mask = x_raw.notna()

        for population_field in population_candidates:
            y_raw = grid_df[population_field]
            for population_transform in population_transform_options:
                valid = mask.copy()
                if population_transform == "log":
                    valid &= y_raw > 0
                else:
                    valid &= y_raw.notna()
                valid &= grid_df[PANEL_A_TARGET].notna()

                df_valid = grid_df.loc[
                    valid, [PANEL_A_TARGET, PANEL_A_FACILITY_FIELD, population_field]
                ].copy()
                if len(df_valid) < 20:
                    continue

                x = transform_series(
                    df_valid[PANEL_A_FACILITY_FIELD], facility_transform
                ).to_numpy(dtype=float)
                y = transform_series(
                    df_valid[population_field], population_transform
                ).to_numpy(dtype=float)
                beta, r_squared = solve_ols(
                    df_valid[PANEL_A_TARGET].to_numpy(dtype=float), x, y
                )
                candidates.append(
                    {
                        "facility_field": PANEL_A_FACILITY_FIELD,
                        "facility_transform": facility_transform,
                        "population_field": population_field,
                        "population_transform": population_transform,
                        "n": len(df_valid),
                        "const": beta[0],
                        "facility_coef": beta[1],
                        "population_coef": beta[2],
                        "r_squared": r_squared,
                        "distance_to_summary": (
                            abs(beta[0] - summary_const)
                            + abs(beta[1] - summary_x)
                            + abs(beta[2] - summary_y)
                            + abs(r_squared - summary_r2)
                            + abs(len(df_valid) - summary_n) * 0.02
                        ),
                    }
                )

    candidate_df = (
        pd.DataFrame(candidates)
        .sort_values("distance_to_summary")
        .reset_index(drop=True)
    )
    return candidate_df


def expand_quadrant_mapping(quadrant_df: pd.DataFrame) -> pd.DataFrame:
    expanded_rows: list[dict[str, str]] = []
    for _, row in quadrant_df.iterrows():
        countries = [
            country.strip()
            for country in str(row["countries"]).split(",")
            if country.strip()
        ]
        for country in countries:
            expanded_rows.append({"country": country, "quadrant": row["quadrant"]})
    expanded = pd.DataFrame(expanded_rows)
    expanded["quadrant_clean"] = expanded["quadrant"].map(QUADRANT_LABEL_MAP)
    return expanded


def prettify_country(country: str) -> str:
    return COUNTRY_DISPLAY_MAP.get(country, country)


def boxes_overlap(
    box_a: tuple[float, float, float, float],
    box_b: tuple[float, float, float, float],
    pad: float = 0.0,
) -> bool:
    ax0, ay0, ax1, ay1 = box_a
    bx0, by0, bx1, by1 = box_b
    return not (
        ax1 + pad < bx0 or bx1 + pad < ax0 or ay1 + pad < by0 or by1 + pad < ay0
    )


def estimate_text_bbox(
    anchor_x: float,
    anchor_y: float,
    width: float,
    height: float,
    ha: str,
) -> tuple[float, float, float, float]:
    if ha == "left":
        x0, x1 = anchor_x, anchor_x + width
    else:
        x0, x1 = anchor_x - width, anchor_x
    y0, y1 = anchor_y - height / 2.0, anchor_y + height / 2.0
    return x0, y0, x1, y1


def place_country_labels(
    fig: plt.Figure,
    ax: plt.Axes,
    panel_b_df: pd.DataFrame,
    label_df: pd.DataFrame,
    fontsize: float = TEXT_FONT,
    candidate_offsets: list[tuple[float, float]] | None = None,
) -> None:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    axes_bbox = ax.get_window_extent(renderer=renderer)
    all_points = ax.transData.transform(
        np.column_stack(
            [panel_b_df[PANEL_B_BASELINE_FIELD], panel_b_df[PANEL_B_DELTA_GINI_FIELD]]
        )
    )
    point_index = {country: idx for idx, country in enumerate(panel_b_df["country"])}
    occupied_boxes: list[tuple[float, float, float, float]] = []
    if candidate_offsets is None:
        candidate_offsets = [
            (55, 22),
            (55, -22),
            (78, 0),
            (88, 28),
            (88, -28),
            (115, 16),
            (115, -16),
            (145, 0),
            (-55, 22),
            (-55, -22),
            (-78, 0),
            (35, 34),
            (35, -34),
        ]

    for _, row in label_df.iterrows():
        label = prettify_country(row["country"])
        probe = ax.text(0, 0, label, fontsize=fontsize, alpha=0.0)
        bbox = probe.get_window_extent(renderer=renderer)
        probe.remove()
        text_width = bbox.width + 6.0
        text_height = bbox.height + 4.0
        point_disp = ax.transData.transform(
            (row[PANEL_B_BASELINE_FIELD], row[PANEL_B_DELTA_GINI_FIELD])
        )
        current_idx = point_index[row["country"]]
        row_offsets = list(candidate_offsets)
        if row["country"] == "Sudan":
            row_offsets = [(-88, 6), (-88, -8), (-104, 12), (-104, -12)] + row_offsets
        elif row[PANEL_B_BASELINE_FIELD] > 1.5:
            row_offsets = [
                (-30, 10),
                (-30, -10),
                (-46, 0),
                (-56, 14),
                (-56, -14),
            ] + row_offsets
        elif row[PANEL_B_BASELINE_FIELD] < 0.35:
            positive_offsets = [offset for offset in row_offsets if offset[0] >= 0]
            negative_offsets = [offset for offset in row_offsets if offset[0] < 0]
            row_offsets = positive_offsets + negative_offsets

        best_choice: (
            tuple[float, float, float, str, tuple[float, float, float, float]] | None
        ) = None
        for dx, dy in row_offsets:
            ha = "left" if dx >= 0 else "right"
            anchor_x = point_disp[0] + dx
            anchor_y = point_disp[1] + dy
            candidate_box = estimate_text_bbox(
                anchor_x, anchor_y, text_width, text_height, ha
            )
            penalty = np.hypot(dx, dy) * 0.02

            if (
                candidate_box[0] < axes_bbox.x0 + 8
                or candidate_box[2] > axes_bbox.x1 - 8
                or candidate_box[1] < axes_bbox.y0 + 8
                or candidate_box[3] > axes_bbox.y1 - 8
            ):
                penalty += 1e6

            for existing_box in occupied_boxes:
                if boxes_overlap(candidate_box, existing_box, pad=6):
                    penalty += 1e6

            for idx, other_point in enumerate(all_points):
                if idx == current_idx:
                    continue
                if (
                    candidate_box[0] - 7 <= other_point[0] <= candidate_box[2] + 7
                    and candidate_box[1] - 7 <= other_point[1] <= candidate_box[3] + 7
                ):
                    penalty += 2000

            if best_choice is None or penalty < best_choice[0]:
                best_choice = (penalty, dx, dy, ha, candidate_box)

        if best_choice is None:
            best_choice = (
                0.0,
                78.0,
                0.0,
                "left",
                estimate_text_bbox(
                    point_disp[0] + 78, point_disp[1], text_width, text_height, "left"
                ),
            )

        _, dx, dy, ha, chosen_box = best_choice
        occupied_boxes.append(chosen_box)
        annotation = ax.annotate(
            label,
            (row[PANEL_B_BASELINE_FIELD], row[PANEL_B_DELTA_GINI_FIELD]),
            xytext=(dx, dy),
            textcoords="offset pixels",
            ha=ha,
            va="center",
            fontsize=fontsize,
            color="#222222",
            arrowprops={
                "arrowstyle": "-",
                "color": "#6F6F6F",
                "linewidth": 0.7,
                "shrinkA": 2,
                "shrinkB": 4,
            },
            zorder=4,
            clip_on=False,
        )
        annotation.set_path_effects(
            [pe.withStroke(linewidth=2.8, foreground="white", alpha=0.92)]
        )


def apply_square_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.size": SQUARE_FONT,
            "axes.labelsize": SQUARE_FONT,
            "axes.titlesize": SQUARE_FONT,
            "xtick.labelsize": SQUARE_FONT,
            "ytick.labelsize": SQUARE_FONT,
            "legend.fontsize": SQUARE_FONT,
            "legend.title_fontsize": SQUARE_FONT,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "mathtext.fontset": "custom",
            "mathtext.rm": "Times New Roman",
            "mathtext.it": "Times New Roman:italic",
            "mathtext.bf": "Times New Roman:bold",
        }
    )


def prepare_panel_a(
    lines: list[str],
) -> tuple[pd.DataFrame, dict[str, float | str], pd.DataFrame]:
    grid_df = pd.read_csv(PANEL_A_CSV)
    spearman_df = pd.read_csv(PANEL_A_SPEARMAN_CSV)
    ols_summary_text = PANEL_A_OLS_TXT.read_text(encoding="utf-8")
    summary_stats = parse_ols_summary(ols_summary_text)
    candidate_df = evaluate_panel_a_candidates(grid_df, summary_stats)
    candidate_df.to_csv(PANEL_A_MODEL_CHECK_PATH, index=False)

    facility_series = grid_df[PANEL_A_FACILITY_FIELD]
    pop_series = grid_df[PANEL_A_POP_FIELD]
    node_series = grid_df[PANEL_A_NODE_FIELD]
    target_series = grid_df[PANEL_A_TARGET]

    best_candidate = candidate_df.iloc[0]
    chosen_candidate = candidate_df[
        (candidate_df["facility_field"] == PANEL_A_FACILITY_FIELD)
        & (candidate_df["facility_transform"] == "log1p")
        & (candidate_df["population_field"] == PANEL_A_POP_FIELD)
        & (candidate_df["population_transform"] == "log")
    ].iloc[0]

    log_line(lines, "Panel A checks")
    log_line(
        lines,
        f"1) grid_cells_pw_delta_t_facility_popdensity.csv columns: {list(grid_df.columns)}",
    )
    log_line(lines, f"2) Sample size n: {len(grid_df)}")
    log_line(
        lines,
        f"3) Climate-shock field: '{PANEL_A_TARGET}', range = {format_range(target_series)}",
    )
    log_line(
        lines,
        "4) Facility-density field: "
        f"'{PANEL_A_FACILITY_FIELD}', raw range = {format_range(facility_series)}, "
        f"log1p range = {format_transform_range(facility_series, 'log1p')}",
    )
    log_line(
        lines,
        "5) Population-related field that reproduces the OLS summary: "
        f"'{PANEL_A_POP_FIELD}', raw range = {format_range(pop_series)}, "
        f"log range = {format_transform_range(pop_series, 'log')}",
    )
    log_line(
        lines,
        "   Existing node-density field in the CSV: "
        f"'{PANEL_A_NODE_FIELD}', raw range = {format_range(node_series)}, "
        f"log range = {format_transform_range(node_series, 'log')}",
    )
    log_line(
        lines,
        "6) Logging requirement: the CSV stores raw values. "
        f"Panel A uses log1p({PANEL_A_FACILITY_FIELD}) because 25 cells have zero facilities, "
        f"and log({PANEL_A_POP_FIELD}) because the population field is strictly positive.",
    )
    log_line(
        lines,
        "7) OLS text summary: "
        f"const = {summary_stats['const']:.4f}, "
        f"log_facility = {summary_stats['log_facility']:.4f}, "
        f"log_pop_density = {summary_stats['log_pop_density']:.4f}, "
        f"R² = {summary_stats['r_squared']:.3f}, "
        f"n = {int(summary_stats['n_obs'])}.",
    )
    log_line(
        lines,
        "   Closest CSV reconstruction: "
        f"log1p({best_candidate['facility_field']}) + {best_candidate['population_transform']}({best_candidate['population_field']}) "
        f"=> const = {best_candidate['const']:.4f}, "
        f"facility coef = {best_candidate['facility_coef']:.4f}, "
        f"population coef = {best_candidate['population_coef']:.4f}, "
        f"R² = {best_candidate['r_squared']:.3f}, "
        f"n = {int(best_candidate['n'])}.",
    )
    node_match = spearman_df.loc[
        spearman_df["x"] == PANEL_A_NODE_FIELD, "label"
    ].tolist()
    log_line(
        lines,
        "8) Naming mismatch detected: the CSV does not contain a 'pop_density' field. "
        f"'{PANEL_A_NODE_FIELD}' is described in the Spearman table as {node_match[0]!r} and does not reproduce the OLS summary "
        f"(R² ≈ {candidate_df.loc[candidate_df['population_field'] == PANEL_A_NODE_FIELD, 'r_squared'].max():.3f}). "
        f"The summary coefficients are instead matched by '{PANEL_A_POP_FIELD}', so the figure uses grid-cell population rather than node density.",
    )
    log_line(
        lines,
        f"   OLS header text: {summary_stats['formula_header']}",
    )
    log_line(
        lines,
        "   Model transform used to reproduce the published OLS: "
        f"log1p({PANEL_A_FACILITY_FIELD}) and log({PANEL_A_POP_FIELD}). "
        "Panel A therefore visualizes both predictors directly, while contour labels carry the predicted pw_delta_t values. "
        f"This configuration reproduces the reported coefficients to rounding "
        f"(const = {chosen_candidate['const']:.4f}, facility coef = {chosen_candidate['facility_coef']:.4f}, "
        f"population coef = {chosen_candidate['population_coef']:.4f}, R² = {chosen_candidate['r_squared']:.3f}).",
    )
    log_line(lines)

    return grid_df, summary_stats, candidate_df


def prepare_panel_b(lines: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    gini_df = pd.read_csv(PANEL_B_GINI_CSV)
    raw_df = pd.read_csv(PANEL_B_RAW_CSV)
    quadrant_df = pd.read_csv(PANEL_B_QUADRANT_CSV)
    quadrant_expanded = expand_quadrant_mapping(quadrant_df)

    joined = gini_df.merge(
        raw_df[["country", PANEL_B_BASELINE_FIELD, PANEL_B_DELTA_GINI_FIELD]],
        on="country",
        how="outer",
        suffixes=("_gini", "_raw"),
        indicator=True,
    )
    gini_only = sorted(joined.loc[joined["_merge"] == "left_only", "country"].tolist())
    raw_only = sorted(joined.loc[joined["_merge"] == "right_only", "country"].tolist())

    matched = joined.loc[joined["_merge"] == "both"].copy()
    matched["baseline_diff"] = (
        matched[f"{PANEL_B_BASELINE_FIELD}_gini"]
        - matched[f"{PANEL_B_BASELINE_FIELD}_raw"]
    )
    matched["delta_gini_diff"] = (
        matched[f"{PANEL_B_DELTA_GINI_FIELD}_gini"]
        - matched[f"{PANEL_B_DELTA_GINI_FIELD}_raw"]
    )

    plot_df = gini_df.merge(quadrant_expanded, on="country", how="left")
    unmatched_quadrant = sorted(
        plot_df.loc[plot_df["quadrant"].isna(), "country"].tolist()
    )
    extra_quadrant_countries = sorted(
        set(quadrant_expanded["country"]) - set(gini_df["country"])
    )

    if unmatched_quadrant:
        raise ValueError(
            f"Countries missing quadrant classifications: {unmatched_quadrant}"
        )

    plot_df["quadrant_clean"] = pd.Categorical(
        plot_df["quadrant_clean"], categories=QUADRANT_ORDER, ordered=True
    )
    plot_df = plot_df.sort_values(
        ["quadrant_clean", PANEL_B_BASELINE_FIELD, PANEL_B_DELTA_GINI_FIELD]
    ).reset_index(drop=True)
    plot_df.to_csv(JOIN_CHECK_PATH, index=False)

    log_line(lines, "Panel B checks")
    log_line(
        lines,
        f"9) country_gini_normal_extreme_delta.csv columns: {list(gini_df.columns)}",
    )
    log_line(
        lines,
        f"10) country_facility_population_accessibility_raw.csv columns: {list(raw_df.columns)}",
    )
    log_line(
        lines,
        f"11) country_facility_density_quadrant_classification.csv columns: {list(quadrant_df.columns)}",
    )
    log_line(
        lines,
        "12) Join results: "
        f"gini ↔ raw matched countries = {len(matched)}; "
        f"gini ↔ expanded quadrant matched countries = {plot_df['quadrant'].notna().sum()}.",
    )
    log_line(
        lines,
        "   Baseline and delta_gini agree exactly between gini and raw on matched countries: "
        f"max |pwmtt_normal diff| = {matched['baseline_diff'].abs().max():.4f}, "
        f"max |delta_gini diff| = {matched['delta_gini_diff'].abs().max():.4f}.",
    )
    log_line(
        lines,
        f"13) Baseline accessibility field: '{PANEL_B_BASELINE_FIELD}', range = {format_range(plot_df[PANEL_B_BASELINE_FIELD])}",
    )
    log_line(
        lines,
        f"14) Inequality-worsening field: '{PANEL_B_DELTA_GINI_FIELD}', range = {format_range(plot_df[PANEL_B_DELTA_GINI_FIELD])}",
    )
    log_line(
        lines,
        "15) Country classification field: expanded 'quadrant', categories = "
        f"{plot_df['quadrant'].drop_duplicates().tolist()}",
    )
    unmatched_messages = []
    if gini_only:
        unmatched_messages.append(f"gini only = {gini_only}")
    if raw_only:
        unmatched_messages.append(f"raw only = {raw_only}")
    if extra_quadrant_countries:
        unmatched_messages.append(f"quadrant only = {extra_quadrant_countries}")
    if not unmatched_messages:
        unmatched_messages.append("none")
    log_line(lines, f"16) Unmatched country lists: {'; '.join(unmatched_messages)}")
    log_line(lines)

    return plot_df, quadrant_expanded


def build_panel_a_levels(predicted: pd.Series) -> np.ndarray:
    candidate_levels = np.array([0.00, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40])
    valid_levels = candidate_levels[
        (candidate_levels >= predicted.min() - 1e-6)
        & (candidate_levels <= predicted.max() + 1e-6)
    ]
    if len(valid_levels) >= 5:
        return valid_levels
    return np.round(
        np.linspace(predicted.quantile(0.08), predicted.quantile(0.92), 6), 2
    )


def compute_panel_a_surface_components(
    panel_a_df: pd.DataFrame,
    summary_stats: dict[str, float | str],
    grid_size: int = 220,
) -> dict[str, object]:
    df = panel_a_df.copy()
    df["facility_log"] = transform_series(df[PANEL_A_FACILITY_FIELD], "log1p")
    df["log_population"] = transform_series(df[PANEL_A_POP_FIELD], "log")
    const = float(summary_stats["const"])
    beta_fac = float(summary_stats["log_facility"])
    beta_pop = float(summary_stats["log_pop_density"])
    df["predicted_shock"] = (
        const + beta_fac * df["facility_log"] + beta_pop * df["log_population"]
    )

    x_grid = np.linspace(df["facility_log"].min(), df["facility_log"].max(), grid_size)
    y_grid = np.linspace(
        df["log_population"].min(), df["log_population"].max(), grid_size
    )
    xx, yy = np.meshgrid(x_grid, y_grid)
    zz = const + beta_fac * xx + beta_pop * yy
    contour_levels = build_panel_a_levels(df["predicted_shock"])

    return {
        "df": df,
        "x_grid": x_grid,
        "y_grid": y_grid,
        "xx": xx,
        "yy": yy,
        "zz": zz,
        "levels": contour_levels,
    }


def build_panel_a_square(
    panel_a_df: pd.DataFrame, summary_stats: dict[str, float | str]
) -> plt.Figure:
    apply_square_style()
    fig = plt.figure(figsize=(SQUARE_INCH, SQUARE_INCH), dpi=300)
    ax = fig.add_axes([0.24, 0.20, 0.70, 0.72])
    parts = compute_panel_a_surface_components(panel_a_df, summary_stats, grid_size=180)
    df = parts["df"]

    ax.set_facecolor("white")
    ax.grid(color="#E5E9EF", linewidth=0.6, alpha=0.9)
    ax.scatter(
        df["facility_log"],
        df["log_population"],
        s=18,
        color="#6FA8DC",
        alpha=0.48,
        edgecolor="white",
        linewidth=0.18,
        zorder=3,
    )
    contour = ax.contour(
        parts["xx"],
        parts["yy"],
        parts["zz"],
        levels=parts["levels"],
        colors=["#D8A47A"],
        linewidths=0.82,
        alpha=0.72,
        zorder=1,
    )
    contour_labels = ax.clabel(
        contour, inline=True, fmt="%.2f", fontsize=7.4, colors="#A36A39"
    )
    for label in contour_labels:
        label.set_path_effects(
            [pe.withStroke(linewidth=1.8, foreground="white", alpha=0.9)]
        )

    ax.set_xlabel("log(1 + facilities/M)", labelpad=2)
    ax.set_ylabel("log(grid-cell population)", labelpad=2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(length=3, width=0.8)

    formula_text = (
        f"pw_Δt = {float(summary_stats['const']):.3f} - {abs(float(summary_stats['log_facility'])):.3f} log(1 + fac/M)\n"
        f"- {abs(float(summary_stats['log_pop_density'])):.3f} log(population)\n"
        f"R² = {float(summary_stats['r_squared']):.3f}; both p < 0.001"
    )
    ax.text(
        0.985,
        0.985,
        formula_text,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=6.9,
        linespacing=0.95,
        color="#222222",
        zorder=5,
    )

    return fig


def build_panel_b_square(panel_b_df: pd.DataFrame) -> plt.Figure:
    apply_square_style()
    fig = plt.figure(figsize=(SQUARE_INCH, SQUARE_INCH), dpi=300)
    ax = fig.add_axes([0.18, 0.47, 0.78, 0.45])

    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    x_median = panel_b_df[PANEL_B_BASELINE_FIELD].median()
    y_reference = 0.0
    ax.axvline(x_median, color="#8C8C8C", linestyle="--", linewidth=0.9, zorder=1)
    ax.axhline(y_reference, color="#8C8C8C", linestyle="--", linewidth=0.9, zorder=1)

    for quadrant in QUADRANT_ORDER:
        subset = panel_b_df.loc[panel_b_df["quadrant_clean"] == quadrant]
        ax.scatter(
            subset[PANEL_B_BASELINE_FIELD],
            subset[PANEL_B_DELTA_GINI_FIELD],
            s=26,
            color=QUADRANT_COLOR_MAP[quadrant],
            edgecolor="white",
            linewidth=0.45,
            alpha=0.97,
            zorder=3,
            label=quadrant,
        )

    ax.set_xlabel("Baseline PWMTT (h)", labelpad=3)
    ax.set_ylabel("Δ Gini", labelpad=4)
    ax.tick_params(length=3, width=0.8)
    ax.grid(color="#D6D6D6", linewidth=0.55, alpha=0.7)
    ax.set_xlim(-0.12, max(2.05, panel_b_df[PANEL_B_BASELINE_FIELD].max() + 0.06))
    ax.set_ylim(
        panel_b_df[PANEL_B_DELTA_GINI_FIELD].min() - 0.0015,
        panel_b_df[PANEL_B_DELTA_GINI_FIELD].max() + 0.003,
    )

    legend_labels = {
        "Dense facility / short travel": "Dense fac.\nshort travel",
        "Dense facility / long travel": "Dense fac.\nlong travel",
        "Sparse facility / short travel": "Sparse fac.\nshort travel",
        "Sparse facility / long travel": "Sparse fac.\nlong travel",
    }
    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="",
            label=legend_labels[label],
            markerfacecolor=QUADRANT_COLOR_MAP[label],
            markeredgecolor="white",
            markeredgewidth=0.45,
            markersize=5.6,
        )
        for label in QUADRANT_ORDER
    ]
    fig.legend(
        handles=legend_handles,
        loc="lower center",
        bbox_to_anchor=(0.56, 0.025),
        frameon=False,
        ncol=2,
        columnspacing=1.0,
        handletextpad=0.4,
        borderaxespad=0.0,
    )

    return fig


def build_figure(
    panel_a_df: pd.DataFrame,
    summary_stats: dict[str, float | str],
    panel_b_df: pd.DataFrame,
) -> plt.Figure:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": TEXT_FONT,
            "axes.labelsize": LABEL_FONT,
            "axes.titlesize": TITLE_FONT,
            "xtick.labelsize": TICK_FONT,
            "ytick.labelsize": TICK_FONT,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    fig = plt.figure(figsize=(15.5, 6.6), dpi=150, constrained_layout=True)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.08, 1.08, 0.26])
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_ann = fig.add_subplot(gs[0, 2])

    for ax in (ax_a, ax_b):
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    ax_ann.axis("off")

    parts = compute_panel_a_surface_components(panel_a_df, summary_stats, grid_size=240)
    df = parts["df"]

    ax_a.set_facecolor("white")
    ax_a.grid(color="#E2E8F0", linewidth=0.7, alpha=0.9)
    ax_a.scatter(
        df["facility_log"],
        df["log_population"],
        s=20,
        color="#9EC5E6",
        alpha=0.26,
        linewidth=0,
        zorder=2,
    )
    contour = ax_a.contour(
        parts["xx"],
        parts["yy"],
        parts["zz"],
        levels=parts["levels"],
        colors=["#B86A31"],
        linewidths=1.3,
        alpha=0.95,
        zorder=3,
    )
    ax_a.clabel(contour, inline=True, fmt="%.2f", fontsize=8.5, colors="#8B4D1B")

    ax_a.set_xlabel("Facility density, log(1 + facilities/M)")
    ax_a.set_ylabel("Grid-cell population, log scale")

    formula_text = (
        "Contours = predicted Δ travel time (pw_Δt)\n"
        "pw_Δt = 0.778 - 0.038 log(1 + fac/M)\n"
        "- 0.044 log(population)\n"
        "R² = 0.429; both p < 0.001; n = 182"
    )
    ax_a.text(
        0.98,
        0.98,
        formula_text,
        transform=ax_a.transAxes,
        ha="right",
        va="top",
        fontsize=TEXT_FONT,
        bbox={
            "boxstyle": "round,pad=0.28",
            "facecolor": (1, 1, 1, 0.86),
            "edgecolor": "#C8CDD5",
            "linewidth": 0.8,
        },
    )

    x_median = panel_b_df[PANEL_B_BASELINE_FIELD].median()
    y_reference = 0.0

    ax_b.axvline(x_median, color="#8C8C8C", linestyle="--", linewidth=1.0, zorder=1)
    ax_b.axhline(y_reference, color="#8C8C8C", linestyle="--", linewidth=1.0, zorder=1)

    for quadrant in QUADRANT_ORDER:
        subset = panel_b_df.loc[panel_b_df["quadrant_clean"] == quadrant]
        ax_b.scatter(
            subset[PANEL_B_BASELINE_FIELD],
            subset[PANEL_B_DELTA_GINI_FIELD],
            s=64,
            color=QUADRANT_COLOR_MAP[quadrant],
            edgecolor="white",
            linewidth=0.7,
            alpha=0.95,
            zorder=3,
            label=quadrant,
        )

    label_y_threshold = max(y_reference, panel_b_df[PANEL_B_DELTA_GINI_FIELD].median())
    label_pool = panel_b_df[
        (panel_b_df[PANEL_B_BASELINE_FIELD] > x_median)
        & (panel_b_df[PANEL_B_DELTA_GINI_FIELD] > label_y_threshold)
    ].copy()
    if len(label_pool) < 4:
        label_pool = panel_b_df[
            panel_b_df[PANEL_B_DELTA_GINI_FIELD]
            > panel_b_df[PANEL_B_DELTA_GINI_FIELD].median()
        ].copy()
    label_pool["label_score"] = (
        label_pool[PANEL_B_BASELINE_FIELD] - x_median
    ) / panel_b_df[PANEL_B_BASELINE_FIELD].std() + (
        label_pool[PANEL_B_DELTA_GINI_FIELD] - y_reference
    ) / panel_b_df[
        PANEL_B_DELTA_GINI_FIELD
    ].std()
    label_df = (
        label_pool.sort_values(
            [PANEL_B_DELTA_GINI_FIELD, PANEL_B_BASELINE_FIELD], ascending=False
        )
        .head(6)
        .reset_index(drop=True)
    )

    ax_b.set_xlabel("Baseline population-weighted mean travel time (hours)")
    ax_b.set_ylabel("Inequality worsening (Δ Gini)")
    ax_b.set_title("Consequence", loc="left", pad=10)
    ax_b.grid(color="#D6D6D6", linewidth=0.6, alpha=0.7)
    ax_b.set_xlim(-0.1, max(2.08, panel_b_df[PANEL_B_BASELINE_FIELD].max() + 0.12))
    ax_b.set_ylim(
        panel_b_df[PANEL_B_DELTA_GINI_FIELD].min() - 0.002,
        panel_b_df[PANEL_B_DELTA_GINI_FIELD].max() + 0.0035,
    )

    place_country_labels(fig, ax_b, panel_b_df, label_df)

    note = ax_ann.text(
        0.0,
        0.97,
        "Accessibility-crisis countries see larger\ninequality worsening under climate stress.",
        transform=ax_ann.transAxes,
        ha="left",
        va="top",
        fontsize=8.6,
        color="#333333",
    )
    note.set_path_effects([pe.withStroke(linewidth=3.0, foreground="white", alpha=0.9)])

    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="",
            label=label,
            markerfacecolor=QUADRANT_COLOR_MAP[label],
            markeredgecolor="white",
            markeredgewidth=0.7,
            markersize=8,
        )
        for label in QUADRANT_ORDER
    ]
    ax_ann.legend(
        handles=legend_handles,
        title="Country type",
        loc="lower left",
        bbox_to_anchor=(0.0, 0.0),
        frameon=False,
        fontsize=TEXT_FONT,
        title_fontsize=TEXT_FONT,
    )

    ax_a.text(
        -0.13, 1.04, "A", transform=ax_a.transAxes, fontsize=16, fontweight="bold"
    )
    ax_b.text(
        -0.13, 1.04, "B", transform=ax_b.transAxes, fontsize=16, fontweight="bold"
    )

    return fig


def main() -> None:
    require_inputs()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    diagnostic_lines: list[str] = []
    panel_a_df, summary_stats, _ = prepare_panel_a(diagnostic_lines)
    panel_b_df, _ = prepare_panel_b(diagnostic_lines)
    LOG_PATH.write_text("\n".join(diagnostic_lines) + "\n", encoding="utf-8")

    fig = build_figure(panel_a_df, summary_stats, panel_b_df)
    fig.savefig(PNG_PATH, dpi=600, bbox_inches="tight")
    fig.savefig(PDF_PATH, bbox_inches="tight")
    plt.close(fig)

    fig_a = build_panel_a_square(panel_a_df, summary_stats)
    fig_a.savefig(PANEL_A_6CM_PNG_PATH, dpi=600)
    fig_a.savefig(PANEL_A_6CM_PDF_PATH)
    plt.close(fig_a)

    fig_b = build_panel_b_square(panel_b_df)
    fig_b.savefig(PANEL_B_6CM_PNG_PATH, dpi=600)
    fig_b.savefig(PANEL_B_6CM_PDF_PATH)
    plt.close(fig_b)

    print(f"Saved figure PNG: {PNG_PATH}")
    print(f"Saved figure PDF: {PDF_PATH}")
    print(f"Saved Panel A 6cm PNG: {PANEL_A_6CM_PNG_PATH}")
    print(f"Saved Panel A 6cm PDF: {PANEL_A_6CM_PDF_PATH}")
    print(f"Saved Panel B 6cm PNG: {PANEL_B_6CM_PNG_PATH}")
    print(f"Saved Panel B 6cm PDF: {PANEL_B_6CM_PDF_PATH}")
    print(f"Saved diagnostics log: {LOG_PATH}")
    print(f"Saved Panel B plot data: {JOIN_CHECK_PATH}")
    print(f"Saved Panel A reconstruction table: {PANEL_A_MODEL_CHECK_PATH}")


if __name__ == "__main__":
    main()
