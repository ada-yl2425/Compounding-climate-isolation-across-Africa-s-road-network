"""Pan-Africa C04 gates must preserve paper OD and physical edge identities."""

from __future__ import annotations

import networkx as nx
import pandas as pd
import pytest

from hpc.pan_africa_route_gate import (
    annotate_physical_path_exposure,
    classify_paper_pairs,
    crosswalk_graph_edges,
    validate_paper_od_nodes,
)
from hpc.route_decomposition import decompose_od_routes


def _mini_graphs():
    normal, extreme = nx.Graph(), nx.Graph()
    for graph in (normal, extreme):
        graph.add_nodes_from([0, 1, 2])
    normal.add_edge(0, 1, road_id="A_road_0", weight=1.0)
    extreme.add_edge(0, 1, road_id="A_road_1", weight=1.5)
    for graph in (normal, extreme):
        graph.add_edge(1, 2, road_id="synthetic_border_1_2", weight=0.25, synthetic=True)
    sources = pd.DataFrame([
        {"road_id": "A_road_0", "length_km": 10.0, "V_normal": 10.0, "V_extreme": 2.0},
        {"road_id": "A_road_1", "length_km": 15.0, "V_normal": 5.0, "V_extreme": 10.0},
    ])
    return normal, extreme, sources


def test_scenario_specific_parallel_road_crosswalk_and_fixed_route():
    normal, extreme, sources = _mini_graphs()
    table = crosswalk_graph_edges(normal, extreme, sources)
    assert len(table) == 3
    assert table.set_index("road_id").loc["A_road_0", "w1"] == 5.0
    assert table.set_index("road_id").loc["A_road_1", "w0"] == 3.0
    synthetic = table[table["synthetic"]].iloc[0]
    assert synthetic["length_km"] == 10.0
    pairs = decompose_od_routes(normal, extreme, table, [{"id": "a", "node": 0}, {"id": "b", "node": 2}])
    assert len(pairs) == 1
    row = pairs.iloc[0]
    assert row["baseline_path_road_ids"] == ["A_road_0", "synthetic_border_1_2"]
    assert row["t_baseline_h"] == 1.25
    assert row["t_fixed_extreme_h"] == 5.25
    assert row["t_rerouted_extreme_h"] == 1.75
    enriched = annotate_physical_path_exposure(pairs, table).iloc[0]
    assert enriched["baseline_physical_length_km"] == 10.0
    assert enriched["baseline_synthetic_length_km"] == 10.0
    assert enriched["baseline_synthetic_normal_time_h"] == 0.25
    assert enriched["baseline_physical_speed_reduction_pct"] == 80.0


def test_crosswalk_rejects_stale_or_unmatched_speed():
    normal, extreme, sources = _mini_graphs()
    with pytest.raises(ValueError, match="missing source speed"):
        crosswalk_graph_edges(normal, extreme, sources.iloc[1:])
    normal[0][1]["weight"] = 2.0
    with pytest.raises(ValueError, match="Graph weight disagrees"):
        crosswalk_graph_edges(normal, extreme, sources)


def test_crosswalk_rejects_synthetic_climate_penalty():
    normal, extreme, sources = _mini_graphs()
    extreme[1][2]["weight"] = 0.5
    with pytest.raises(ValueError, match="Synthetic connector climate weight changed"):
        crosswalk_graph_edges(normal, extreme, sources)


def test_paper_od_excludes_only_west_sahara_and_classifies_international():
    countries = {f"C{i:02d}" for i in range(49)}
    rows = []
    for i, country in enumerate(sorted(countries)):
        rows.append({"node_id": f"{country}_capital", "name": f"City{i}", "type": "capital",
                     "country_folder": country, "iso3": country, "lon": i, "lat": 0})
    for i in range(34):
        rows.append({"node_id": f"mega{i}", "name": f"Mega{i}", "type": "megacity",
                     "country_folder": f"C{i:02d}", "iso3": f"C{i:02d}", "lon": i, "lat": 1})
    rows.append({"node_id": "ESH_capital", "name": "Bir Lehlou", "type": "capital",
                 "country_folder": "WestSahara", "iso3": "ESH", "lon": -9, "lat": 26})
    selected = validate_paper_od_nodes(pd.DataFrame(rows), countries)
    assert len(selected) == 83
    pairs = classify_paper_pairs(pd.DataFrame([
        {"origin_id": "C00_capital", "destination_id": "mega0"},
        {"origin_id": "C00_capital", "destination_id": "C01_capital"},
    ]), selected)
    assert pairs["international"].tolist() == [False, True]
    with pytest.raises(ValueError, match="83 nodes"):
        validate_paper_od_nodes(pd.DataFrame(rows), set(list(countries)[:48]))
