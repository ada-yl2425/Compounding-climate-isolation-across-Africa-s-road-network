"""
bottleneck_stability.py
========================
Proves that top-K strategic bottleneck roads remain stable across future
climate scenarios (2040, 2060, 2080 × rcp26 / rcp45 / rcp85).

Method
------
  NI (network importance) is purely topological — it does NOT change with
  climate.  Only CV (climate vulnerability = relative travel-time increase
  under extreme weather) needs to be re-evaluated for each future scenario.

  New CV for an edge (u, v) under a future scenario:
      CV_future = V_normal / (V_extreme_future × (1 − p_block_future)) − 1

  V_normal is the same as the baseline (road quality unchanged).
  V_extreme_future and p_block_future come from future_road_speed.py outputs.

  Stability metrics (per scenario):
    • Jaccard@K   : |top-K_future ∩ top-K_baseline| / |union|
    • Spearman ρ  : rank correlation of bottleneck scores across all edges
    • Retention % : % of current "strategic" roads (High NI × High CV quadrant)
                    that remain strategic under the future scenario

Spatial matching
----------------
  02_edge_scores.csv has (mid_lon, mid_lat) for each edge.
  Future road speed CSVs have (center_lon, center_lat) per road segment.
  These are matched via KD-tree with a ≤ 0.02° tolerance (~2 km).
  Unmatched edges retain their baseline CV (conservative assumption).

Usage:
    python result3/bottleneck_stability.py \\
        --base-dir <BASE_DIR> \\
        --edge-scores <EDGE_SCORES_CSV> \\
        --scenarios rcp26 rcp45 rcp85 \\
        --periods 2040 2060 2080 \\
        --gcm MPI-M-MPI-ESM-LR \\
        --top-k 500

Output:
    <BASE_DIR>/web/network_results/bottleneck_paving/bottleneck_stability_report.csv
    <BASE_DIR>/web/network_results/bottleneck_paving/bottleneck_stability_{scenario}_{period}.csv
"""

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")

MATCH_TOLERANCE_DEG = 0.02  # ~2 km
CV_MIN_THRESHOLD = 0.02  # same as bottleneck_network.py
TOP_K_DEFAULT = 500


# =============================================================================
# LOAD BASELINE EDGE SCORES
# =============================================================================
def load_baseline(edge_scores_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(edge_scores_csv)
    required = {"u", "v", "mid_lon", "mid_lat", "w0", "NI", "CV"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"02_edge_scores.csv missing columns: {missing}")

    df["_edge_id"] = df.index
    df["NI"] = pd.to_numeric(df["NI"], errors="coerce").fillna(0)
    df["CV"] = pd.to_numeric(df["CV"], errors="coerce").fillna(0)
    df["w0"] = pd.to_numeric(df["w0"], errors="coerce")
    df["V_normal_implied"] = np.where(df["w0"] > 0, 1.0 / df["w0"], np.nan)

    ni_pos = df["NI"][df["NI"] > 0]
    cv_pos = df["CV"][df["CV"] > CV_MIN_THRESHOLD]
    ni_med = float(ni_pos.median()) if len(ni_pos) else 0.0
    cv_med = float(cv_pos.median()) if len(cv_pos) else 0.0
    df["_strategic"] = (df["NI"] >= ni_med) & (df["CV"] >= cv_med)

    print(f"  Baseline: {len(df):,} edges")
    print(f"  NI > 0: {(df['NI'] > 0).sum():,}")
    print(f"  CV > {CV_MIN_THRESHOLD}: {(df['CV'] > CV_MIN_THRESHOLD).sum():,}")
    print(f"  Strategic (High NI × High CV): {df['_strategic'].sum():,}")
    return df


# =============================================================================
# LOAD FUTURE ROAD SPEEDS FOR ALL COUNTRIES
# =============================================================================
def load_future_speeds(future_dir: Path) -> pd.DataFrame:
    """Load all country CSVs from a scenario/period directory."""
    dfs = []
    for csv_path in sorted(future_dir.glob("*_road_speed.csv")):
        try:
            df = pd.read_csv(
                csv_path,
                usecols=[
                    "road_id",
                    "center_lon",
                    "center_lat",
                    "V_normal",
                    "V_extreme",
                    "p_block",
                ],
            )
            dfs.append(df)
        except Exception as e:
            print(f"  [WARN] Could not read {csv_path.name}: {e}")
    if not dfs:
        return None
    combined = pd.concat(dfs, ignore_index=True)
    for col in ["V_normal", "V_extreme", "p_block"]:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")
    combined = combined.dropna(
        subset=["center_lon", "center_lat", "V_extreme", "p_block"]
    )
    combined["V_extreme"] = combined["V_extreme"].clip(lower=0.5)
    combined["p_block"] = combined["p_block"].clip(0, 0.99)
    return combined


# =============================================================================
# SPATIAL MATCH: edge midpoints → road segment centroids
# =============================================================================
def spatial_match(edges_df: pd.DataFrame, roads_df: pd.DataFrame) -> pd.Series:
    """
    Returns a Series indexed by edge index, values = matched road index (or -1).
    """
    road_xy = roads_df[["center_lon", "center_lat"]].values
    tree = cKDTree(road_xy)
    edge_xy = edges_df[["mid_lon", "mid_lat"]].values
    dists, idxs = tree.query(edge_xy, workers=-1)
    matched = np.where(dists <= MATCH_TOLERANCE_DEG, idxs, -1)
    return pd.Series(matched, index=edges_df.index)


# =============================================================================
# COMPUTE FUTURE CV AND BOTTLENECK
# =============================================================================
def compute_future_cv(
    edges_df: pd.DataFrame, roads_df: pd.DataFrame, match_series: pd.Series
) -> pd.Series:
    """
    CV_future = V_normal / (V_extreme_future × (1 − p_block_future)) − 1

    Edges with no match retain their baseline CV.
    """
    cv_future = edges_df["CV"].copy()

    matched_mask = match_series >= 0
    edge_idx = edges_df.index[matched_mask]
    road_idx = match_series[matched_mask].values

    matched_roads = roads_df.iloc[road_idx].reset_index(drop=True)
    matched_edges = edges_df.loc[edge_idx].reset_index(drop=True)

    v_n = matched_roads["V_normal"].values.clip(0.5)
    v_e = matched_roads["V_extreme"].values.clip(0.5)
    pb = matched_roads["p_block"].values.clip(0, 0.99)

    cv_vals = v_n / (v_e * (1.0 - pb)) - 1.0
    cv_vals = np.clip(cv_vals, 0, None)

    cv_future.loc[edge_idx] = cv_vals
    return cv_future


def compute_bottleneck_scores(ni: pd.Series, cv: pd.Series) -> pd.Series:
    ni_pos = ni[ni > 0]
    cv_pos = cv[cv > CV_MIN_THRESHOLD]
    ni_max = float(ni_pos.max()) if len(ni_pos) else 1.0
    cv_max = float(cv_pos.max()) if len(cv_pos) else 1.0
    ni_norm = (ni / ni_max).clip(0, 1)
    cv_norm = (cv / cv_max).clip(0, 1)
    return ni_norm * cv_norm


# =============================================================================
# STABILITY METRICS
# =============================================================================
def jaccard_at_k(baseline_scores: pd.Series, future_scores: pd.Series, k: int) -> float:
    top_b = set(baseline_scores.nlargest(k).index)
    top_f = set(future_scores.nlargest(k).index)
    if not top_b and not top_f:
        return 1.0
    return len(top_b & top_f) / len(top_b | top_f)


def strategic_retention(
    baseline_strategic: pd.Series,
    future_scores: pd.Series,
    ni: pd.Series,
    future_cv: pd.Series,
) -> float:
    """Fraction of current strategic roads that remain in High-NI × High-CV quadrant."""
    ni_pos = ni[ni > 0]
    cv_pos = future_cv[future_cv > CV_MIN_THRESHOLD]
    ni_med = float(ni_pos.median()) if len(ni_pos) else 0.0
    cv_med = float(cv_pos.median()) if len(cv_pos) else 0.0
    future_strategic = (ni >= ni_med) & (future_cv >= cv_med)
    n_base = baseline_strategic.sum()
    if n_base == 0:
        return float("nan")
    retained = (baseline_strategic & future_strategic).sum()
    return float(retained / n_base)


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Bottleneck stability across future scenarios"
    )
    parser.add_argument("--base-dir", required=True)
    parser.add_argument(
        "--edge-scores",
        default=None,
        help="Path to 02_edge_scores.csv (default: auto-locate under base-dir)",
    )
    parser.add_argument("--gcm", default="MPI-M-MPI-ESM-LR")
    parser.add_argument("--scenarios", nargs="+", default=["rcp26", "rcp45", "rcp85"])
    parser.add_argument("--periods", nargs="+", type=int, default=[2045, 2065, 2085])
    parser.add_argument("--top-k", type=int, default=TOP_K_DEFAULT)
    args = parser.parse_args()

    base = Path(args.base_dir)
    edge_scores_path = (
        Path(args.edge_scores)
        if args.edge_scores
        else (
            base
            / "web"
            / "network_results"
            / "bottleneck_paving"
            / "02_edge_scores.csv"
        )
    )
    out_dir = base / "web" / "network_results" / "bottleneck_paving"
    out_dir.mkdir(parents=True, exist_ok=True)
    future_base = base / "road_speed_future"

    print(f"\n{'='*60}")
    print(f"  Bottleneck Stability Analysis")
    print(f"  GCM: {args.gcm}")
    print(f"  Scenarios: {args.scenarios}")
    print(f"  Periods:   {args.periods}")
    print(f"  Top-K:     {args.top_k}")
    print(f"{'='*60}\n")

    print("[1] Loading baseline edge scores...")
    baseline = load_baseline(edge_scores_path)

    baseline["bottleneck_base"] = compute_bottleneck_scores(
        baseline["NI"], baseline["CV"]
    )

    summary_rows = []

    for rcp in args.scenarios:
        for period in args.periods:
            label = f"{args.gcm}_{rcp}_{period}"
            future_dir = future_base / label
            print(f"\n[{label}]")

            if not future_dir.exists():
                print(f"  [SKIP] Directory not found: {future_dir}")
                summary_rows.append(
                    {
                        "gcm": args.gcm,
                        "rcp": rcp,
                        "period": period,
                        "status": "missing",
                        "n_matched": 0,
                        "jaccard_at_k": None,
                        "spearman_rho": None,
                        "strategic_retention_pct": None,
                        "mean_cv_baseline": None,
                        "mean_cv_future": None,
                        "cv_change_pct": None,
                    }
                )
                continue

            roads_df = load_future_speeds(future_dir)
            if roads_df is None or roads_df.empty:
                print(f"  [SKIP] No road speed CSVs found in {future_dir}")
                continue

            print(f"  Road segments loaded: {len(roads_df):,}")

            match_series = spatial_match(baseline, roads_df)
            n_matched = (match_series >= 0).sum()
            match_rate = n_matched / len(baseline) * 100
            print(
                f"  Matched edges: {n_matched:,} / {len(baseline):,}  ({match_rate:.1f}%)"
            )

            cv_future = compute_future_cv(baseline, roads_df, match_series)
            b_future = compute_bottleneck_scores(baseline["NI"], cv_future)

            # Save per-scenario edge-level results
            per_edge = baseline[
                [
                    "u",
                    "v",
                    "mid_lon",
                    "mid_lat",
                    "NI",
                    "CV",
                    "bottleneck_base",
                    "_strategic",
                ]
            ].copy()
            per_edge["CV_future"] = cv_future
            per_edge["bottleneck_future"] = b_future
            per_edge["CV_change_pct"] = (
                (cv_future - baseline["CV"]) / (baseline["CV"].clip(lower=0.001)) * 100
            )
            per_edge.to_csv(
                out_dir / f"bottleneck_stability_{rcp}_{period}.csv", index=False
            )

            # Stability metrics
            j_k = jaccard_at_k(baseline["bottleneck_base"], b_future, args.top_k)
            rho, _ = spearmanr(
                baseline["bottleneck_base"].fillna(0), b_future.fillna(0)
            )
            ret = strategic_retention(
                baseline["_strategic"], b_future, baseline["NI"], cv_future
            )

            cv_base_mean = float(baseline["CV"][baseline["CV"] > 0].mean())
            cv_fut_mean = float(cv_future[cv_future > 0].mean())
            cv_delta = (cv_fut_mean - cv_base_mean) / cv_base_mean * 100

            print(
                f"  Jaccard@{args.top_k}:          {j_k:.3f}  ({j_k*100:.1f}% overlap)"
            )
            print(f"  Spearman ρ:           {rho:.4f}")
            print(f"  Strategic retention:  {ret*100:.1f}%")
            print(
                f"  Mean CV: baseline={cv_base_mean:.3f}  future={cv_fut_mean:.3f}  Δ={cv_delta:+.1f}%"
            )

            summary_rows.append(
                {
                    "gcm": args.gcm,
                    "rcp": rcp,
                    "period": period,
                    "status": "ok",
                    "n_matched": int(n_matched),
                    "match_rate_pct": round(match_rate, 1),
                    "jaccard_at_k": round(j_k, 4),
                    "spearman_rho": round(float(rho), 4),
                    "strategic_retention_pct": round(ret * 100, 1),
                    "mean_cv_baseline": round(cv_base_mean, 4),
                    "mean_cv_future": round(cv_fut_mean, 4),
                    "cv_change_pct": round(cv_delta, 2),
                }
            )

    summary_df = pd.DataFrame(summary_rows)
    out_path = out_dir / "bottleneck_stability_report.csv"
    summary_df.to_csv(out_path, index=False)

    print(f"\n{'='*60}")
    print("  STABILITY SUMMARY")
    print(f"{'='*60}")
    ok_rows = summary_df[summary_df["status"] == "ok"]
    if not ok_rows.empty:
        print(
            ok_rows[
                [
                    "rcp",
                    "period",
                    "jaccard_at_k",
                    "spearman_rho",
                    "strategic_retention_pct",
                    "cv_change_pct",
                ]
            ].to_string(index=False)
        )
        print(
            f"\n  Mean Jaccard@{args.top_k} across scenarios: {ok_rows['jaccard_at_k'].mean():.3f}"
        )
        print(
            f"  Mean Spearman ρ:                        {ok_rows['spearman_rho'].mean():.4f}"
        )
        print(
            f"  Mean strategic retention:               {ok_rows['strategic_retention_pct'].mean():.1f}%"
        )
    print(f"\n  Report saved → {out_path}")


if __name__ == "__main__":
    main()
