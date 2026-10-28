"""Strict OD and physical/synthetic edge crosswalk for Pan-African C04.

This is an independent gate, not a replacement for ``run_africa_layer.py``.
It deliberately rejects old graph pickles and missing speed rows. A formal run
must rebuild both scenario graphs from the same versioned road/speed inputs.
"""

from __future__ import annotations

import math
from pathlib import Path

import networkx as nx
import pandas as pd


def validate_paper_od_nodes(nodes: pd.DataFrame, official_countries: set[str]) -> pd.DataFrame:
    """Require the paper's 49 capitals + 34 other megacities, excluding ESH.

    The archived CSV has 84 rows / 50 country folders: WestSahara is present
    there but has no road result. It must be excluded explicitly, not silently
    omitted by a failed snap or missing graph.
    """
    required = {"node_id", "name", "type", "country_folder", "iso3", "lon", "lat"}
    if required - set(nodes):
        raise ValueError(f"OD CSV lacks {sorted(required - set(nodes))}")
    if len(nodes) != 84 or (nodes["country_folder"] == "WestSahara").sum() != 1:
        raise ValueError("Archived OD source must contain 84 rows and exactly one WestSahara")
    selected = nodes[nodes["country_folder"] != "WestSahara"].copy()
    if len(selected) != 83 or len(official_countries) != 49:
        raise ValueError("Paper OD scope must be 83 nodes and 49 countries")
    if set(selected["country_folder"]) != official_countries:
        raise ValueError("OD countries disagree with the official 49-country registry")
    counts = selected["type"].value_counts().to_dict()
    if counts != {"capital": 49, "megacity": 34}:
        raise ValueError(f"Paper OD type counts disagree: {counts}")
    if selected["node_id"].isna().any() or selected["node_id"].duplicated().any():
        raise ValueError("OD node_id must be non-null and unique")
    if selected["name"].isna().any() or selected["name"].duplicated().any():
        raise ValueError("Legacy OD matrix is name-keyed; names must be unique")
    for col in ("lon", "lat"):
        val = pd.to_numeric(selected[col], errors="coerce")
        if val.isna().any() or not val.map(math.isfinite).all():
            raise ValueError(f"OD {col} is not finite")
    return selected.reset_index(drop=True)


def road_source_table(shp_path: Path, speed_path: Path, country: str) -> pd.DataFrame:
    """Join speed to original source-row IDs before any length filtering."""
    import geopandas as gpd

    roads = gpd.read_file(shp_path)
    if "road_id" not in roads:
        roads["road_id"] = [f"{country}_road_{i}" for i in range(len(roads))]
    if roads["road_id"].isna().any() or roads["road_id"].duplicated().any():
        raise ValueError(f"{country}: source road IDs are missing or duplicate")
    if "length_km" not in roads:
        roads["length_km"] = roads.to_crs("ESRI:102022").geometry.length / 1000
    speed = pd.read_csv(speed_path)
    required = {"road_id", "V_normal", "V_extreme"}
    if required - set(speed):
        raise ValueError(f"{country}: speed CSV lacks {sorted(required - set(speed))}")
    if speed["road_id"].isna().any() or speed["road_id"].duplicated().any():
        raise ValueError(f"{country}: speed IDs are missing or duplicate")
    joined = roads[["road_id", "length_km"]].merge(
        speed[["road_id", "V_normal", "V_extreme"]], on="road_id", how="left", validate="one_to_one"
    )
    return joined


def verified_speed_source_table(speed_path: Path) -> pd.DataFrame:
    """Fast path after a separate all-row shape/speed identity+length audit passes.

    A speed CSV alone is *not* provenance: callers must record the matching
    C00-style input-alignment manifest for the speed version being used.
    """
    source = pd.read_csv(speed_path, usecols=["road_id", "length_km", "V_normal", "V_extreme"])
    if source["road_id"].isna().any() or source["road_id"].duplicated().any():
        raise ValueError("Verified speed source has missing/duplicate road IDs")
    return source


def crosswalk_graph_edges(
    G0: nx.Graph, G1: nx.Graph, sources: pd.DataFrame, *, synthetic_speed_kmh: float = 40.0
) -> pd.DataFrame:
    """Return one row for every graph-selected road ID in either scenario.

    Parallel physical roads can win different scenarios. Their IDs cannot be
    inferred from node pairs alone; read each scenario's edge ``road_id``.
    Synthetic border connectors have identical weights in both scenarios and
    are marked separately so they are not misreported as weather-exposed roads.
    """
    edges0 = {frozenset((u, v)) for u, v in G0.edges}
    edges1 = {frozenset((u, v)) for u, v in G1.edges}
    if set(G0.nodes) != set(G1.nodes) or edges0 != edges1:
        raise ValueError("Normal and extreme graph topology differs")
    if not math.isfinite(synthetic_speed_kmh) or synthetic_speed_kmh <= 0:
        raise ValueError("Synthetic connector speed must be positive")
    if sources["road_id"].isna().any() or sources["road_id"].duplicated().any():
        raise ValueError("Source road IDs must be unique")
    source_lookup = sources.set_index("road_id")
    records = {}
    for graph, field in ((G0, "w0"), (G1, "w1")):
        for u, v, attrs in graph.edges(data=True):
            rid = attrs.get("road_id")
            synthetic = bool(attrs.get("synthetic", False))
            if not isinstance(rid, str) or not rid:
                raise ValueError("Graph edge lacks physical or synthetic road_id")
            if synthetic != rid.startswith("synthetic_border_"):
                raise ValueError(f"Synthetic marker/ID conflict for {rid}")
            weight = float(attrs.get("weight", math.nan))
            if not math.isfinite(weight) or weight <= 0:
                raise ValueError(f"Invalid graph {field} for {rid}")
            if rid in records and {u, v} != {records[rid]["u"], records[rid]["v"]}:
                raise ValueError(f"One road_id has conflicting endpoints: {rid}")
            if synthetic:
                if not G0.has_edge(u, v) or not G1.has_edge(u, v):
                    raise ValueError("Synthetic connector missing in a scenario")
                if G0[u][v].get("road_id") != rid or G1[u][v].get("road_id") != rid:
                    raise ValueError("Synthetic connector differs by scenario")
                w0 = float(G0[u][v]["weight"])
                w1 = float(G1[u][v]["weight"])
                if not math.isclose(w0, w1, rel_tol=1e-12, abs_tol=1e-12):
                    raise ValueError("Synthetic connector climate weight changed")
                record = {"road_id": rid, "u": u, "v": v, "length_km": w0 * synthetic_speed_kmh,
                          "w0": w0, "w1": w1, "synthetic": True}
            else:
                if rid not in source_lookup.index:
                    raise ValueError(f"Graph physical road_id missing source speed: {rid}")
                source = source_lookup.loc[rid]
                length = float(source["length_km"])
                vn = float(source["V_normal"])
                ve = float(source["V_extreme"])
                if not all(math.isfinite(x) and x > 0 for x in (length, vn, ve)):
                    raise ValueError(f"Graph physical road has invalid length/speed: {rid}")
                record = {"road_id": rid, "u": u, "v": v, "length_km": length,
                          "w0": length / vn, "w1": length / ve, "synthetic": False}
            if not math.isclose(weight, record[field], rel_tol=1e-9, abs_tol=1e-11):
                raise ValueError(f"Graph weight disagrees with source road {rid} in {field}")
            records[rid] = record
    result = pd.DataFrame.from_records(list(records.values()))
    if result.empty:
        raise ValueError("No graph-selected edges")
    return result


def classify_paper_pairs(pairs: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    """Attach country/type metadata and distinguish international pairs."""
    lookup = nodes.set_index("node_id")
    result = pairs.copy()
    for side, col in (("origin", "origin_id"), ("destination", "destination_id")):
        if not result[col].isin(lookup.index).all():
            raise ValueError(f"Unknown {side} OD ID")
        result[f"{side}_country"] = result[col].map(lookup["country_folder"])
        result[f"{side}_type"] = result[col].map(lookup["type"])
    result["international"] = result["origin_country"] != result["destination_country"]
    return result
