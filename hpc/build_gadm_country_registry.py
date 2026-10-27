"""Build an auditable 49-country GADM 4.1 extraction registry.

Only SQLite metadata and GID columns are read. The source is never modified and
no geometries are dissolved here. The registry is a preflight input to the PBS
array in ``hpc/pbs_gadm_admin_array.pbs``; it does not approve any road or
healthcare result.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

FIELDS = (
    "array_index",
    "country_folder",
    "iso3",
    "admin_level",
    "source_rows",
    "target_unique_gid",
    "unique_gid1",
    "unique_gid2",
    "empty_gid2_rows",
    "status",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def code_country_mapping(code_path: Path) -> dict[str, str]:
    """Read the literal FOLDER_TO_ISO mapping without importing project code."""
    tree = ast.parse(code_path.read_text(encoding="utf-8"), filename=str(code_path))
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "FOLDER_TO_ISO"
            for target in node.targets
        )
    ]
    if len(matches) != 1:
        raise ValueError("expected exactly one literal FOLDER_TO_ISO assignment")
    mapping = ast.literal_eval(matches[0].value)
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("FOLDER_TO_ISO must be a nonempty dictionary")
    if any(
        not isinstance(folder, str) or not isinstance(iso, str)
        for folder, iso in mapping.items()
    ):
        raise ValueError("FOLDER_TO_ISO keys and values must be strings")
    return mapping


def formal_mapping(
    mapping: dict[str, str], *, expected_count: int = 49
) -> dict[str, str]:
    if mapping.get("WestSahara") != "ESH":
        raise ValueError(
            "WestSahara -> ESH exclusion is not present in the code mapping"
        )
    formal = {folder: iso for folder, iso in mapping.items() if iso != "ESH"}
    if len(formal) != expected_count:
        raise ValueError(
            f"expected {expected_count} formal countries, found {len(formal)}"
        )
    if any(not re.fullmatch(r"[A-Z]{3}", iso) for iso in formal.values()):
        raise ValueError("invalid ISO3 in FOLDER_TO_ISO")
    if len(set(formal.values())) != len(formal):
        raise ValueError("duplicate ISO3 in FOLDER_TO_ISO")
    return formal


def open_source_read_only(
    source_path: Path, layer: str = "gadm_410"
) -> sqlite3.Connection:
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", layer):
        raise ValueError("invalid SQLite layer identifier")
    connection = sqlite3.connect(source_path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    content = connection.execute(
        "SELECT data_type,srs_id FROM gpkg_contents WHERE table_name=?", (layer,)
    ).fetchone()
    geometry = connection.execute(
        "SELECT geometry_type_name,srs_id FROM gpkg_geometry_columns WHERE table_name=?",
        (layer,),
    ).fetchone()
    if content != ("features", 4326) or geometry != ("MULTIPOLYGON", 4326):
        connection.close()
        raise ValueError(f"{layer} must be MULTIPOLYGON features in EPSG:4326")
    return connection


def source_gid_counts(
    connection: sqlite3.Connection, isos: list[str], *, layer: str = "gadm_410"
) -> dict[str, dict]:
    """Read one aggregation over the GPKG, not one full-table pass per ISO."""
    if not isos or any(not re.fullmatch(r"[A-Z]{3}", iso) for iso in isos):
        raise ValueError("isos must be nonempty uppercase ISO3 codes")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", layer):
        raise ValueError("invalid SQLite layer identifier")
    placeholders = ",".join("?" for _ in isos)
    rows = connection.execute(
        f"""
        SELECT GID_0,
               COUNT(*) AS n_rows,
               COUNT(DISTINCT NULLIF(TRIM(GID_1),'')) AS n_gid1,
               COUNT(DISTINCT NULLIF(TRIM(GID_2),'')) AS n_gid2,
               SUM(CASE WHEN GID_1 IS NULL OR TRIM(GID_1)='' THEN 1 ELSE 0 END) AS empty_gid1,
               SUM(CASE WHEN GID_2 IS NULL OR TRIM(GID_2)='' THEN 1 ELSE 0 END) AS empty_gid2,
               SUM(CASE WHEN geom IS NULL THEN 1 ELSE 0 END) AS empty_geom
        FROM "{layer}"
        WHERE GID_0 IN ({placeholders})
        GROUP BY GID_0
        """,
        isos,
    ).fetchall()
    return {
        iso: {
            "source_rows": n_rows,
            "unique_gid1": n_gid1,
            "unique_gid2": n_gid2,
            "empty_gid1_rows": empty_gid1,
            "empty_gid2_rows": empty_gid2,
            "null_geometry_rows": empty_geom,
        }
        for iso, n_rows, n_gid1, n_gid2, empty_gid1, empty_gid2, empty_geom in rows
    }


def make_registry(formal: dict[str, str], counts: dict[str, dict]) -> list[dict]:
    missing = sorted(set(formal.values()) - set(counts))
    if missing:
        raise ValueError(f"GADM source missing formal ISO3: {missing}")
    result = []
    for index, (folder, iso) in enumerate(formal.items(), start=1):
        stats = counts[iso]
        n = stats["source_rows"]
        if n <= 0 or stats["empty_gid1_rows"] or stats["null_geometry_rows"]:
            raise ValueError(f"{iso}: empty source, GID_1, or geometry")
        if stats["empty_gid2_rows"] == 0:
            level, targets = 2, stats["unique_gid2"]
        elif stats["empty_gid2_rows"] == n:
            level, targets = 1, stats["unique_gid1"]
        else:
            raise ValueError(f"{iso}: mixed empty/nonempty GID_2")
        if targets < 1 or targets > n:
            raise ValueError(f"{iso}: impossible target GID count {targets}")
        result.append(
            {
                "array_index": index,
                "country_folder": folder,
                "iso3": iso,
                "admin_level": level,
                "source_rows": n,
                "target_unique_gid": targets,
                "unique_gid1": stats["unique_gid1"],
                "unique_gid2": stats["unique_gid2"],
                "empty_gid2_rows": stats["empty_gid2_rows"],
                "status": "READY",
            }
        )
    return result


def build(
    source_path: Path,
    code_path: Path,
    csv_path: Path,
    manifest_path: Path,
    *,
    layer: str = "gadm_410",
) -> dict:
    if csv_path.exists() or manifest_path.exists():
        raise FileExistsError("registry/manifest exists; use a new run-specific path")
    mapping = code_country_mapping(code_path)
    formal = formal_mapping(mapping)
    connection = open_source_read_only(source_path, layer)
    try:
        counts = source_gid_counts(connection, list(formal.values()), layer=layer)
    finally:
        connection.close()
    records = make_registry(formal, counts)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    manifest = {
        "status": "PASS",
        "source_file": str(source_path.resolve()),
        "source_layer": layer,
        "source_bytes": source_path.stat().st_size,
        "source_sha256": sha256(source_path),
        "code_mapping_file": str(code_path.resolve()),
        "code_mapping_sha256": sha256(code_path),
        "registry_file": str(csv_path.resolve()),
        "registry_sha256": sha256(csv_path),
        "formal_country_count": len(records),
        "excluded_country": "WestSahara",
        "excluded_iso3": "ESH",
        "l2_countries": sum(row["admin_level"] == 2 for row in records),
        "l1_fallback_countries": [
            row["iso3"] for row in records if row["admin_level"] == 1
        ],
        "source_rows_formal_total": sum(row["source_rows"] for row in records),
        "expected_output_features_total": sum(
            row["target_unique_gid"] for row in records
        ),
        "note": "Registry is an input/schema gate; geometry union and area QC run separately per country.",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, type=Path, help="Extracted original gadm_410.gpkg"
    )
    parser.add_argument(
        "--code-map", type=Path, default=Path("data_procession/prepare_city_layer.py")
    )
    parser.add_argument(
        "--registry", required=True, type=Path, help="New run-specific CSV"
    )
    parser.add_argument(
        "--manifest", required=True, type=Path, help="New run-specific JSON"
    )
    parser.add_argument("--layer", default="gadm_410")
    args = parser.parse_args()
    result = build(
        args.input, args.code_map, args.registry, args.manifest, layer=args.layer
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "formal_country_count": result["formal_country_count"],
                "l1_fallback_countries": result["l1_fallback_countries"],
                "registry": result["registry_file"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
