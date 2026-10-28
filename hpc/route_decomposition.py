"""Auditable fixed-physical-road versus rerouted OD travel-time decomposition.

The baseline route is a sequence of *road IDs*, not merely a sequence of
vertices: parallel roads can have different normal and extreme winners.
All times are hours when input edge weights are length_km / speed_kmh.
"""

from __future__ import annotations

import math

import networkx as nx
import pandas as pd


def _edge_lookup(df_edges: pd.DataFrame) -> dict:
    required = {"road_id", "u", "v", "w0", "w1", "length_km"}
    missing = required - set(df_edges.columns)
    if missing:
        raise ValueError(f"Physical edge table missing fields: {sorted(missing)}")
    if df_edges["road_id"].isna().any() or df_edges["road_id"].duplicated().any():
        raise ValueError("Physical road_id must be non-null and unique")
    for field in ("w0", "w1", "length_km"):
        values = pd.to_numeric(df_edges[field], errors="coerce")
        if values.isna().any() or not values.map(lambda x: math.isfinite(x) and x > 0).all():
            raise ValueError(f"Physical {field} must be finite and strictly positive")
    return df_edges.set_index("road_id").to_dict("index")


def _check_graph(G: nx.Graph, lookup: dict, weight_field: str) -> None:
    for u, v, attrs in G.edges(data=True):
        rid = attrs.get("road_id")
        if rid not in lookup:
            raise ValueError(f"Graph {weight_field} road_id missing from edge table: {rid}")
        row = lookup[rid]
        if {u, v} != {row["u"], row["v"]}:
            raise ValueError(f"Graph endpoints disagree with road_id {rid}")
        if not math.isclose(float(attrs.get("weight", math.nan)), float(row[weight_field]), rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError(f"Graph {weight_field} disagrees with road_id {rid}")


def _path_from_predecessors(predecessors: dict, source, target) -> list:
    path = [target]
    while path[-1] != source:
        parents = predecessors.get(path[-1])
        if not parents:
            raise ValueError("Dijkstra predecessor chain is broken")
        path.append(parents[0])
    path.reverse()
    return path


def decompose_od_routes(
    G0: nx.Graph,
    G1: nx.Graph,
    df_edges: pd.DataFrame,
    origins: list[dict],
    destinations: list[dict] | None = None,
) -> pd.DataFrame:
    """Return one row per distinct OD, with exact baseline physical-road IDs.

    Each OD record needs ``id`` and ``node``. With one shared list, unordered
    pairs are emitted once; with separate lists, all non-identical pairs are
    emitted. Disconnected and zero-distance pairs receive explicit statuses.
    """
    lookup = _edge_lookup(df_edges)
    _check_graph(G0, lookup, "w0")
    _check_graph(G1, lookup, "w1")
    if destinations is None:
        destinations = origins
        same_set = True
    else:
        same_set = False
    ids = [record["id"] for record in origins]
    if len(ids) != len(set(ids)):
        raise ValueError("Origin IDs must be unique")
    records = []
    for i, origin in enumerate(origins):
        source = origin["node"]
        if source in G0:
            predecessors, dist0 = nx.dijkstra_predecessor_and_distance(G0, source, weight="weight")
        else:
            predecessors, dist0 = {}, {}
        dist1 = nx.single_source_dijkstra_path_length(G1, source, weight="weight") if source in G1 else {}
        for j, dest in enumerate(destinations):
            if (same_set and j <= i) or (not same_set and dest["id"] == origin["id"]):
                continue
            target = dest["node"]
            base = dist0.get(target)
            rerouted = dist1.get(target)
            row = {
                "origin_id": origin["id"],
                "destination_id": dest["id"],
                "origin_node": source,
                "destination_node": target,
                "status": "connected",
                "t_baseline_h": base,
                "t_fixed_extreme_h": None,
                "t_rerouted_extreme_h": rerouted,
                "direct_path_increase_pct": None,
                "rerouting_relief_pct_of_fixed": None,
                "baseline_path_length_km": None,
                "baseline_path_speed_normal_kmh": None,
                "baseline_path_speed_extreme_kmh": None,
                "baseline_path_speed_reduction_pct": None,
                "baseline_path_mean_segment_speed_reduction_pct": None,
                "baseline_path_road_ids": None,
            }
            if base is None:
                row["status"] = "baseline_unreachable"
            elif base == 0:
                row["status"] = "same_snapped_node"
            else:
                path = _path_from_predecessors(predecessors, source, target)
                road_ids = [G0[u][v]["road_id"] for u, v in zip(path[:-1], path[1:])]
                fixed = sum(float(lookup[rid]["w1"]) for rid in road_ids)
                baseline_exact = sum(float(lookup[rid]["w0"]) for rid in road_ids)
                if not math.isclose(base, baseline_exact, rel_tol=1e-9, abs_tol=1e-10):
                    raise ValueError("Baseline shortest path and physical road weights disagree")
                if rerouted is None:
                    row["status"] = "extreme_unreachable"
                elif rerouted > fixed and not math.isclose(rerouted, fixed, rel_tol=1e-9, abs_tol=1e-10):
                    raise ValueError("Rerouted path cannot cost more than the fixed baseline path")
                route_length = sum(float(lookup[rid]["length_km"]) for rid in road_ids)
                segment_reductions = [
                    1 - float(lookup[rid]["w0"]) / float(lookup[rid]["w1"])
                    for rid in road_ids
                ]
                row.update(
                    t_fixed_extreme_h=fixed,
                    direct_path_increase_pct=100 * (fixed / base - 1),
                    rerouting_relief_pct_of_fixed=(100 * (fixed - rerouted) / fixed if rerouted is not None else None),
                    baseline_path_length_km=route_length,
                    baseline_path_speed_normal_kmh=route_length / base,
                    baseline_path_speed_extreme_kmh=route_length / fixed,
                    baseline_path_speed_reduction_pct=100 * (1 - base / fixed),
                    baseline_path_mean_segment_speed_reduction_pct=100 * sum(segment_reductions) / len(segment_reductions),
                    baseline_path_road_ids=road_ids,
                )
            records.append(row)
    return pd.DataFrame.from_records(records)
