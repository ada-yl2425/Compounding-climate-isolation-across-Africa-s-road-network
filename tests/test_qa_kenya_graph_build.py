"""Pure unit tests for graph/table consistency diagnostics."""

import csv

import networkx as nx
import pandas as pd
import pytest

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
    extreme.add_edge(1, 2, road_id="first", weight=5.0)
    connectivity.add_edge(1, 2)
    table = pd.DataFrame([{"u": 1, "v": 2, "road_id": "first", "w0": 3.0, "w1": 5.0}])
    result = audit_graph(normal, extreme, connectivity, table, {"first"})
    assert result["edge_table_matches_route_graph"]


def test_real_builder_reports_stale_table_after_parallel_edge_update(tmp_path):
    geopandas = pytest.importorskip("geopandas")
    from shapely.geometry import LineString

    from result1.network_pipeline import build_graphs_from_shp

    roads = geopandas.GeoDataFrame(
        {"Surface": ["unpaved", "unpaved"]},
        geometry=[
            LineString([(10, 0), (10.02, 0)]),
            LineString([(10, 0), (10.01, 0.001), (10.02, 0)]),
        ],
        crs="EPSG:4326",
    )
    shp = tmp_path / "Kenya.shp"
    roads.to_file(shp)
    speed = tmp_path / "Kenya_road_speed.csv"
    with speed.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=(
            "road_id", "V_normal", "V_extreme", "passable_rate_extreme"
        ))
        writer.writeheader()
        writer.writerow({"road_id": "Kenya_road_0", "V_normal": 10,
                         "V_extreme": 5, "passable_rate_extreme": 1})
        writer.writerow({"road_id": "Kenya_road_1", "V_normal": 100,
                         "V_extreme": 50, "passable_rate_extreme": 1})
    normal, extreme, connectivity, table, _ = build_graphs_from_shp(shp, speed)
    result = audit_graph(normal, extreme, connectivity, table,
                         {"Kenya_road_0", "Kenya_road_1"})
    assert result["route_edges"] == 1
    assert result["edge_table_rows"] == 2
    assert result["parallel_physical_edges"] == 1
    assert result["edge_table_matches_route_graph"]
    assert normal[0][1]["road_id"] == "Kenya_road_1"
    assert extreme[0][1]["road_id"] == "Kenya_road_1"


def test_parallel_projection_can_choose_different_road_in_each_scenario(tmp_path):
    geopandas = pytest.importorskip("geopandas")
    from shapely.geometry import LineString

    from result1.network_pipeline import build_graphs_from_shp

    roads = geopandas.GeoDataFrame(
        {"Surface": ["unpaved", "unpaved"]},
        geometry=[LineString([(10, 0), (10.02, 0)]),
                  LineString([(10, 0), (10.02, 0.001), (10.02, 0)])],
        crs="EPSG:4326",
    )
    shp = tmp_path / "Kenya.shp"
    roads.to_file(shp)
    speed = tmp_path / "Kenya_road_speed.csv"
    with speed.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=(
            "road_id", "V_normal", "V_extreme", "passable_rate_extreme"
        ))
        writer.writeheader()
        writer.writerow({"road_id": "Kenya_road_0", "V_normal": 100,
                         "V_extreme": 5, "passable_rate_extreme": 1})
        writer.writerow({"road_id": "Kenya_road_1", "V_normal": 10,
                         "V_extreme": 50, "passable_rate_extreme": 1})
    normal, extreme, connectivity, table, _ = build_graphs_from_shp(shp, speed)
    assert len(table) == 2
    assert normal[0][1]["road_id"] == "Kenya_road_0"
    assert extreme[0][1]["road_id"] == "Kenya_road_1"
    assert audit_graph(normal, extreme, connectivity, table,
                       {"Kenya_road_0", "Kenya_road_1"})["edge_table_matches_route_graph"]
