#!/usr/bin/env python3
"""Audit archived, pre-revision TGR sources without changing scientific inputs.

This is diagnostic only: corrected terrain, road topology and healthcare routing
will require a separate formal C07 run. Reads ZIP members in place to avoid
extracting multi-country archives to scarce local disk.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SUMMARY_MEMBER = "result/result2/country_accessibility_summary.csv"
FIGURE_MEMBER = (
    "result/result2/finding1_2_country_tail_gap_p50_p90_ranking/"
    "country_p50_p90_delta_travel_time_and_tail_gap.csv"
)
ROBUSTNESS_MEMBER = (
    "robustness_outputs/08_health_variant_grid/health_variant_grid_summary.csv"
)
UNREACHABLE_H = 1e6


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_member(archive: zipfile.ZipFile, member: str) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(archive.read(member)))


def weighted_step_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Reproduce compute_health_accessibility.py's first-crossing quantile."""
    if len(values) == 0 or not np.isfinite(weights.sum()) or weights.sum() <= 0:
        return float("nan")
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    fractions = np.cumsum(weights[order]) / weights.sum()
    pos = min(int(np.searchsorted(fractions, q)), len(sorted_values) - 1)
    return float(sorted_values[pos])


def baseline_group_means(
    t0: np.ndarray, delta: np.ndarray, weights: np.ndarray
) -> tuple[float, float, int, int]:
    """Mirror legacy buffering script's P40–P60 and >P80 baseline groups."""
    order = np.argsort(t0, kind="stable")
    fraction = np.cumsum(weights[order]) / weights.sum()
    mid = (fraction >= 0.40) & (fraction <= 0.60)
    upper = fraction > 0.80

    def mean(mask: np.ndarray) -> float:
        ww = weights[order][mask]
        return float(np.average(delta[order][mask], weights=ww)) if len(ww) and ww.sum() > 0 else float("nan")

    return mean(mid), mean(upper), int(mid.sum()), int(upper.sum())


def audit_node_table(frame: pd.DataFrame) -> dict[str, float | int]:
    t0 = pd.to_numeric(frame["t_normal"], errors="coerce").to_numpy(float)
    t1 = pd.to_numeric(frame["t_extreme"], errors="coerce").to_numpy(float)
    pop = pd.to_numeric(frame["population"], errors="coerce").to_numpy(float)
    mask = (
        np.isfinite(t0)
        & np.isfinite(t1)
        & np.isfinite(pop)
        & (t0 < UNREACHABLE_H)
        & (t1 < UNREACHABLE_H)
        & (pop > 0)
    )
    t0, t1, pop = t0[mask], t1[mask], pop[mask]
    delta = t1 - t0
    p50 = weighted_step_quantile(delta, pop, 0.50)
    p90 = weighted_step_quantile(delta, pop, 0.90)
    mid, upper, n_mid, n_upper = baseline_group_means(t0, delta, pop) if len(pop) else (np.nan, np.nan, 0, 0)
    return {
        "n_nodes_all": len(frame),
        "n_nodes_valid": int(mask.sum()),
        "population_valid": float(pop.sum()),
        "p50_delta_weighted_h": p50,
        "p90_delta_weighted_h": p90,
        "tail_ratio_delta_weighted": p90 / p50 if p50 > 0 else np.nan,
        "baseline_mid_group_mean_delta_h": mid,
        "baseline_upper_group_mean_delta_h": upper,
        "baseline_upper_over_mid_delta_mean": upper / mid if mid > 0 else np.nan,
        "n_baseline_mid_nodes": n_mid,
        "n_baseline_upper_nodes": n_upper,
    }


def run_audit(health_zip: Path, result_zip: Path, robustness_zip: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(health_zip) as health, zipfile.ZipFile(result_zip) as result:
        summary = read_member(result, SUMMARY_MEMBER)
        figure = read_member(result, FIGURE_MEMBER)
        node_rows = []
        for country in sorted(set(figure["country"])):
            member = f"health_accessibility/node_accessibility_{country}.csv"
            node_rows.append({"country": country, **audit_node_table(read_member(health, member))})

    nodes = pd.DataFrame(node_rows)
    data = figure.merge(summary, on="country", suffixes=("_figure", "_summary"), validate="one_to_one")
    data = data.merge(nodes, on="country", validate="one_to_one")
    # The plotting file uses a renamed/imputed ratio; compare its raw delta quantiles.
    data["figure_vs_summary_p50_match"] = np.isclose(
        data["p50_delta_h_figure"], data["p50_delta_h_summary"], rtol=0, atol=1e-10
    )
    data["figure_vs_summary_p90_match"] = np.isclose(
        data["p90_delta_h_figure"], data["p90_delta_h_summary"], rtol=0, atol=1e-10
    )
    data["node_vs_summary_p50_match"] = np.isclose(
        data["p50_delta_weighted_h"], data["p50_delta_h_summary"], rtol=0, atol=1e-10
    )
    data["node_vs_summary_p90_match"] = np.isclose(
        data["p90_delta_weighted_h"], data["p90_delta_h_summary"], rtol=0, atol=1e-10
    )
    keep = [
        "country", "n_nodes_all", "n_nodes_valid", "population_valid",
        "p50_delta_h_figure", "p90_delta_h_figure", "tail_gap_ratio_plot",
        "p50_delta_h_summary", "p90_delta_h_summary", "tail_gap_ratio",
        "p50_delta_weighted_h", "p90_delta_weighted_h", "tail_ratio_delta_weighted",
        "baseline_mid_group_mean_delta_h", "baseline_upper_group_mean_delta_h",
        "baseline_upper_over_mid_delta_mean", "n_baseline_mid_nodes",
        "n_baseline_upper_nodes", "figure_vs_summary_p50_match",
        "figure_vs_summary_p90_match", "node_vs_summary_p50_match",
        "node_vs_summary_p90_match",
    ]
    out_csv = output_dir / "legacy_tgr_country_diagnostic.csv"
    data[keep].to_csv(out_csv, index=False)

    with zipfile.ZipFile(robustness_zip) as robustness:
        variants = read_member(robustness, ROBUSTNESS_MEMBER)
    summary49 = summary[summary["country"] != "WestSahara"]
    aggregates = {
        "scope": "diagnostic_archived_results_not_formal_revision",
        "inputs_sha256": {
            "health_accessibility_zip": sha256_file(health_zip),
            "result_zip": sha256_file(result_zip),
            "robustness_outputs_zip": sha256_file(robustness_zip),
        },
        "summary_countries": int(len(summary)),
        "summary_49_countries": int(len(summary49)),
        "summary_49_nonmissing_tgr": int(summary49["tail_gap_ratio"].notna().sum()),
        "summary_49_mean_tgr_skip_missing": float(summary49["tail_gap_ratio"].mean()),
        "summary_50_mean_tgr_skip_missing": float(summary["tail_gap_ratio"].mean()),
        "figure_49_mean_tgr": float(figure["tail_gap_ratio_plot"].mean()),
        "figure_49_median_tgr": float(figure["tail_gap_ratio_plot"].median()),
        "figure_49_tgr_gt_1": int((figure["tail_gap_ratio_plot"] > 1).sum()),
        "figure_49_p90_delta_gt_p50_delta": int(
            (figure["p90_delta_h"] > figure["p50_delta_h"]).sum()
        ),
        "figure_summary_both_delta_quantiles_match_count": int(
            (data["figure_vs_summary_p50_match"] & data["figure_vs_summary_p90_match"]).sum()
        ),
        "node_summary_both_delta_quantiles_match_count": int(
            (data["node_vs_summary_p50_match"] & data["node_vs_summary_p90_match"]).sum()
        ),
        "robustness_rows": int(len(variants)),
        "robustness_mean_tgr_min": float(variants["mean_tail_gap_ratio"].min()),
        "robustness_mean_tgr_max": float(variants["mean_tail_gap_ratio"].max()),
        "output_country_csv_sha256": sha256_file(out_csv),
    }
    (output_dir / "legacy_tgr_aggregate_diagnostic.json").write_text(
        json.dumps(aggregates, indent=2, ensure_ascii=False) + "\n"
    )
    return aggregates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health-zip", type=Path, required=True)
    parser.add_argument("--result-zip", type=Path, required=True)
    parser.add_argument("--robustness-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_audit(args.health_zip, args.result_zip, args.robustness_zip, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
