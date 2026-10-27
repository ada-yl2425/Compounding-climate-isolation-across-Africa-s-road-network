"""Fail-closed final audit of a 49-country GADM extraction array.

Read the PASS preflight registry, all country QC JSON reports, and all output
GeoPackages. Recheck bytes, hashes, layer schema, CRS, country/GID counts, and
per-country area diagnostics. A failed run writes a FAIL output manifest but
never writes the small PASS summary CSV. This does not recompute geometries or
any paper result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path


SUMMARY_FIELDS = (
    "array_index",
    "country_folder",
    "iso3",
    "admin_level",
    "source_rows",
    "target_unique_gid",
    "output_bytes",
    "output_sha256",
    "qc_sha256",
    "area_delta_km2",
    "symmetric_difference_km2",
    "source_overlap_km2",
    "target_overlap_km2",
    "status",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_registry(path: Path, expected_count: int) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != expected_count:
        raise ValueError(f"registry has {len(rows)} rows, expected {expected_count}")
    indices = [int(row["array_index"]) for row in rows]
    if indices != list(range(1, expected_count + 1)):
        raise ValueError("registry array indices must be exactly 1..49 in order")
    countries = [row["iso3"] for row in rows]
    if len(set(countries)) != expected_count or "ESH" in countries:
        raise ValueError("registry ISO3 set is duplicated or contains ESH")
    if any(not re.fullmatch(r"[A-Z]{3}", iso) for iso in countries):
        raise ValueError("registry contains invalid ISO3")
    if any(
        row["status"] != "READY" or row["admin_level"] not in {"1", "2"} for row in rows
    ):
        raise ValueError("registry has non-READY or invalid-level row")
    return rows


def _check_gpkg(
    path: Path, iso: str, level: int, expected_count: int, expected_rows: int
) -> dict:
    layer = f"gadm41_{iso}_{level}"
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        contents = connection.execute(
            "SELECT table_name,data_type,srs_id FROM gpkg_contents"
        ).fetchall()
        if contents != [(layer, "features", 4326)]:
            raise ValueError(
                f"GPKG must contain only {layer} features, EPSG:4326; found {contents}"
            )
        geom = connection.execute(
            "SELECT column_name,geometry_type_name,srs_id FROM gpkg_geometry_columns WHERE table_name=?",
            (layer,),
        ).fetchone()
        if (
            geom is None
            or geom[1] not in {"POLYGON", "MULTIPOLYGON", "GEOMETRY"}
            or geom[2] != 4326
        ):
            raise ValueError(f"invalid GPKG geometry metadata: {geom}")
        geom_col = geom[0]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", geom_col):
            raise ValueError("invalid GPKG geometry column name")
        key = "GID_2" if level == 2 else "GID_1"
        result = connection.execute(
            f'''SELECT COUNT(*),COUNT(DISTINCT admin_gid),
                       SUM(CASE WHEN GID_0<>? OR GID_0 IS NULL THEN 1 ELSE 0 END),
                       SUM(CASE WHEN admin_level<>? OR admin_level IS NULL THEN 1 ELSE 0 END),
                       SUM(CASE WHEN admin_gid<>"{key}" OR admin_gid IS NULL OR "{key}" IS NULL THEN 1 ELSE 0 END),
                       SUM(CASE WHEN "{geom_col}" IS NULL OR length("{geom_col}")=0 THEN 1 ELSE 0 END),
                       SUM(source_rows)
                FROM "{layer}"''',
            (iso, level),
        ).fetchone()
        n, n_gid, wrong_iso, wrong_level, wrong_key, missing_geom, source_rows_sum = (
            result
        )
        if (n, n_gid) != (expected_count, expected_count):
            raise ValueError(
                f"feature/unique GID count {n}/{n_gid} != {expected_count}"
            )
        if any((wrong_iso, wrong_level, wrong_key, missing_geom)):
            raise ValueError(
                f"GPKG row mismatch iso={wrong_iso},level={wrong_level},key={wrong_key},geom={missing_geom}"
            )
        if source_rows_sum != expected_rows:
            raise ValueError(f"source_rows sum {source_rows_sum} != {expected_rows}")
        if geom[1] == "GEOMETRY":
            # GeoPandas/Fiona declares a layer GEOMETRY when valid polygon and
            # multipolygon units coexist. A generic declaration is acceptable
            # only after checking every actual feature, not by metadata alone.
            import geopandas as gpd

            geometries = gpd.read_file(path, layer=layer).geometry
            if (
                len(geometries) != expected_count
                or geometries.isna().any()
                or geometries.is_empty.any()
                or not geometries.geom_type.isin({"Polygon", "MultiPolygon"}).all()
                or not geometries.is_valid.all()
            ):
                raise ValueError("GEOMETRY layer contains non-polygon/invalid features")
        return {
            "layer": layer,
            "features": n,
            "unique_gid": n_gid,
            "source_rows_sum": source_rows_sum,
        }
    finally:
        connection.close()


def _check_country(row: dict, root: Path, preflight: dict) -> dict:
    iso = row["iso3"]
    level = int(row["admin_level"])
    expected_rows = int(row["source_rows"])
    expected_count = int(row["target_unique_gid"])
    folder = root / iso
    output = folder / f"gadm41_{iso}_{level}.gpkg"
    report = folder / f"gadm41_{iso}_{level}_qc.json"
    if not report.is_file():
        raise FileNotFoundError(report)
    qc = json.loads(report.read_text(encoding="utf-8"))
    expected = {
        "status": "PASS",
        "country": iso,
        "admin_level": level,
        "source_rows": expected_rows,
        "target_unique_admin_gid": expected_count,
        "source_unique_admin_gid": expected_count,
        "source_layer": preflight["source_layer"],
        "output_layer": f"gadm41_{iso}_{level}",
    }
    for key, value in expected.items():
        if qc.get(key) != value:
            raise ValueError(f"{iso}: QC {key}={qc.get(key)!r}, expected {value!r}")
    if Path(qc["source_file"]).resolve() != Path(preflight["source_file"]).resolve():
        raise ValueError(f"{iso}: QC source path differs from preflight")
    if Path(qc["output_file"]).resolve() != output.resolve():
        raise ValueError(f"{iso}: QC output path differs from expected")
    if not output.is_file():
        raise FileNotFoundError(output)
    output_bytes = output.stat().st_size
    output_sha = sha256(output)
    if qc.get("output_bytes") != output_bytes or qc.get("output_sha256") != output_sha:
        raise ValueError(f"{iso}: GPKG size/SHA-256 differs from QC report")
    metrics = (
        "area_delta_km2",
        "symmetric_difference_km2",
        "source_overlap_km2",
        "target_overlap_km2",
    )
    tolerance = float(qc["area_tolerance_km2"])
    if tolerance < 0 or any(not 0 <= float(qc[key]) <= tolerance for key in metrics):
        raise ValueError(f"{iso}: area/overlap QC exceeds declared tolerance")
    if qc.get("source_crs") != "EPSG:4326" or qc.get("output_crs") != "EPSG:4326":
        raise ValueError(f"{iso}: QC CRS differs from EPSG:4326")
    gpkg = _check_gpkg(output, iso, level, expected_count, expected_rows)
    return {
        "array_index": int(row["array_index"]),
        "country_folder": row["country_folder"],
        "iso3": iso,
        "admin_level": level,
        "source_rows": expected_rows,
        "target_unique_gid": expected_count,
        "output_file": str(output.resolve()),
        "output_layer": gpkg["layer"],
        "output_bytes": output_bytes,
        "output_sha256": output_sha,
        "qc_file": str(report.resolve()),
        "qc_sha256": sha256(report),
        **{key: qc[key] for key in metrics},
        "status": "PASS",
    }


def audit_outputs(
    registry: Path,
    registry_manifest: Path,
    source: Path,
    output_root: Path,
    *,
    expected_count: int = 49,
) -> tuple[dict, list[dict]]:
    """Return final manifest and passing country rows; never changes inputs."""
    preflight = json.loads(registry_manifest.read_text(encoding="utf-8"))
    if (
        preflight.get("status") != "PASS"
        or preflight.get("formal_country_count") != expected_count
    ):
        raise ValueError("preflight manifest must be PASS with exact country count")
    if sha256(registry) != preflight.get("registry_sha256"):
        raise ValueError("registry SHA-256 mismatch")
    if source.resolve() != Path(preflight["source_file"]).resolve():
        raise ValueError("source path differs from preflight manifest")
    if source.stat().st_size != preflight.get("source_bytes") or sha256(
        source
    ) != preflight.get("source_sha256"):
        raise ValueError("original GADM source size/SHA-256 mismatch")
    rows = _read_registry(registry, expected_count)
    passes, failures = [], []
    for row in rows:
        try:
            passes.append(_check_country(row, output_root, preflight))
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            sqlite3.DatabaseError,
            json.JSONDecodeError,
        ) as exc:
            failures.append({"iso3": row["iso3"], "reason": str(exc)})
    manifest = {
        "status": "PASS" if len(passes) == expected_count and not failures else "FAIL",
        "expected_country_count": expected_count,
        "passed_country_count": len(passes),
        "failures": failures,
        "countries": [row["iso3"] for row in rows],
        "registry_file": str(registry.resolve()),
        "registry_sha256": preflight["registry_sha256"],
        "registry_manifest_file": str(registry_manifest.resolve()),
        "registry_manifest_sha256": sha256(registry_manifest),
        "source_file": str(source.resolve()),
        "source_bytes": preflight["source_bytes"],
        "source_sha256": preflight["source_sha256"],
        "output_root": str(output_root.resolve()),
        "source_rows_formal_total_expected": sum(
            int(row["source_rows"]) for row in rows
        ),
        "target_features_total_expected": sum(
            int(row["target_unique_gid"]) for row in rows
        ),
        "target_features_total_passed": sum(row["target_unique_gid"] for row in passes),
        "outputs": passes,
        "note": "Input-boundary preprocessing only; no road or reviewer scientific results approved.",
    }
    return manifest, passes


def finalize(
    registry: Path,
    registry_manifest: Path,
    source: Path,
    output_root: Path,
    manifest_path: Path,
    summary_path: Path,
    *,
    expected_count: int = 49,
) -> dict:
    if manifest_path.exists() or summary_path.exists():
        raise FileExistsError(
            "final manifest/summary exists; use a fresh run-specific path"
        )
    try:
        manifest, rows = audit_outputs(
            registry,
            registry_manifest,
            source,
            output_root,
            expected_count=expected_count,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        sqlite3.DatabaseError,
        json.JSONDecodeError,
    ) as exc:
        manifest, rows = {
            "status": "FAIL",
            "failures": [{"stage": "preflight", "reason": str(exc)}],
        }, []
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest["status"] == "PASS":
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=SUMMARY_FIELDS,
                lineterminator="\n",
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)
        manifest["summary_file"] = str(summary_path.resolve())
        manifest["summary_sha256"] = sha256(summary_path)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--registry-manifest", required=True, type=Path)
    parser.add_argument(
        "--source", required=True, type=Path, help="Original extracted gadm_410.gpkg"
    )
    parser.add_argument(
        "--output-root", required=True, type=Path, help="Country output parent"
    )
    parser.add_argument("--manifest", required=True, type=Path, help="New final JSON")
    parser.add_argument(
        "--summary", required=True, type=Path, help="New PASS-only small CSV"
    )
    args = parser.parse_args()
    result = finalize(
        args.registry,
        args.registry_manifest,
        args.source,
        args.output_root,
        args.manifest,
        args.summary,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "passed": result.get("passed_country_count", 0),
                "expected": result.get("expected_country_count", 49),
                "manifest": str(args.manifest),
            },
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
