"""Small real-GeoPackage/Shapefile integration gate for source-row road IDs."""

import csv

import pytest


gpd = pytest.importorskip("geopandas")
from shapely.geometry import LineString

from result1.network_pipeline import build_graphs_from_shp


def test_graph_builder_keeps_source_road_ids_after_surface_filter(tmp_path):
    roads = gpd.GeoDataFrame(
        {"Surface": ["paved", "unpaved", "unpaved"]},
        geometry=[
            LineString([(10, 0), (10.02, 0)]),
            LineString([(20, 0), (20.02, 0)]),
            LineString([(30, 0), (30.02, 0)]),
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
        writer.writerow({"road_id": "Kenya_road_1", "V_normal": 10, "V_extreme": 5, "passable_rate_extreme": 1})
        writer.writerow({"road_id": "Kenya_road_2", "V_normal": 20, "V_extreme": 10, "passable_rate_extreme": 1})

    normal, _, _, edges, _ = build_graphs_from_shp(shp, speed)
    assert normal.number_of_edges() == 2
    assert set(edges["road_id"]) == {"Kenya_road_1", "Kenya_road_2"}
    assert sorted(round(value, 1) for value in edges["w0"] * 10 / edges["length_km"]) == [0.5, 1.0]
