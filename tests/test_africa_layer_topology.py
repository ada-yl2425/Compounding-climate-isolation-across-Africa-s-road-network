"""Pan-African country graph must share the road identity/topology invariants."""

import csv

import numpy as np
import pytest


def test_africa_endpoint_merging_preserves_each_physical_road():
    pytest.importorskip("igraph")
    from result1.run_africa_layer import _merge_endpoints

    points = np.array([[0.0, 0.0], [0.006, 0.0],
                       [0.003, 0.0], [0.003, 0.0001]])
    node_ids, _ = _merge_endpoints(points, {(0, 1), (2, 3)}, 0.0045)
    assert node_ids[0] != node_ids[1]
    assert node_ids[2] != node_ids[3]


def test_africa_country_graph_selects_parallel_roads_per_scenario(tmp_path, monkeypatch):
    pytest.importorskip("igraph")
    geopandas = pytest.importorskip("geopandas")
    from shapely.geometry import LineString
    from result1 import run_africa_layer as africa

    roads = tmp_path / "roads" / "Kenya"
    roads.mkdir(parents=True)
    speeds = tmp_path / "speeds"
    speeds.mkdir()
    gdf = geopandas.GeoDataFrame(
        {"Surface": ["unpaved", "unpaved"]},
        geometry=[LineString([(10, 0), (10.02, 0)]),
                  LineString([(10, 0), (10.02, 0.001), (10.02, 0)])],
        crs="EPSG:4326",
    )
    gdf.to_file(roads / "Kenya.shp")
    with (speeds / "Kenya_road_speed.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=(
            "road_id", "V_normal", "V_extreme", "passable_rate_extreme"
        ))
        writer.writeheader()
        writer.writerow({"road_id": "Kenya_road_0", "V_normal": 100,
                         "V_extreme": 5, "passable_rate_extreme": 1})
        writer.writerow({"road_id": "Kenya_road_1", "V_normal": 10,
                         "V_extreme": 50, "passable_rate_extreme": 1})
    monkeypatch.setattr(africa, "ROADS_DIR", tmp_path / "roads")
    monkeypatch.setattr(africa, "SPEED_DIR", speeds)
    result = africa.build_country_graph("Kenya", 0)
    assert result is not None
    G0, G1, _, _ = result
    assert G0.number_of_edges() == 1
    assert G1.number_of_edges() == 1
    assert G0[0][1]["road_id"] == "Kenya_road_0"
    assert G1[0][1]["road_id"] == "Kenya_road_1"
