"""RCP8.5 bottleneck and intervention-priority stability checks.

This is a robustness-only wrapper around the bottleneck stability logic.
It keeps the expensive full network rebuilding out of scope, reads existing
future road-speed CSVs, and writes compact tables under sensitivity.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

from sensitivity.config import TOPK_SHARES, add_common_path_args, resolve_paths
from sensitivity.io_utils import ensure_dir, write_table

MATCH_TOLERANCE_DEG = 0.02
CV_MIN_THRESHOLD = 0.02


def _finite(values: np.ndarray, fill: float = 0.0) -> np.ndarray:
    out = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    out[~np.isfinite(out)] = fill
    return out


def _norm_positive(values: np.ndarray, threshold: float = 0.0) -> np.ndarray:
    values = _finite(values)
    pos = values[values > threshold]
    if len(pos) == 0:
        return np.zeros_like(values, dtype=float)
    return np.clip(values / float(pos.max()), 0.0, 1.0)


def bottleneck_score(ni: np.ndarray, cv: np.ndarray) -> np.ndarray:
    return _norm_positive(ni) * _norm_positive(cv, CV_MIN_THRESHOLD)


def top_indices(values: np.ndarray, k: int) -> np.ndarray:
    values = np.asarray(values)
    if k <= 0:
        return np.array([], dtype=np.int64)
    k = min(int(k), len(values))
    idx = np.argpartition(values, -k)[-k:]
    return idx[np.argsort(values[idx])[::-1]]


def jaccard(a: np.ndarray, b: np.ndarray) -> float:
    sa = set(np.asarray(a, dtype=np.int64).tolist())
    sb = set(np.asarray(b, dtype=np.int64).tolist())
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def load_baseline(edge_scores_csv: Path) -> pd.DataFrame:
    usecols = ["u", "v", "mid_lon", "mid_lat", "NI", "CV"]
    df = pd.read_csv(edge_scores_csv, usecols=usecols)
    for col in ["mid_lon", "mid_lat", "NI", "CV"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["mid_lon", "mid_lat"]).reset_index(drop=True)
    df["NI"] = df["NI"].fillna(0.0).clip(lower=0.0)
    df["CV"] = df["CV"].fillna(0.0).clip(lower=0.0)
    return df


def load_future_arrays(future_dir: Path) -> tuple[dict[str, np.ndarray], list[str]]:
    files = sorted(future_dir.glob("*_road_speed.csv"))
    if not files:
        raise FileNotFoundError(f"No *_road_speed.csv files in {future_dir}")

    arrays: dict[str, list[np.ndarray]] = {
        "center_lon": [],
        "center_lat": [],
        "V_normal": [],
        "V_extreme": [],
        "p_block": [],
        "country_code": [],
    }
    countries: list[str] = []
    usecols = ["center_lon", "center_lat", "V_normal", "V_extreme", "p_block"]
    dtype = {
        "center_lon": "float32",
        "center_lat": "float32",
        "V_normal": "float32",
        "V_extreme": "float32",
        "p_block": "float32",
    }

    for code, csv_path in enumerate(files):
        country = csv_path.name.replace("_road_speed.csv", "")
        countries.append(country)
        df = pd.read_csv(csv_path, usecols=usecols, dtype=dtype)
        df = df.replace([np.inf, -np.inf], np.nan).dropna()
        if df.empty:
            continue
        arrays["center_lon"].append(df["center_lon"].to_numpy(dtype=np.float64))
        arrays["center_lat"].append(df["center_lat"].to_numpy(dtype=np.float64))
        arrays["V_normal"].append(df["V_normal"].clip(lower=0.5).to_numpy(dtype=float))
        arrays["V_extreme"].append(
            df["V_extreme"].clip(lower=0.5).to_numpy(dtype=float)
        )
        arrays["p_block"].append(df["p_block"].clip(0.0, 0.99).to_numpy(dtype=float))
        arrays["country_code"].append(np.full(len(df), code, dtype=np.int16))

    out = {key: np.concatenate(parts) for key, parts in arrays.items() if parts}
    if not out:
        raise ValueError(f"No readable future road-speed rows in {future_dir}")
    return out, countries


def spatial_match(
    edges: pd.DataFrame, roads: dict[str, np.ndarray]
) -> tuple[np.ndarray, np.ndarray]:
    road_xy = np.column_stack([roads["center_lon"], roads["center_lat"]])
    edge_xy = edges[["mid_lon", "mid_lat"]].to_numpy(dtype=float)
    tree = cKDTree(road_xy)
    dists, idxs = tree.query(edge_xy, workers=-1)
    matched = dists <= MATCH_TOLERANCE_DEG
    idxs = idxs.astype(np.int64)
    idxs[~matched] = -1
    return idxs, matched


def compute_future_cv(
    baseline_cv: np.ndarray,
    roads: dict[str, np.ndarray],
    match_idx: np.ndarray,
) -> np.ndarray:
    cv_future = baseline_cv.copy()
    matched = match_idx >= 0
    road_idx = match_idx[matched]
    effective_speed = roads["V_extreme"][road_idx] * (1.0 - roads["p_block"][road_idx])
    vals = roads["V_normal"][road_idx] / np.clip(effective_speed, 0.5, None) - 1.0
    cv_future[matched] = np.clip(vals, 0.0, None)
    return cv_future


def strategic_mask(ni: np.ndarray, cv: np.ndarray) -> np.ndarray:
    ni_pos = ni[ni > 0]
    cv_pos = cv[cv > CV_MIN_THRESHOLD]
    ni_cut = float(np.median(ni_pos)) if len(ni_pos) else 0.0
    cv_cut = float(np.median(cv_pos)) if len(cv_pos) else 0.0
    return (ni >= ni_cut) & (cv >= cv_cut)


def priority_capture_rows(
    base_score: np.ndarray,
    future_score: np.ndarray,
    future_cv: np.ndarray,
    budgets: list[tuple[str, int]],
) -> list[dict]:
    rows = []
    denom = float(np.nansum(future_score))
    if denom <= 0:
        return rows

    strategies = {
        "baseline_bottleneck_priority": base_score,
        "future_bottleneck_upper_bound": future_score,
        "future_CV_only": future_cv,
    }
    n_edges = len(future_score)
    for budget_label, k in budgets:
        k = min(max(int(k), 1), n_edges)
        for strategy, ranking_score in strategies.items():
            idx = top_indices(ranking_score, k)
            rows.append(
                {
                    "budget": budget_label,
                    "top_k": k,
                    "strategy": strategy,
                    "future_bottleneck_capture_share": round(
                        float(np.nansum(future_score[idx]) / denom), 6
                    ),
                }
            )
        rows.append(
            {
                "budget": budget_label,
                "top_k": k,
                "strategy": "random_expectation",
                "future_bottleneck_capture_share": round(float(k / n_edges), 6),
            }
        )
    return rows


def country_hotspot_rows(
    base_score: np.ndarray,
    future_score: np.ndarray,
    country_by_edge: np.ndarray,
    countries: list[str],
    shares: list[float],
) -> tuple[list[dict], list[dict]]:
    rows = []
    summary = []
    valid_country = country_by_edge >= 0
    for share in shares:
        k = max(1, int(round(len(base_score) * share)))
        base_top = top_indices(base_score, k)
        fut_top = top_indices(future_score, k)
        base_counts = np.bincount(
            country_by_edge[base_top][country_by_edge[base_top] >= 0],
            minlength=len(countries),
        )
        fut_counts = np.bincount(
            country_by_edge[fut_top][country_by_edge[fut_top] >= 0],
            minlength=len(countries),
        )
        top_base = set(np.argsort(base_counts)[-10:])
        top_future = set(np.argsort(fut_counts)[-10:])
        denom = len(top_base | top_future)
        overlap = len(top_base & top_future) / denom if denom else 1.0
        rho, _ = spearmanr(base_counts, fut_counts)
        summary.append(
            {
                "top_share_pct": round(share * 100, 3),
                "top_k": k,
                "matched_country_edge_share": round(float(valid_country.mean()), 4),
                "top10_country_overlap": round(float(overlap), 4),
                "country_count_spearman": round(float(rho), 4),
            }
        )
        for code, country in enumerate(countries):
            rows.append(
                {
                    "top_share_pct": round(share * 100, 3),
                    "country": country,
                    "baseline_top_edges": int(base_counts[code]),
                    "future_top_edges": int(fut_counts[code]),
                    "baseline_rank": int(
                        len(countries) - np.argsort(np.argsort(base_counts))[code]
                    ),
                    "future_rank": int(
                        len(countries) - np.argsort(np.argsort(fut_counts))[code]
                    ),
                }
            )
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_path_args(parser)
    parser.add_argument("--gcm", default="MPI-M-MPI-ESM-LR")
    parser.add_argument("--rcp", default="rcp85")
    parser.add_argument("--period", type=int, default=2085)
    parser.add_argument("--top-k", type=int, default=500)
    parser.add_argument(
        "--write-matched-edge-sample",
        action="store_true",
        help="Write a small top-edge sample for inspection; no full per-edge file is written.",
    )
    args = parser.parse_args()

    paths = resolve_paths(args.base_dir, args.output_dir)
    out_dir = ensure_dir(paths.output_root / "05_future_scenarios")
    edge_scores = paths.bottleneck_dir / "02_edge_scores.csv"
    future_dir = paths.road_speed_future / f"{args.gcm}_{args.rcp}_{args.period}"

    baseline = load_baseline(edge_scores)
    roads, countries = load_future_arrays(future_dir)

    ni = baseline["NI"].to_numpy(dtype=float)
    cv_base = baseline["CV"].to_numpy(dtype=float)
    base_score = bottleneck_score(ni, cv_base)

    match_idx, matched = spatial_match(baseline, roads)
    cv_future = compute_future_cv(cv_base, roads, match_idx)
    future_score = bottleneck_score(ni, cv_future)

    country_by_edge = np.full(len(baseline), -1, dtype=np.int16)
    country_by_edge[matched] = roads["country_code"][match_idx[matched]]

    base_strategic = strategic_mask(ni, cv_base)
    future_strategic = strategic_mask(ni, cv_future)
    strategic_retention = (
        float((base_strategic & future_strategic).sum() / base_strategic.sum())
        if base_strategic.sum() > 0
        else np.nan
    )
    rho, _ = spearmanr(base_score, future_score)
    cv_base_mean = float(np.mean(cv_base[cv_base > 0]))
    cv_future_mean = float(np.mean(cv_future[cv_future > 0]))

    topk_grid = [(f"K={args.top_k}", args.top_k)]
    for share in TOPK_SHARES:
        topk_grid.append(
            (f"top_{share * 100:g}pct", int(round(len(base_score) * share)))
        )

    topk_rows = []
    for label, k in topk_grid:
        topk_rows.append(
            {
                "gcm": args.gcm,
                "rcp": args.rcp,
                "period": args.period,
                "budget": label,
                "top_k": int(k),
                "jaccard_overlap": round(
                    jaccard(top_indices(base_score, k), top_indices(future_score, k)), 4
                ),
            }
        )

    priority_budgets = [
        ("0.1pct", int(round(len(base_score) * 0.001))),
        ("1pct", int(round(len(base_score) * 0.01))),
        ("3pct", int(round(len(base_score) * 0.03))),
        ("5pct", int(round(len(base_score) * 0.05))),
        ("10pct", int(round(len(base_score) * 0.10))),
    ]
    priority_rows = priority_capture_rows(
        base_score, future_score, cv_future, priority_budgets
    )

    hotspot_rows, hotspot_summary = country_hotspot_rows(
        base_score, future_score, country_by_edge, countries, [0.01, 0.05, 0.10]
    )

    summary = pd.DataFrame(
        [
            {
                "gcm": args.gcm,
                "rcp": args.rcp,
                "period": args.period,
                "n_edges": int(len(baseline)),
                "n_future_road_segments": int(len(roads["center_lon"])),
                "n_country_speed_csv": int(len(countries)),
                "match_rate_pct": round(float(matched.mean() * 100.0), 2),
                "spearman_rho": round(float(rho), 4),
                "strategic_retention_pct": round(float(strategic_retention * 100), 2),
                "mean_cv_baseline": round(cv_base_mean, 4),
                "mean_cv_future": round(cv_future_mean, 4),
                "cv_change_pct": round(
                    float((cv_future_mean - cv_base_mean) / cv_base_mean * 100.0), 2
                ),
            }
        ]
    )

    write_table(
        summary, out_dir / f"rcp85_stability_summary_{args.gcm}_{args.period}.csv"
    )
    write_table(
        pd.DataFrame(topk_rows),
        out_dir / f"rcp85_topk_overlap_{args.gcm}_{args.period}.csv",
    )
    write_table(
        pd.DataFrame(priority_rows),
        out_dir / f"rcp85_priority_capture_{args.gcm}_{args.period}.csv",
    )
    write_table(
        pd.DataFrame(hotspot_rows),
        out_dir / f"rcp85_hotspot_countries_{args.gcm}_{args.period}.csv",
    )
    write_table(
        pd.DataFrame(hotspot_summary),
        out_dir / f"rcp85_hotspot_summary_{args.gcm}_{args.period}.csv",
    )

    if args.write_matched_edge_sample:
        sample_idx = top_indices(future_score, min(5000, len(future_score)))
        sample = baseline.iloc[sample_idx][
            ["u", "v", "mid_lon", "mid_lat", "NI", "CV"]
        ].copy()
        sample["CV_future"] = cv_future[sample_idx]
        sample["bottleneck_base"] = base_score[sample_idx]
        sample["bottleneck_future"] = future_score[sample_idx]
        sample["matched_country"] = [
            countries[int(code)] if code >= 0 else ""
            for code in country_by_edge[sample_idx]
        ]
        write_table(
            sample, out_dir / f"rcp85_top_edge_sample_{args.gcm}_{args.period}.csv"
        )

    priority_df = pd.DataFrame(priority_rows)
    one_pct = priority_df[priority_df["budget"] == "1pct"].set_index("strategy")
    target = float(
        one_pct.loc["baseline_bottleneck_priority", "future_bottleneck_capture_share"]
    )
    cv_only = float(one_pct.loc["future_CV_only", "future_bottleneck_capture_share"])
    random = float(one_pct.loc["random_expectation", "future_bottleneck_capture_share"])
    topk_df = pd.DataFrame(topk_rows)
    k500_j = float(
        topk_df.loc[topk_df["budget"] == f"K={args.top_k}", "jaccard_overlap"].iloc[0]
    )
    top1_j = float(
        topk_df.loc[topk_df["budget"] == "top_1pct", "jaccard_overlap"].iloc[0]
    )
    top3_j = float(
        topk_df.loc[topk_df["budget"] == "top_3pct", "jaccard_overlap"].iloc[0]
    )
    top10_j = float(
        topk_df.loc[topk_df["budget"] == "top_10pct", "jaccard_overlap"].iloc[0]
    )
    hotspot_df = pd.DataFrame(hotspot_summary)
    hotspot1 = float(
        hotspot_df.loc[
            hotspot_df["top_share_pct"] == 1.0, "top10_country_overlap"
        ].iloc[0]
    )
    hotspot5 = float(
        hotspot_df.loc[
            hotspot_df["top_share_pct"] == 5.0, "top10_country_overlap"
        ].iloc[0]
    )
    hotspot10 = float(
        hotspot_df.loc[
            hotspot_df["top_share_pct"] == 10.0, "top10_country_overlap"
        ].iloc[0]
    )
    interpretation = pd.DataFrame(
        [
            {
                "check": "bottleneck ranking under stronger forcing",
                "result": (
                    "rank_stable_exact_topk_moderate"
                    if rho >= 0.85 and top3_j >= 0.55
                    else "sensitive"
                ),
                "evidence": (
                    f"Spearman={rho:.3f}; Jaccard K={args.top_k}: {k500_j:.3f}; "
                    f"top-1%={top1_j:.3f}; top-3%={top3_j:.3f}; "
                    f"top-10%={top10_j:.3f}"
                ),
            },
            {
                "check": "key hotspot geography",
                "result": (
                    "stable" if hotspot1 >= 0.7 and hotspot5 >= 0.7 else "sensitive"
                ),
                "evidence": (
                    "top-10 country overlap: "
                    f"top-1% edges={hotspot1:.3f}; top-5%={hotspot5:.3f}; "
                    f"top-10%={hotspot10:.3f}"
                ),
            },
            {
                "check": "targeted paving priority proxy vs CV-only and random",
                "result": (
                    "stable" if target > cv_only and target > random else "sensitive"
                ),
                "evidence": (
                    "1% future bottleneck-score capture: "
                    f"baseline bottleneck priority={target:.3f}, "
                    f"future CV-only={cv_only:.3f}, random={random:.3f}"
                ),
            },
        ]
    )
    write_table(
        interpretation, out_dir / f"rcp85_interpretation_{args.gcm}_{args.period}.csv"
    )

    print("RCP8.5 future stability written to:", out_dir)
    print(summary.to_string(index=False))
    print(interpretation.to_string(index=False))


if __name__ == "__main__":
    main()
