import csv

import pytest

from hpc.audit_road_speed_alignment import (
    close_enough,
    is_unpaved,
    load_speed_rows,
    source_road_id,
)


def test_road_identity_and_filter_rule():
    assert source_road_id("Kenya", 8) == "Kenya_road_8"
    assert is_unpaved("unpaved")
    assert is_unpaved("Partly unpaved")
    assert not is_unpaved("paved")
    assert not is_unpaved(None)
    with pytest.raises(ValueError):
        source_road_id("Kenya", -1)


def test_speed_loader_finds_duplicates_and_wrong_country(tmp_path):
    path = tmp_path / "speed.csv"
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=(
            "road_id", "Surface", "length_km", "center_lon", "center_lat"
        ))
        writer.writeheader()
        writer.writerow({"road_id": "Kenya_road_8", "Surface": "unpaved", "length_km": 1, "center_lon": 37, "center_lat": -1})
        writer.writerow({"road_id": "Kenya_road_8", "Surface": "unpaved", "length_km": 1, "center_lon": 37, "center_lat": -1})
        writer.writerow({"road_id": "Uganda_road_1", "Surface": "unpaved", "length_km": 1, "center_lon": 37, "center_lat": -1})
    rows, stats = load_speed_rows(path, "Kenya")
    assert len(rows) == 2
    assert stats["duplicate_id_examples"] == ["Kenya_road_8"]
    assert stats["malformed_id_rows"] == 1


def test_geometry_comparison_is_strict_and_finite():
    assert close_enough(1.0 + 1e-9, 1.0, absolute_tolerance=1e-6)
    assert not close_enough(1.1, 1.0, absolute_tolerance=1e-6)
    assert not close_enough(float("nan"), 1.0, absolute_tolerance=1e-6)
