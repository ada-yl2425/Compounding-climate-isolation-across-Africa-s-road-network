import csv
import json

from hpc.finalize_road_speed_alignment import finalize


def _registry(path):
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=("archive_country", "speed_country"))
        writer.writeheader()
        writer.writerow({"archive_country": "Kenya", "speed_country": "Kenya"})


def test_missing_country_qc_is_fail(tmp_path):
    registry = tmp_path / "registry.csv"
    _registry(registry)
    result = finalize(registry, tmp_path / "results", expected_count=1)
    assert result["status"] == "FAIL"
    assert result["failures"] == ["missing QC: Kenya"]


def test_good_qc_is_pass(tmp_path):
    registry = tmp_path / "registry.csv"
    _registry(registry)
    path = tmp_path / "results" / "admin_units" / "Kenya" / "road_speed_alignment_qc.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "status": "PASS", "country": "Kenya", "matched_ids": 2,
        "expected_speed_rows": 2, "speed_rows": 2, "source_features": 3,
        "duplicate_id_rows": 0, "malformed_id_rows": 0,
        "missing_speed_ids": 0, "extra_speed_ids": 0,
        "geometry_mismatch_rows": 0, "invalid_geometry_rows": 0,
        "speed_surface_mismatch_rows": 0,
    }))
    result = finalize(registry, tmp_path / "results", expected_count=1)
    assert result["status"] == "PASS"
    assert result["total_matched_ids"] == 2
