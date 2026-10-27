"""Audit legacy speed rows against unfiltered source-road feature identities.

This is an engineering lineage check, not a climate/IRI recalculation.  The
legacy speed writer numbers source features before filtering for unpaved roads
and a 0.05 km projected length.  Reconstruct those rules and compare every
retained row with its speed-table geometry fields.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path


REQUIRED_SPEED_COLUMNS = {
    "road_id",
    "Surface",
    "length_km",
    "center_lon",
    "center_lat",
}
MAX_EXAMPLES = 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_road_id(country: str, source_row: int) -> str:
    if not country or source_row < 0:
        raise ValueError("invalid country or source row")
    return f"{country}_road_{source_row}"


def is_unpaved(surface: object) -> bool:
    return isinstance(surface, str) and "unpaved" in surface.lower()


def close_enough(actual: float, expected: float, *, absolute_tolerance: float) -> bool:
    return math.isfinite(actual) and math.isfinite(expected) and math.isclose(
        actual, expected, rel_tol=1e-8, abs_tol=absolute_tolerance
    )


def load_speed_rows(path: Path, country: str) -> tuple[dict[str, dict], dict]:
    rows: dict[str, dict] = {}
    duplicate_ids: list[str] = []
    duplicate_count = 0
    malformed_rows = 0
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing = sorted(REQUIRED_SPEED_COLUMNS - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"speed CSV missing columns: {missing}")
        for row in reader:
            road_id = row["road_id"]
            if road_id in rows:
                duplicate_count += 1
                if len(duplicate_ids) < MAX_EXAMPLES:
                    duplicate_ids.append(road_id)
                continue
            if not re.fullmatch(re.escape(country) + r"_road_[0-9]+", road_id):
                malformed_rows += 1
            rows[road_id] = row
    return rows, {
        "speed_rows": len(rows) + duplicate_count,
        "speed_unique_ids": len(rows),
        "duplicate_id_rows": duplicate_count,
        "duplicate_id_examples": duplicate_ids,
        "malformed_id_rows": malformed_rows,
    }


def audit(shapefile: Path, speed_csv: Path, country: str) -> dict:
    import fiona
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform

    speed, speed_stats = load_speed_rows(speed_csv, country)
    unmatched_speed = set(speed)
    stats = {
        "source_features": 0,
        "source_unpaved": 0,
        "source_unpaved_below_0_05_km": 0,
        "expected_speed_rows": 0,
        "matched_ids": 0,
        "missing_speed_ids": 0,
        "geometry_mismatch_rows": 0,
        "invalid_geometry_rows": 0,
        "speed_surface_mismatch_rows": 0,
    }
    examples = {name: [] for name in (
        "missing_speed_ids", "geometry_mismatch_rows", "invalid_geometry_rows",
        "speed_surface_mismatch_rows", "extra_speed_ids"
    )}

    def record(name: str, item: object) -> None:
        stats[name] += 1
        if len(examples[name]) < MAX_EXAMPLES:
            examples[name].append(item)

    with fiona.open(shapefile) as source:
        if not source.crs:
            raise ValueError("source shapefile has no CRS")
        to_m = Transformer.from_crs(source.crs, "ESRI:102022", always_xy=True)
        to_ll = Transformer.from_crs(source.crs, "EPSG:4326", always_xy=True)
        source_crs = source.crs.to_string()
        source_schema = source.schema
        for source_row, feature in enumerate(source):
            stats["source_features"] += 1
            surface = feature["properties"].get("Surface")
            if not is_unpaved(surface):
                continue
            stats["source_unpaved"] += 1
            road_id = source_road_id(country, source_row)
            try:
                geometry = shape(feature["geometry"])
                if geometry.is_empty or not geometry.is_valid:
                    raise ValueError("empty or invalid source geometry")
                length_km = transform(to_m.transform, geometry).length / 1000.0
                if not math.isfinite(length_km):
                    raise ValueError("nonfinite projected length")
            except (TypeError, ValueError) as error:
                record("invalid_geometry_rows", {"road_id": road_id, "error": str(error)})
                continue
            if length_km < 0.05:
                stats["source_unpaved_below_0_05_km"] += 1
                continue
            stats["expected_speed_rows"] += 1
            actual = speed.get(road_id)
            if actual is None:
                record("missing_speed_ids", road_id)
                continue
            unmatched_speed.discard(road_id)
            stats["matched_ids"] += 1
            center = transform(to_ll.transform, geometry).centroid
            try:
                values_match = all((
                    close_enough(float(actual["length_km"]), length_km, absolute_tolerance=1e-6),
                    close_enough(float(actual["center_lon"]), center.x, absolute_tolerance=1e-7),
                    close_enough(float(actual["center_lat"]), center.y, absolute_tolerance=1e-7),
                ))
            except (TypeError, ValueError):
                values_match = False
            if not values_match:
                record("geometry_mismatch_rows", road_id)
            if not is_unpaved(actual["Surface"]):
                record("speed_surface_mismatch_rows", road_id)

    examples["extra_speed_ids"] = sorted(unmatched_speed)[:MAX_EXAMPLES]
    status = "PASS" if (
        speed_stats["duplicate_id_rows"] == 0
        and speed_stats["malformed_id_rows"] == 0
        and all(stats[name] == 0 for name in (
            "missing_speed_ids", "geometry_mismatch_rows", "invalid_geometry_rows",
            "speed_surface_mismatch_rows"
        ))
        and not unmatched_speed
        and stats["matched_ids"] == stats["expected_speed_rows"]
    ) else "FAIL"
    return {
        "status": status,
        "scope": "legacy_road_speed_identity_alignment_only",
        "country": country,
        "source_shapefile": str(shapefile),
        "source_shapefile_sha256": sha256(shapefile),
        "speed_csv": str(speed_csv),
        "speed_csv_sha256": sha256(speed_csv),
        "source_crs": source_crs,
        "source_schema": source_schema,
        **speed_stats,
        **stats,
        "extra_speed_ids": len(unmatched_speed),
        "examples": examples,
        "note": "Does not validate slope/curvature, climate, IRI, passability or final graph weights.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shapefile", required=True, type=Path)
    parser.add_argument("--speed-csv", required=True, type=Path)
    parser.add_argument("--country", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.shapefile, args.speed_csv, args.country)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
