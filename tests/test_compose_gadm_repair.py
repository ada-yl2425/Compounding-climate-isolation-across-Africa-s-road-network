"""No-GIS synthetic checks for isolated Ghana repair composition."""

import csv
import json

import pytest

from hpc.compose_gadm_repair import compose, sha256


def _fixture(tmp_path):
    original = tmp_path / "original"
    repair = tmp_path / "repair"
    rows = []
    for index in range(1, 50):
        iso = "GHA" if index == 19 else f"T{index:02d}"
        rows.append(
            {
                "array_index": index,
                "iso3": iso,
                "admin_level": 2,
                "source_rows": 1,
                "target_unique_gid": 1,
            }
        )
        directory = (repair if iso == "GHA" else original) / iso
        directory.mkdir(parents=True)
        gpkg = directory / f"gadm41_{iso}_2.gpkg"
        gpkg.write_bytes(iso.encode())
        qc = {
            "status": "PASS",
            "country": iso,
            "admin_level": 2,
            "source_rows": 1,
            "target_unique_admin_gid": 1,
            "output_file": str(gpkg.resolve()),
            "output_bytes": gpkg.stat().st_size,
            "output_sha256": sha256(gpkg),
        }
        (directory / f"gadm41_{iso}_2_qc.json").write_text(json.dumps(qc))
    registry = tmp_path / "registry.csv"
    with registry.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return registry, original, repair


def test_compose_49_links_with_explicit_ghana_producer(tmp_path):
    registry, original, repair = _fixture(tmp_path)
    composed = tmp_path / "composed"
    result = compose(registry, original, repair, composed, "old", "fix")
    assert result["status"] == "COMPOSED_PENDING_FINAL_AUDIT"
    assert result["country_count"] == 49
    assert (composed / "GHA").resolve() == (repair / "GHA").resolve()
    assert (composed / "T01").resolve() == (original / "T01").resolve()
    assert next(row for row in result["countries"] if row["iso3"] == "GHA")[
        "producer_commit"
    ] == "fix"
    with pytest.raises(FileExistsError):
        compose(registry, original, repair, composed, "old", "fix")


def test_compose_fails_closed_before_creating_links_on_missing_country(tmp_path):
    registry, original, repair = _fixture(tmp_path)
    (original / "T48/gadm41_T48_2.gpkg").unlink()
    composed = tmp_path / "composed"
    with pytest.raises(FileNotFoundError):
        compose(registry, original, repair, composed, "old", "fix")
    assert not composed.exists()


def test_compose_rejects_tampered_ghana_output(tmp_path):
    registry, original, repair = _fixture(tmp_path)
    with (repair / "GHA/gadm41_GHA_2.gpkg").open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="GHA"):
        compose(registry, original, repair, tmp_path / "composed", "old", "fix")
