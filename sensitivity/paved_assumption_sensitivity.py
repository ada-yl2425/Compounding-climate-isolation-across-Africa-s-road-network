"""Preflight and manifest for paved-road assumption robustness.

The road network treats paved-road speed as climate-neutral links filled with
the median unpaved speed. This program reruns the networks under alternative
paved assumptions. This script does not rebuild the graph by default; it writes
a scenario manifest and input status table so the rerun is explicit and reproducible.
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

from sensitivity.config import COUNTRIES, add_common_path_args, resolve_paths
from sensitivity.io_utils import (
    ensure_dir,
    finite_numeric,
    jaccard,
    top_set,
    write_table,
)

PAVED_SCENARIOS = [
    {
        "scenario": "default_web1",
        "paved_speed_normal_kmh": "median_unpaved_by_country",
        "paved_speed_extreme_kmh": "same_as_normal",
        "paved_p_block": 0.0,
        "interpretation": "current climate-neutral fill assumption",
    },
    {
        "scenario": "fixed_high_climate_neutral",
        "paved_speed_normal_kmh": 80.0,
        "paved_speed_extreme_kmh": 80.0,
        "paved_p_block": 0.0,
        "interpretation": "paved roads faster than median unpaved and climate-neutral",
    },
    {
        "scenario": "fixed_high_mild_degradation",
        "paved_speed_normal_kmh": 80.0,
        "paved_speed_extreme_kmh": 65.0,
        "paved_p_block": 0.1875,
        "interpretation": "paved roads faster but mildly degraded under extreme climate",
    },
    {
        "scenario": "fixed_high_light_degradation",
        "paved_speed_normal_kmh": 80.0,
        "paved_speed_extreme_kmh": 72.0,
        "paved_p_block": 0.10,
        "interpretation": "less severe paved-road climate degradation",
    },
]
OD_SCENARIOS = [
    {
        "scenario": "default_web1",
        "neutral_normal_speed_kmh": "as_checkpoint",
        "neutral_extreme_speed_kmh": "as_checkpoint",
        "neutral_extreme_multiplier": 1.0,
    },
    {
        "scenario": "fixed80_neutral",
        "neutral_normal_speed_kmh": 80.0,
        "neutral_extreme_speed_kmh": 80.0,
        "neutral_extreme_multiplier": 1.0,
    },
    {
        "scenario": "fixed80_to72_light_degradation",
        "neutral_normal_speed_kmh": 80.0,
        "neutral_extreme_speed_kmh": 72.0,
        "neutral_extreme_multiplier": 80.0 / 72.0,
    },
    {
        "scenario": "fixed80_to65_moderate_degradation",
        "neutral_normal_speed_kmh": 80.0,
        "neutral_extreme_speed_kmh": 65.0,
        "neutral_extreme_multiplier": 80.0 / 65.0,
    },
]
UNREACHABLE = 1e8


def speed_status(paths) -> pd.DataFrame:
    rows = []
    for country in COUNTRIES:
        speed_path = paths.road_speed / f"{country}_road_speed.csv"
        if not speed_path.exists():
            rows.append(
                {
                    "country": country,
                    "speed_csv_exists": False,
                    "n_unpaved_speed_rows": 0,
                    "median_unpaved_v_normal": None,
                    "median_unpaved_v_extreme": None,
                }
            )
            continue
        df = pd.read_csv(speed_path, usecols=lambda c: c in {"V_normal", "V_extreme"})
        rows.append(
            {
                "country": country,
                "speed_csv_exists": True,
                "n_unpaved_speed_rows": int(len(df)),
                "median_unpaved_v_normal": round(
                    float(finite_numeric(df["V_normal"]).median()), 3
                ),
                "median_unpaved_v_extreme": round(
                    float(finite_numeric(df["V_extreme"]).median()), 3
                ),
            }
        )
    return pd.DataFrame(rows)


def command_manifest(paths, repo_root: Path) -> pd.DataFrame:
    rows = []
    for scenario in PAVED_SCENARIOS:
        rows.append(
            {
                "scenario": scenario["scenario"],
                "step": "country_layer",
                "command_template": (
                    "python path/to/network_pipeline.py --base-dir "
                    f"{paths.data_base} --layer country --country <COUNTRY> "
                    "--surface all --paved-assumption "
                    f"{scenario['scenario']} --out-dir "
                    f"{paths.output_root}/02_paved_assumptions/{scenario['scenario']}/country_layer/<COUNTRY>"
                ),
                "note": "requires adding paved-assumption options to network builder before execution",
            }
        )
        rows.append(
            {
                "scenario": scenario["scenario"],
                "step": "africa_layer",
                "command_template": (
                    "python ABtest/run_africa_layer.py --base-dir "
                    f"{paths.data_base} --paved-assumption {scenario['scenario']} "
                    f"--out-dir {paths.output_root}/02_paved_assumptions/{scenario['scenario']}/africa_layer"
                ),
                "note": "requires paved-aware pan-African graph rerun",
            }
        )
    return pd.DataFrame(rows)


def load_snapped_cities(
    nodes_csv: Path, node_coords: dict[int, tuple[float, float]]
) -> pd.DataFrame:
    nodes = pd.read_csv(nodes_csv)
    graph_nodes = list(node_coords.keys())
    xy = np.array([node_coords[n] for n in graph_nodes], dtype=np.float64)
    tree = cKDTree(xy)
    snapped = []
    for _, row in nodes.iterrows():
        dist, idx = tree.query([row["lon"], row["lat"]])
        snapped.append(
            {
                "city_name": row["name"],
                "country_folder": row["country_folder"],
                "iso3": row["iso3"],
                "type": row.get("type", ""),
                "snap_node": graph_nodes[idx],
                "snap_dist_km": float(dist * 111.0),
            }
        )
    return pd.DataFrame(snapped)


def build_igraph_from_checkpoint(checkpoint_path: Path):
    with checkpoint_path.open("rb") as f:
        data = pickle.load(f)
    G0 = data["G0"]
    G1 = data["G1"]
    node_coords = data["all_nc"]
    node_list = list(G0.nodes())
    node_idx = {n: i for i, n in enumerate(node_list)}
    edge_list = list(G0.edges())
    edges_ig = [(node_idx[u], node_idx[v]) for u, v in edge_list]
    w0 = np.array([G0[u][v]["weight"] for u, v in edge_list], dtype=np.float64)
    w1 = np.array(
        [
            G1[u][v]["weight"] if G1.has_edge(u, v) else G0[u][v]["weight"]
            for u, v in edge_list
        ],
        dtype=np.float64,
    )
    graph = ig.Graph(n=len(node_list), edges=edges_ig, directed=False)
    return graph, node_idx, node_coords, w0, w1


def scenario_weights(
    base_w0: np.ndarray,
    base_w1: np.ndarray,
    neutral_mask: np.ndarray,
    scenario: dict,
    median_unpaved_v_normal: float,
) -> tuple[np.ndarray, np.ndarray]:
    w0 = base_w0.copy()
    w1 = base_w1.copy()
    if scenario["scenario"] == "default_web1":
        return w0, w1

    scale_to_80 = median_unpaved_v_normal / 80.0
    w0[neutral_mask] = base_w0[neutral_mask] * scale_to_80
    w1[neutral_mask] = w0[neutral_mask] * float(scenario["neutral_extreme_multiplier"])
    return w0, w1


def compute_od_pairs(
    graph: ig.Graph,
    city_df: pd.DataFrame,
    node_idx: dict[int, int],
    w0: np.ndarray,
    w1: np.ndarray,
) -> pd.DataFrame:
    city_df = city_df[city_df["snap_node"].isin(node_idx)].copy()
    city_idx = [node_idx[n] for n in city_df["snap_node"]]
    graph.es["weight"] = w0.tolist()
    d0 = np.array(graph.distances(source=city_idx, target=city_idx, weights="weight"))
    graph.es["weight"] = w1.tolist()
    d1 = np.array(graph.distances(source=city_idx, target=city_idx, weights="weight"))

    rows = []
    cities = city_df.reset_index(drop=True)
    for i in range(len(cities)):
        for j in range(i + 1, len(cities)):
            t0 = d0[i, j]
            t1 = d1[i, j]
            t0_ok = np.isfinite(t0) and t0 < UNREACHABLE
            t1_ok = np.isfinite(t1) and t1 < UNREACHABLE
            if not t0_ok and not t1_ok:
                conn_type = "both_unreachable"
            elif t0_ok and not t1_ok:
                conn_type = "climate_disconnected"
            elif not t0_ok and t1_ok:
                conn_type = "normal_unreachable"
            else:
                conn_type = "connected"
            inc = float("nan")
            if t0_ok and t1_ok and t0 > 0:
                inc = (t1 - t0) / t0 * 100.0
            rows.append(
                {
                    "city_A": cities.loc[i, "city_name"],
                    "city_B": cities.loc[j, "city_name"],
                    "country_A": cities.loc[i, "country_folder"],
                    "country_B": cities.loc[j, "country_folder"],
                    "t_normal_h": t0 if t0_ok else np.nan,
                    "t_extreme_h": t1 if t1_ok else np.nan,
                    "increase_pct": inc,
                    "conn_type": conn_type,
                    "cross_country": bool(
                        cities.loc[i, "country_folder"]
                        != cities.loc[j, "country_folder"]
                    ),
                }
            )
    return pd.DataFrame(rows)


def summarize_od(
    scenario: str,
    od: pd.DataFrame,
    w0: np.ndarray,
    w1: np.ndarray,
    neutral_mask: np.ndarray,
) -> dict:
    connected = od[od["conn_type"] == "connected"].copy()
    cross = connected[connected["cross_country"]]
    edge_penalty = (w1 / np.maximum(w0, 1e-12) - 1.0) * 100.0
    direct_edge_mean = float(np.nanmean(edge_penalty))
    cross_mean = float(cross["increase_pct"].mean())
    all_mean = float(connected["increase_pct"].mean())
    return {
        "scenario": scenario,
        "n_pairs": int(len(od)),
        "n_connected": int(len(connected)),
        "n_cross_country_connected": int(len(cross)),
        "cross_country_mean_increase_pct": round(cross_mean, 4),
        "all_pair_mean_increase_pct": round(all_mean, 4),
        "all_pair_median_increase_pct": round(
            float(connected["increase_pct"].median()), 4
        ),
        "pct_severe_gt50": round(float((od["increase_pct"] >= 50.0).mean() * 100), 4),
        "direct_edge_travel_penalty_pct": round(direct_edge_mean, 4),
        "amplification_proxy_cross_country": (
            round(cross_mean / direct_edge_mean, 4) if direct_edge_mean > 0 else np.nan
        ),
        "neutral_link_share_pct": round(float(neutral_mask.mean() * 100), 4),
    }


def hotspot_overlap(default_od: pd.DataFrame, scenario_od: pd.DataFrame) -> dict:
    key = ["city_A", "city_B"]
    base = default_od[default_od["conn_type"] == "connected"].copy()
    alt = scenario_od[scenario_od["conn_type"] == "connected"].copy()
    base["pair"] = list(zip(base["city_A"], base["city_B"]))
    alt["pair"] = list(zip(alt["city_A"], alt["city_B"]))
    merged = base[["pair", "increase_pct"]].merge(
        alt[["pair", "increase_pct"]],
        on="pair",
        suffixes=("_default", "_scenario"),
    )
    rho = spearmanr(
        merged["increase_pct_default"].fillna(0),
        merged["increase_pct_scenario"].fillna(0),
    ).statistic
    out = {"spearman_increase_pct": round(float(rho), 4)}
    for k in [10, 25, 50]:
        out[f"top{k}_corridor_jaccard"] = round(
            jaccard(
                top_set(merged["increase_pct_default"], k),
                top_set(merged["increase_pct_scenario"], k),
            ),
            4,
        )
    return out


def run_checkpoint_od(paths, out_dir: Path, median_unpaved_v_normal: float) -> None:
    checkpoint = paths.network_results / "africa_layer" / "graph_checkpoint.pkl"
    nodes_csv = paths.data_base / "web" / "africa_layer" / "africa_nodes.csv"
    graph, node_idx, node_coords, base_w0, base_w1 = build_igraph_from_checkpoint(
        checkpoint
    )
    neutral_mask = np.isclose(base_w0, base_w1, rtol=1e-10, atol=1e-12)
    city_df = load_snapped_cities(nodes_csv, node_coords)
    write_table(city_df, out_dir / "paved_assumption_city_snaps.csv")

    summary_rows = []
    od_by_scenario = {}
    for scenario in OD_SCENARIOS:
        label = scenario["scenario"]
        print(f"  OD scenario: {label}", flush=True)
        w0, w1 = scenario_weights(
            base_w0, base_w1, neutral_mask, scenario, median_unpaved_v_normal
        )
        od = compute_od_pairs(graph, city_df, node_idx, w0, w1)
        od["scenario"] = label
        write_table(od, out_dir / f"od_pairs_{label}.csv")
        summary_rows.append(summarize_od(label, od, w0, w1, neutral_mask))
        od_by_scenario[label] = od

    summary = pd.DataFrame(summary_rows)
    default_od = od_by_scenario["default_web1"]
    overlap_rows = []
    for label, od in od_by_scenario.items():
        overlap = hotspot_overlap(default_od, od)
        overlap_rows.append({"scenario": label, **overlap})
    overlap_df = pd.DataFrame(overlap_rows)
    write_table(summary, out_dir / "paved_assumption_od_summary.csv")
    write_table(overlap_df, out_dir / "paved_assumption_hotspot_overlap.csv")

    interp_rows = []
    default_cross = float(
        summary.loc[
            summary["scenario"] == "default_web1", "cross_country_mean_increase_pct"
        ].iloc[0]
    )
    for _, row in summary.iterrows():
        overlap = overlap_df[overlap_df["scenario"] == row["scenario"]].iloc[0]
        interp_rows.append(
            {
                "scenario": row["scenario"],
                "cross_country_mean_increase_pct": row[
                    "cross_country_mean_increase_pct"
                ],
                "change_vs_default_pp": round(
                    row["cross_country_mean_increase_pct"] - default_cross, 4
                ),
                "amplification_proxy_cross_country": row[
                    "amplification_proxy_cross_country"
                ],
                "top25_corridor_jaccard": overlap["top25_corridor_jaccard"],
                "interpretation": (
                    "stable"
                    if overlap["top25_corridor_jaccard"] >= 0.8
                    else "sensitive"
                ),
            }
        )
    write_table(pd.DataFrame(interp_rows), out_dir / "interpretation_summary.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_path_args(parser)
    parser.add_argument(
        "--run-checkpoint-od",
        action="store_true",
        help="Run OD comparison by perturbing currently climate-neutral checkpoint links.",
    )
    args = parser.parse_args()

    paths = resolve_paths(args.base_dir, args.output_dir)
    out_dir = ensure_dir(paths.output_root / "02_paved_assumptions")

    scenarios = pd.DataFrame(PAVED_SCENARIOS)
    status = speed_status(paths)
    commands = command_manifest(paths, Path.cwd())

    write_table(scenarios, out_dir / "paved_assumption_scenarios.csv")
    write_table(status, out_dir / "paved_assumption_input_status.csv")
    write_table(commands, out_dir / "paved_assumption_rerun_manifest.csv")
    median_unpaved_v_normal = float(status["median_unpaved_v_normal"].median())

    summary = pd.DataFrame(
        [
            {
                "n_countries_with_speed_csv": int(status["speed_csv_exists"].sum()),
                "median_country_unpaved_v_normal": round(median_unpaved_v_normal, 3),
                "median_country_unpaved_v_extreme": round(
                    float(status["median_unpaved_v_extreme"].median()), 3
                ),
                "status": "manifest_only_graph_rerun_required",
            }
        ]
    )
    write_table(summary, out_dir / "paved_assumption_summary.csv")

    if args.run_checkpoint_od:
        run_checkpoint_od(paths, out_dir, median_unpaved_v_normal)

    print("Paved-road assumption manifest written to:", out_dir)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
