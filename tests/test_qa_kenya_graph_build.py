"""Pure unit tests for graph/table consistency diagnostics."""

import networkx as nx
import pandas as pd

from hpc.qa_kenya_graph_build import audit_graph, parse_build_counts


def test_parse_build_counts_for_parallel_collapses():
    log = "Filtered segments: 10,000\n  IRI Match=100.0%  Fill=0  Skip=5\n"
    assert parse_build_counts(log, 9990) == {
        "filtered_unpaved_segments": 10000,
        "skipped_geometry_or_selfloop_segments": 5,
        "speed_fill_segments": 0,
        "candidate_road_segments": 9995,
        "parallel_segments_collapsed": 5,
    }


def test_audit_detects_collapsed_parallel_edge_table_staleness():
    normal, extreme, connectivity = nx.Graph(), nx.Graph(), nx.Graph()
    normal.add_edge(1, 2, road_id="second", weight=1.0)
    extreme.add_edge(1, 2, weight=2.0)
    connectivity.add_edge(1, 2)
    table = pd.DataFrame([{"u": 1, "v": 2, "road_id": "first", "w0": 3.0, "w1": 5.0}])
    result = audit_graph(normal, extreme, connectivity, table, {"first", "second"})
    assert result["normal_graph_table_road_id_mismatch"] == 1
    assert result["normal_graph_table_weight_mismatch"] == 1
    assert result["extreme_graph_table_weight_mismatch"] == 1
    assert not result["edge_table_matches_route_graph"]


def test_audit_accepts_matching_edge_table():
    normal, extreme, connectivity = nx.Graph(), nx.Graph(), nx.Graph()
    normal.add_edge(1, 2, road_id="first", weight=3.0)
    extreme.add_edge(1, 2, weight=5.0)
    connectivity.add_edge(1, 2)
    table = pd.DataFrame([{"u": 1, "v": 2, "road_id": "first", "w0": 3.0, "w1": 5.0}])
    result = audit_graph(normal, extreme, connectivity, table, {"first"})
    assert result["edge_table_matches_route_graph"]
