"""Compose immutable 48-country array outputs plus isolated Ghana repair.

Only creates symlinks after all expected country outputs and QC reports pass
basic identity/hash checks. The downstream finalizer independently verifies
the full GeoPackage schema, GIDs, CRS, geometry audit and original source.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compose(
    registry: Path,
    original_root: Path,
    repair_root: Path,
    composed_root: Path,
    original_commit: str,
    repair_commit: str,
) -> dict:
    if composed_root.exists():
        raise FileExistsError(f"fresh composed root required: {composed_root}")
    with registry.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 49 or len({row["iso3"] for row in rows}) != 49:
        raise ValueError("registry must contain exactly 49 unique countries")
    if [int(row["array_index"]) for row in rows] != list(range(1, 50)):
        raise ValueError("registry indices must be 1..49")
    if sum(row["iso3"] == "GHA" for row in rows) != 1:
        raise ValueError("GHA must appear exactly once")

    links = []
    for row in rows:
        iso = row["iso3"]
        level = int(row["admin_level"])
        producer_root = repair_root if iso == "GHA" else original_root
        producer_commit = repair_commit if iso == "GHA" else original_commit
        source_dir = producer_root / iso
        gpkg = source_dir / f"gadm41_{iso}_{level}.gpkg"
        report = source_dir / f"gadm41_{iso}_{level}_qc.json"
        if not gpkg.is_file() or not report.is_file():
            raise FileNotFoundError(f"{iso}: GPKG or QC report missing")
        qc = json.loads(report.read_text(encoding="utf-8"))
        if (
            qc.get("status") != "PASS"
            or qc.get("country") != iso
            or qc.get("admin_level") != level
            or qc.get("source_rows") != int(row["source_rows"])
            or qc.get("target_unique_admin_gid") != int(row["target_unique_gid"])
            or Path(qc["output_file"]).resolve() != gpkg.resolve()
            or qc.get("output_bytes") != gpkg.stat().st_size
            or qc.get("output_sha256") != sha256(gpkg)
        ):
            raise ValueError(f"{iso}: producer output differs from PASS QC/registry")
        links.append(
            {
                "iso3": iso,
                "producer_commit": producer_commit,
                "producer_directory": str(source_dir.resolve()),
                "gpkg_sha256": qc["output_sha256"],
                "qc_sha256": sha256(report),
            }
        )

    composed_root.mkdir(parents=True)
    for row in links:
        (composed_root / row["iso3"]).symlink_to(
            row["producer_directory"], target_is_directory=True
        )
    lineage = {
        "status": "COMPOSED_PENDING_FINAL_AUDIT",
        "original_array_commit": original_commit,
        "ghana_repair_commit": repair_commit,
        "original_root": str(original_root.resolve()),
        "repair_root": str(repair_root.resolve()),
        "composed_root": str(composed_root.resolve()),
        "country_count": len(links),
        "countries": links,
    }
    (composed_root / "lineage.json").write_text(
        json.dumps(lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return lineage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--original-root", required=True, type=Path)
    parser.add_argument("--repair-root", required=True, type=Path)
    parser.add_argument("--composed-root", required=True, type=Path)
    parser.add_argument("--original-commit", required=True)
    parser.add_argument("--repair-commit", required=True)
    args = parser.parse_args()
    lineage = compose(**vars(args))
    print(json.dumps({"status": lineage["status"], "countries": 49}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
