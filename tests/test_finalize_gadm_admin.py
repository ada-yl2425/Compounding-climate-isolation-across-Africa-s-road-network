"""Synthetic end-to-end gates for the 49-country GADM finalizer."""

import csv
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from hpc.finalize_gadm_admin import _check_gpkg, audit_outputs, finalize, sha256


def _gpkg(path: Path, iso: str, level: int, gid: str, source_rows: int):
    layer = f"gadm41_{iso}_{level}"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE gpkg_contents(table_name TEXT,data_type TEXT,srs_id INTEGER)"
    )
    connection.execute(
        "CREATE TABLE gpkg_geometry_columns(table_name TEXT,column_name TEXT,geometry_type_name TEXT,srs_id INTEGER)"
    )
    connection.execute(
        "INSERT INTO gpkg_contents VALUES(?,?,?)", (layer, "features", 4326)
    )
    connection.execute(
        "INSERT INTO gpkg_geometry_columns VALUES(?,?,?,?)",
        (layer, "geom", "MULTIPOLYGON", 4326),
    )
    connection.execute(
        f'CREATE TABLE "{layer}"(admin_gid TEXT,admin_level INTEGER,GID_0 TEXT,GID_1 TEXT,GID_2 TEXT,source_rows INTEGER,geom BLOB)'
    )
    connection.execute(
        f'INSERT INTO "{layer}" VALUES(?,?,?,?,?,?,?)',
        (
            gid,
            level,
            iso,
            gid if level == 1 else f"{iso}.1_1",
            gid if level == 2 else "",
            source_rows,
            b"geometry-tested-by-country-qc",
        ),
    )
    connection.commit()
    connection.close()


def _fixture(tmp_path: Path):
    source = tmp_path / "gadm_410.gpkg"
    source.write_bytes(b"immutable-source-fixture")
    registry = tmp_path / "registry.csv"
    registry_rows = [
        {
            "array_index": 1,
            "country_folder": "Kenya",
            "iso3": "KEN",
            "admin_level": 2,
            "source_rows": 2,
            "target_unique_gid": 1,
            "status": "READY",
        },
        {
            "array_index": 2,
            "country_folder": "Lesotho",
            "iso3": "LSO",
            "admin_level": 1,
            "source_rows": 1,
            "target_unique_gid": 1,
            "status": "READY",
        },
    ]
    with registry.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=registry_rows[0].keys())
        writer.writeheader()
        writer.writerows(registry_rows)
    preflight = tmp_path / "registry_manifest.json"
    preflight.write_text(
        json.dumps(
            {
                "status": "PASS",
                "formal_country_count": 2,
                "registry_sha256": sha256(registry),
                "source_file": str(source.resolve()),
                "source_layer": "gadm_410",
                "source_bytes": source.stat().st_size,
                "source_sha256": sha256(source),
            }
        ),
        encoding="utf-8",
    )
    root = tmp_path / "outputs"
    for iso, level, gid, n in (("KEN", 2, "KEN.1.1_1", 2), ("LSO", 1, "LSO.1_1", 1)):
        folder = root / iso
        folder.mkdir(parents=True)
        output = folder / f"gadm41_{iso}_{level}.gpkg"
        report = folder / f"gadm41_{iso}_{level}_qc.json"
        _gpkg(output, iso, level, gid, n)
        qc = {
            "status": "PASS",
            "country": iso,
            "admin_level": level,
            "source_rows": n,
            "target_unique_admin_gid": 1,
            "source_unique_admin_gid": 1,
            "source_file": str(source.resolve()),
            "source_layer": "gadm_410",
            "output_file": str(output.resolve()),
            "output_layer": f"gadm41_{iso}_{level}",
            "output_bytes": output.stat().st_size,
            "output_sha256": sha256(output),
            "source_crs": "EPSG:4326",
            "output_crs": "EPSG:4326",
            "area_tolerance_km2": 0.05,
            "area_delta_km2": 0.0,
            "symmetric_difference_km2": 0.0,
            "source_overlap_km2": 0.0,
            "target_overlap_km2": 0.0,
        }
        report.write_text(json.dumps(qc), encoding="utf-8")
    return registry, preflight, source, root


def test_complete_country_set_passes_and_writes_small_summary(tmp_path):
    registry, preflight, source, root = _fixture(tmp_path)
    manifest_path = tmp_path / "final.json"
    summary_path = tmp_path / "summary.csv"
    result = finalize(
        registry, preflight, source, root, manifest_path, summary_path, expected_count=2
    )
    assert result["status"] == "PASS"
    assert result["passed_country_count"] == 2
    assert result["target_features_total_passed"] == 2
    assert summary_path.exists()
    with summary_path.open(newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 2


def test_missing_output_is_fail_without_pass_summary(tmp_path):
    registry, preflight, source, root = _fixture(tmp_path)
    (root / "LSO/gadm41_LSO_1.gpkg").unlink()
    summary_path = tmp_path / "summary.csv"
    result = finalize(
        registry,
        preflight,
        source,
        root,
        tmp_path / "final.json",
        summary_path,
        expected_count=2,
    )
    assert result["status"] == "FAIL"
    assert result["passed_country_count"] == 1
    assert not summary_path.exists()


def test_tampered_gpkg_and_qc_are_rejected(tmp_path):
    registry, preflight, source, root = _fixture(tmp_path)
    output = root / "KEN/gadm41_KEN_2.gpkg"
    with output.open("ab") as handle:
        handle.write(b"tamper")
    manifest, _rows = audit_outputs(registry, preflight, source, root, expected_count=2)
    assert manifest["status"] == "FAIL"
    assert any(item["iso3"] == "KEN" for item in manifest["failures"])


def test_wrong_country_or_gid_count_is_rejected(tmp_path):
    registry, preflight, source, root = _fixture(tmp_path)
    output = root / "KEN/gadm41_KEN_2.gpkg"
    connection = sqlite3.connect(output)
    connection.execute('UPDATE "gadm41_KEN_2" SET GID_0="UGA"')
    connection.commit()
    connection.close()
    qc_path = root / "KEN/gadm41_KEN_2_qc.json"
    qc = json.loads(qc_path.read_text(encoding="utf-8"))
    qc["output_bytes"] = output.stat().st_size
    qc["output_sha256"] = sha256(output)
    qc_path.write_text(json.dumps(qc), encoding="utf-8")
    manifest, _rows = audit_outputs(registry, preflight, source, root, expected_count=2)
    assert manifest["status"] == "FAIL"
    assert any(item["iso3"] == "KEN" for item in manifest["failures"])


def test_submission_entry_uses_scheduler_afterok():
    source = Path("hpc/submit_gadm_finalize_afterok.sh").read_text(encoding="utf-8")
    assert "depend=afterok:$array_job_id" in source
    assert "qsub -W" in source


def test_generic_gpkg_geometry_metadata_requires_actual_polygons(tmp_path):
    gpd = pytest.importorskip("geopandas")
    pytest.importorskip("shapely", minversion="2.0")
    from shapely.geometry import LineString, MultiPolygon, box

    layer = "gadm41_KEN_2"
    path = tmp_path / "mixed_polygons.gpkg"
    records = {
        "admin_gid": ["KEN.1.1_1", "KEN.1.2_1"],
        "admin_level": [2, 2],
        "GID_0": ["KEN", "KEN"],
        "GID_1": ["KEN.1_1", "KEN.1_1"],
        "GID_2": ["KEN.1.1_1", "KEN.1.2_1"],
        "source_rows": [1, 1],
    }
    geometries = [box(0, 0, 1, 1), MultiPolygon([box(2, 0, 3, 1)])]
    frame = gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")
    frame.to_file(path, layer=layer, driver="GPKG", index=False)
    with sqlite3.connect(path) as connection:
        declared = connection.execute(
            "SELECT geometry_type_name FROM gpkg_geometry_columns"
        ).fetchone()[0]
    assert declared == "GEOMETRY"
    assert _check_gpkg(path, "KEN", 2, 2, 2)["features"] == 2

    bad = tmp_path / "polygon_and_line.gpkg"
    frame.geometry = [box(0, 0, 1, 1), LineString([(2, 0), (3, 1)])]
    frame.to_file(bad, layer=layer, driver="GPKG", index=False)
    with pytest.raises(ValueError, match="non-polygon"):
        _check_gpkg(bad, "KEN", 2, 2, 2)


def test_submission_wrapper_requires_whole_array_id(tmp_path):
    fake_qsub = tmp_path / "qsub"
    fake_qsub.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding="utf-8")
    fake_qsub.chmod(0o755)
    code_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env.update(
        {
            "PATH": str(tmp_path) + os.pathsep + env["PATH"],
            "GADM_CODE_ROOT": str(code_root),
            "GADM_SOURCE": str(tmp_path / "source.gpkg"),
            "GADM_REGISTRY": str(tmp_path / "registry.csv"),
            "GADM_MANIFEST": str(tmp_path / "registry.json"),
            "GADM_OUTPUT_ROOT": str(tmp_path / "outputs"),
            "GADM_FINAL_MANIFEST": str(tmp_path / "final.json"),
            "GADM_FINAL_CSV": str(tmp_path / "final.csv"),
            "GADM_PYTHON": sys.executable,
        }
    )
    script = code_root / "hpc/submit_gadm_finalize_afterok.sh"
    rejected = subprocess.run(
        ["bash", str(script), "12345.pbs-7"], env=env, capture_output=True, text=True
    )
    assert rejected.returncode == 2
    accepted = subprocess.run(
        ["bash", str(script), "12345[].pbs-7"], env=env, capture_output=True, text=True
    )
    assert accepted.returncode == 0
    assert "depend=afterok:12345[].pbs-7" in accepted.stdout
