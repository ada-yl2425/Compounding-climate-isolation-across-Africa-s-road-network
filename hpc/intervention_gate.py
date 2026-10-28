"""Preflight checks for reviewer C10--C12 intervention calculations.

This module does not recompute the paper's metrics. It rejects graph/edge
combinations that cannot support physical-road bridge, percolation, or
road-length interpretations.
"""

from __future__ import annotations

from collections import Counter

import networkx as nx
import pandas as pd


REQUIRED_ROAD_COLUMNS = {"road_id", "u", "v", "w0", "w1", "length_km"}


def _pair(u, v):
    return (u, v) if u <= v else (v, u)


def audit_physical_road_projection(
    physical_roads: pd.DataFrame,
    normal_graph: nx.Graph,
    extreme_graph: nx.Graph,
    connectivity_graph: nx.Graph,
    *,
    atol: float = 1e-10,
) -> dict:
    """Compare simple routing projections with all physical road segments.

    Parallel physical roads may remain in ``physical_roads`` while routing
    graphs use their minimum-weight projection. That is valid for shortest
    paths, but not by itself for a per-road bridge/percolation denominator.
    """

    missing = REQUIRED_ROAD_COLUMNS - set(physical_roads.columns)
    if missing:
        raise ValueError(f"Missing physical road columns: {sorted(missing)}")
    if physical_roads["road_id"].isna().any() or physical_roads["road_id"].duplicated().any():
        raise ValueError("Physical road IDs must be present and unique")
    if (physical_roads["u"] == physical_roads["v"]).any():
        raise ValueError("Physical road table contains snapped self-loops")
    if (physical_roads[["w0", "w1", "length_km"]] <= 0).any().any():
        raise ValueError("Road travel weights and lengths must be positive")

    grouped: dict[tuple, list] = {}
    for row in physical_roads.itertuples(index=False):
        grouped.setdefault(_pair(row.u, row.v), []).append(row)

    pair_counts = Counter({pair: len(rows) for pair, rows in grouped.items()})
    normal_weight_mismatches = []
    extreme_weight_mismatches = []
    missing_graph_pairs = []
    selected_id_mismatches = []
    for (u, v), rows in grouped.items():
        if not all(g.has_edge(u, v) for g in (normal_graph, extreme_graph, connectivity_graph)):
            missing_graph_pairs.append((u, v))
            continue
        best0 = min(rows, key=lambda row: row.w0)
        best1 = min(rows, key=lambda row: row.w1)
        if abs(float(normal_graph[u][v]["weight"]) - best0.w0) > atol:
            normal_weight_mismatches.append((u, v))
        if abs(float(extreme_graph[u][v]["weight"]) - best1.w1) > atol:
            extreme_weight_mismatches.append((u, v))
        for graph, best, label in (
            (normal_graph, best0, "normal"),
            (extreme_graph, best1, "extreme"),
        ):
            if "road_id" in graph[u][v] and graph[u][v]["road_id"] != best.road_id:
                selected_id_mismatches.append((label, u, v))

    graph_pairs = {_pair(u, v) for u, v in connectivity_graph.edges()}
    extra_graph_pairs = sorted(graph_pairs - grouped.keys())
    projected_bridges = {_pair(u, v) for u, v in nx.bridges(connectivity_graph)}
    false_physical_bridges = sorted(pair for pair in projected_bridges if pair_counts[pair] > 1)
    parallel_pairs = sum(count > 1 for count in pair_counts.values())
    collapsed_roads = sum(count - 1 for count in pair_counts.values() if count > 1)
    return {
        "n_physical_roads": len(physical_roads),
        "n_unique_endpoint_pairs": len(grouped),
        "n_parallel_pairs": parallel_pairs,
        "n_collapsed_roads": collapsed_roads,
        "n_false_physical_bridges_if_simple_graph": len(false_physical_bridges),
        "false_physical_bridge_pairs": false_physical_bridges,
        "normal_weight_mismatches": normal_weight_mismatches,
        "extreme_weight_mismatches": extreme_weight_mismatches,
        "selected_id_mismatches": selected_id_mismatches,
        "missing_graph_pairs": missing_graph_pairs,
        "extra_graph_pairs": extra_graph_pairs,
        "routing_projection_pass": not (
            normal_weight_mismatches
            or extreme_weight_mismatches
            or selected_id_mismatches
            or missing_graph_pairs
        ),
        "physical_bridge_and_percolation_pass": collapsed_roads == 0 and not extra_graph_pairs,
    }


def summarize_selected_road_lengths(
    physical_roads: pd.DataFrame, selected_road_ids: list[str]
) -> dict:
    """Compute C11 length from exact selected *physical* IDs, never (u, v)."""

    if not {"road_id", "length_km"}.issubset(physical_roads.columns):
        raise ValueError("road_id and length_km are required")
    if physical_roads["road_id"].duplicated().any():
        raise ValueError("Physical road IDs are not unique")
    if len(set(selected_road_ids)) != len(selected_road_ids):
        raise ValueError("Selected road IDs contain duplicates")
    indexed = physical_roads.set_index("road_id")
    missing = sorted(set(selected_road_ids) - set(indexed.index))
    if missing:
        raise ValueError(f"Selected road IDs missing from physical inventory: {missing[:5]}")
    lengths = indexed.loc[selected_road_ids, "length_km"].astype(float)
    if lengths.isna().any() or (lengths <= 0).any():
        raise ValueError("Selected physical roads have missing/nonpositive length")
    return {
        "n_roads": len(selected_road_ids),
        "total_length_km": float(lengths.sum()),
        "mean_length_km": float(lengths.mean()) if len(lengths) else 0.0,
        "median_length_km": float(lengths.median()) if len(lengths) else 0.0,
    }


def projected_weights_after_restoration(
    physical_roads: pd.DataFrame, selected_road_ids: list[str]
) -> dict[tuple, float]:
    """Project physical-road restoration to route-pair weights.

    This models the paper's idealized operation, ``selected w1 <- w0``.
    Other parallel roads retain their extreme weight; the route-pair weight
    is then the minimum of *all* available physical roads.
    """

    if not REQUIRED_ROAD_COLUMNS.issubset(physical_roads.columns):
        raise ValueError("Physical road inventory lacks required columns")
    if physical_roads["road_id"].duplicated().any():
        raise ValueError("Physical road IDs are not unique")
    selected = set(selected_road_ids)
    missing = selected - set(physical_roads["road_id"])
    if missing:
        raise ValueError(f"Selected road IDs missing from physical inventory: {sorted(missing)[:5]}")
    projected: dict[tuple, float] = {}
    for row in physical_roads.itertuples(index=False):
        pair = _pair(row.u, row.v)
        weight = float(row.w0 if row.road_id in selected else row.w1)
        projected[pair] = min(projected.get(pair, float("inf")), weight)
    return projected
