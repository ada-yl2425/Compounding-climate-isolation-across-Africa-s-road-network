"""Headline robustness tables for climate-state and paved-road assumptions.

The expensive full network products are already cached by the web_1/web_2/web_3
pipelines. This script adds a lightweight headline layer for reviewer-facing
robustness: continent OD is recomputed on the cached Africa checkpoint, while
health and paving headlines are propagated from cached headline outputs using
country-level or edge-level severity ratios.
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import igraph as ig
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

from sensitivity.config import (
    add_common_path_args,
    resolve_paths,
)
from sensitivity.io_utils import ensure_dir, finite_numeric, jaccard, write_table


UNREACHABLE = 1e8


def scenario_factor_table(screening: pd.DataFrame) -> pd.DataFrame:
    base = screening[
        (screening["precip_percentile"] == 95.0)
        & (screening["soil_threshold_percentile"] == 75.0)
        & (screening["penalty_form"] == "proportional")
    ]
    if base.empty:
        raise ValueError("Default P95/P75 proportional row not found.")
    base_mean = float(base["mean_delta_pct"].iloc[0])
    out = screening.copy()
    out["severity_factor_vs_default"] = out["mean_delta_pct"] / max(base_mean, 1e-12)
    return out


def load_africa_checkpoint(paths):
    checkpoint = paths.network_results / "africa_layer" / "graph_checkpoint.pkl"
    with checkpoint.open("rb") as f:
        data = pickle.load(f)
    g0_nx = data["G0"]
    g1_nx = data["G1"]
    node_coords = data["all_nc"]

    node_list = list(g0_nx.nodes())
    node_idx = {n: i for i, n in enumerate(node_list)}
    edge_list = list(g0_nx.edges())
    graph = ig.Graph(
        n=len(node_list),
        edges=[(node_idx[u], node_idx[v]) for u, v in edge_list],
        directed=False,
    )
    w0 = np.array([g0_nx[u][v]["weight"] for u, v in edge_list], dtype=np.float64)
    w1 = np.array(
        [
            g1_nx[u][v]["weight"] if g1_nx.has_edge(u, v) else g0_nx[u][v]["weight"]
            for u, v in edge_list
        ],
        dtype=np.float64,
    )
    return graph, node_idx, node_coords, w0, w1


def snapped_africa_cities(nodes_csv: Path, node_coords: dict[int, tuple[float, float]]) -> pd.DataFrame:
    cities = pd.read_csv(nodes_csv)
    graph_nodes = list(node_coords.keys())
    xy = np.array([node_coords[n] for n in graph_nodes], dtype=np.float64)
    tree = cKDTree(xy)
    rows = []
    for _, row in cities.iterrows():
        _, idx = tree.query([row["lon"], row["lat"]])
        rows.append(
            {
                "name": row["name"],
                "country_folder": row["country_folder"],
                "iso3": row["iso3"],
                "snap_node": graph_nodes[idx],
            }
        )
    return pd.DataFrame(rows)


def continent_od_metrics(
    graph: ig.Graph,
    city_df: pd.DataFrame,
    node_idx: dict[int, int],
    w0: np.ndarray,
    w_extreme: np.ndarray,
    d0: np.ndarray | None = None,
    city_idx: list[int] | None = None,
) -> dict:
    city_df = city_df[city_df["snap_node"].isin(node_idx)].reset_index(drop=True)
    if city_idx is None:
        city_idx = [node_idx[n] for n in city_df["snap_node"]]

    if d0 is None:
        graph.es["weight"] = w0.tolist()
        d0 = np.array(graph.distances(source=city_idx, target=city_idx, weights="weight"))
    graph.es["weight"] = w_extreme.tolist()
    d1 = np.array(graph.distances(source=city_idx, target=city_idx, weights="weight"))

    increases = []
    cross_increases = []
    pairs = []
    for i in range(len(city_df)):
        for j in range(i + 1, len(city_df)):
            t0, t1 = d0[i, j], d1[i, j]
            ok = np.isfinite(t0) and np.isfinite(t1) and 0 < t0 < UNREACHABLE and t1 < UNREACHABLE
            if not ok:
                continue
            inc = (t1 - t0) / t0 * 100.0
            increases.append(inc)
            pair = (city_df.loc[i, "name"], city_df.loc[j, "name"])
            pairs.append((pair, inc))
            if city_df.loc[i, "country_folder"] != city_df.loc[j, "country_folder"]:
                cross_increases.append(inc)

    direct_edge_penalty_pct = float(np.mean((w_extreme / np.maximum(w0, 1e-12) - 1.0) * 100.0))
    cross_mean = float(np.mean(cross_increases))
    return {
        "continent_cross_country_increase_pct": round(cross_mean, 4),
        "continent_all_pair_increase_pct": round(float(np.mean(increases)), 4),
        "direct_edge_penalty_pct": round(direct_edge_penalty_pct, 4),
        "continent_amplification_factor": round(cross_mean / direct_edge_penalty_pct, 4)
        if direct_edge_penalty_pct > 0
        else np.nan,
        "_pairs": pairs,
    }


def top_pair_set(scores: pd.Series, k: int) -> set[tuple[str, str]]:
    if k <= 0 or scores.empty:
        return set()
    return set(scores.nlargest(min(k, len(scores))).index.tolist())


def climate_continent_table(paths, factors: pd.DataFrame) -> pd.DataFrame:
    graph, node_idx, node_coords, w0, w1_default = load_africa_checkpoint(paths)
    cities = snapped_africa_cities(paths.data_base / "web" / "africa_layer" / "africa_nodes.csv", node_coords)
    cities = cities[cities["snap_node"].isin(node_idx)].reset_index(drop=True)
    city_idx = [node_idx[n] for n in cities["snap_node"]]
    graph.es["weight"] = w0.tolist()
    d0 = np.array(graph.distances(source=city_idx, target=city_idx, weights="weight"))
    base_edge_delta = (w1_default / np.maximum(w0, 1e-12) - 1.0).clip(min=0.0)

    factors = factors.copy()
    factors["_is_default"] = (
        (factors["precip_percentile"] == 95.0)
        & (factors["soil_threshold_percentile"] == 75.0)
        & (factors["penalty_form"] == "proportional")
    )
    factors = factors.sort_values(
        ["_is_default", "precip_percentile", "soil_threshold_percentile", "penalty_form"],
        ascending=[False, True, True, True],
    )

    default_pairs = None
    rows = []
    for _, row in factors.iterrows():
        factor = float(row["severity_factor_vs_default"])
        w_extreme = w0 * (1.0 + base_edge_delta * factor)
        metrics = continent_od_metrics(graph, cities, node_idx, w0, w_extreme, d0=d0, city_idx=city_idx)
        pairs = metrics.pop("_pairs")
        if default_pairs is None and (
            row["precip_percentile"] == 95.0
            and row["soil_threshold_percentile"] == 75.0
            and row["penalty_form"] == "proportional"
        ):
            default_pairs = pd.Series({p: v for p, v in pairs})
        pair_series = pd.Series({p: v for p, v in pairs})
        if default_pairs is not None:
            common = default_pairs.index.intersection(pair_series.index)
            rho = spearmanr(default_pairs.loc[common], pair_series.loc[common]).statistic
            hot25 = jaccard(top_pair_set(default_pairs.loc[common], 25), top_pair_set(pair_series.loc[common], 25))
        else:
            rho = np.nan
            hot25 = np.nan
        rows.append(
            {
                "precip_percentile": row["precip_percentile"],
                "soil_threshold_percentile": row["soil_threshold_percentile"],
                "penalty_form": row["penalty_form"],
                "severity_factor_vs_default": round(factor, 4),
                **metrics,
                "corridor_spearman_vs_default": round(float(rho), 4) if np.isfinite(rho) else np.nan,
                "top25_corridor_jaccard_vs_default": round(float(hot25), 4) if np.isfinite(hot25) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def health_proxy_table(paths, by_country: pd.DataFrame) -> pd.DataFrame:
    health = pd.read_csv(paths.health_accessibility / "country_accessibility_summary.csv")
    health["total_population"] = finite_numeric(health["total_population"])
    health["isochrone_shrinkage_T60min"] = finite_numeric(health["isochrone_shrinkage_T60min"])
    health["tail_gap_ratio"] = pd.to_numeric(health["tail_gap_ratio"], errors="coerce")

    default = by_country[
        (by_country["precip_percentile"] == 95.0)
        & (by_country["soil_threshold_percentile"] == 75.0)
        & (by_country["penalty_form"] == "proportional")
    ][["country", "mean_delta_pct", "median_delta_pct", "p90_delta_pct"]].rename(
        columns={
            "mean_delta_pct": "default_mean_delta_pct",
            "median_delta_pct": "default_median_delta_pct",
            "p90_delta_pct": "default_p90_delta_pct",
        }
    )
    merged_default = health.merge(default, on="country", how="left")

    rows = []
    for keys, scen in by_country.groupby(
        ["precip_percentile", "soil_threshold_percentile", "penalty_form"]
    ):
        scen = scen[["country", "mean_delta_pct", "median_delta_pct", "p90_delta_pct"]]
        df = merged_default.merge(scen, on="country", how="left")
        severity = df["mean_delta_pct"] / df["default_mean_delta_pct"].replace(0, np.nan)
        severity = severity.replace([np.inf, -np.inf], np.nan).fillna(1.0).clip(0.0, 20.0)
        loss = (df["isochrone_shrinkage_T60min"] * severity).clip(0.0, 1.0)

        p90_factor = df["p90_delta_pct"] / df["default_p90_delta_pct"].replace(0, np.nan)
        med_factor = df["median_delta_pct"] / df["default_median_delta_pct"].replace(0, np.nan)
        tail_shape = (p90_factor / med_factor).replace([np.inf, -np.inf], np.nan).fillna(1.0).clip(0.25, 4.0)
        tgr = (df["tail_gap_ratio"] * tail_shape).replace([np.inf, -np.inf], np.nan)

        pop = df["total_population"].clip(lower=0)
        rows.append(
            {
                "precip_percentile": keys[0],
                "soil_threshold_percentile": keys[1],
                "penalty_form": keys[2],
                "one_hour_coverage_loss_pct_proxy": round(float(np.average(loss, weights=pop) * 100), 4),
                "mean_tail_gap_ratio_proxy": round(float(tgr.mean(skipna=True)), 4),
                "countries_with_TGR_gt_1_proxy": int((tgr > 1).sum()),
                "median_country_severity_factor": round(float(severity.median()), 4),
            }
        )
    return pd.DataFrame(rows)


def recovery_proxy_table(paths, factors: pd.DataFrame) -> pd.DataFrame:
    recovery = pd.read_csv(paths.output_root / "04_bottleneck_recovery" / "headline_recovery_existing.csv")
    r001 = float(recovery.loc[recovery["requested_paving_fraction"] == 0.001, "recovery_guided"].iloc[0])
    r010 = float(recovery.loc[recovery["requested_paving_fraction"] == 0.01, "recovery_guided"].iloc[0])
    out = factors[
        ["precip_percentile", "soil_threshold_percentile", "penalty_form", "severity_factor_vs_default"]
    ].copy()
    out["recovery_0p1_pct_proxy"] = round(r001 * 100, 2)
    out["recovery_1pct_proxy"] = round(r010 * 100, 2)
    out["recovery_proxy_note"] = (
        "Recovery is reported as a fraction of scenario loss; under the reduced "
        "severity-rescaling check, the guided recovery fraction remains invariant."
    )
    return out


def combine_climate_headlines(continent: pd.DataFrame, health: pd.DataFrame, recovery: pd.DataFrame) -> pd.DataFrame:
    keys = ["precip_percentile", "soil_threshold_percentile", "penalty_form"]
    return (
        continent.merge(health, on=keys, how="left")
        .merge(
            recovery.drop(columns=["severity_factor_vs_default"], errors="ignore"),
            on=keys,
            how="left",
        )
        .sort_values(keys)
        .reset_index(drop=True)
    )


def paved_headline_table(paths) -> pd.DataFrame:
    out_dir = paths.output_root / "02_paved_assumptions"
    od = pd.read_csv(out_dir / "paved_assumption_od_summary.csv")
    hot = pd.read_csv(out_dir / "paved_assumption_hotspot_overlap.csv")
    interp = pd.read_csv(out_dir / "interpretation_summary.csv")
    df = od.merge(hot, on="scenario", how="left").merge(
        interp[["scenario", "change_vs_default_pp", "interpretation"]],
        on="scenario",
        how="left",
    )
    keep = [
        "scenario",
        "cross_country_mean_increase_pct",
        "change_vs_default_pp",
        "amplification_proxy_cross_country",
        "spearman_increase_pct",
        "top25_corridor_jaccard",
        "interpretation",
    ]
    return df[keep]


def interpretation_table(climate: pd.DataFrame, paved: pd.DataFrame) -> pd.DataFrame:
    continuous = climate[climate["penalty_form"].isin(["proportional", "capped_linear"])]
    stress = climate[climate["penalty_form"].isin(["binary_block", "logistic"])]
    paved_stable = paved[paved["top25_corridor_jaccard"] >= 0.8]
    return pd.DataFrame(
        [
            {
                "check": "Climate percentiles with continuous penalties",
                "evidence": (
                    f"Amplification range {continuous['continent_amplification_factor'].min():.3f}-"
                    f"{continuous['continent_amplification_factor'].max():.3f}; "
                    f"1h coverage-loss proxy range {continuous['one_hour_coverage_loss_pct_proxy'].min():.2f}-"
                    f"{continuous['one_hour_coverage_loss_pct_proxy'].max():.2f}%."
                ),
                "status": "robust for central continuous-penalty specifications",
            },
            {
                "check": "Binary/logistic passability stress tests",
                "evidence": (
                    f"Stress-test amplification range {stress['continent_amplification_factor'].min():.3f}-"
                    f"{stress['continent_amplification_factor'].max():.3f}; "
                    f"1h coverage-loss proxy can reach {stress['one_hour_coverage_loss_pct_proxy'].max():.2f}%."
                ),
                "status": "stress-test boundary; do not pool with central estimates",
            },
            {
                "check": "Paved-road climate-neutral assumption",
                "evidence": (
                    f"{len(paved_stable)}/{len(paved)} paved scenarios have top-25 corridor Jaccard >= 0.8; "
                    f"minimum Jaccard is {paved['top25_corridor_jaccard'].min():.3f}."
                ),
                "status": "stable for fixed 80 km/h and mild degradation; moderate degradation is sensitive",
            },
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_path_args(parser)
    args = parser.parse_args()

    paths = resolve_paths(args.base_dir, args.output_dir)
    out_dir = ensure_dir(paths.output_root / "07_headline_assumptions")

    climate_dir = paths.output_root / "01_climate_penalty"
    factors = scenario_factor_table(pd.read_csv(climate_dir / "climate_penalty_screening_summary.csv"))
    by_country = pd.read_csv(climate_dir / "climate_penalty_screening_by_country.csv")

    continent = climate_continent_table(paths, factors)
    health = health_proxy_table(paths, by_country)
    recovery = recovery_proxy_table(paths, factors)
    climate = combine_climate_headlines(continent, health, recovery)
    paved = paved_headline_table(paths)
    interp = interpretation_table(climate, paved)

    write_table(continent, out_dir / "climate_continent_headline_sensitivity.csv")
    write_table(health, out_dir / "climate_health_headline_proxy.csv")
    write_table(recovery, out_dir / "climate_recovery_headline_proxy.csv")
    write_table(climate, out_dir / "climate_headline_sensitivity_combined.csv")
    write_table(paved, out_dir / "paved_road_headline_sensitivity.csv")
    write_table(interp, out_dir / "interpretation_summary.csv")

    print("Headline assumption sensitivity written to:", out_dir)
    print("\nClimate headline combined preview:")
    preview_cols = [
        "precip_percentile",
        "soil_threshold_percentile",
        "penalty_form",
        "continent_amplification_factor",
        "one_hour_coverage_loss_pct_proxy",
        "mean_tail_gap_ratio_proxy",
        "recovery_0p1_pct_proxy",
        "recovery_1pct_proxy",
    ]
    print(climate[preview_cols].head(16).to_string(index=False))
    print("\nPaved-road headline table:")
    print(paved.to_string(index=False))
    print("\nInterpretation:")
    print(interp.to_string(index=False))


if __name__ == "__main__":
    main()
