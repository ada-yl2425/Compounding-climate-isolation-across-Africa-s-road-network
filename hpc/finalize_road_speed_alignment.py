"""Finalize 49-country C00 identity audits without approving speed physics."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finalize(registry_path: Path, results_root: Path, expected_count: int = 49) -> dict:
    with registry_path.open(newline="", encoding="utf-8") as source:
        registry = list(csv.DictReader(source))
    failures = []
    outputs = []
    if len(registry) != expected_count:
        failures.append(f"registry count {len(registry)} != {expected_count}")
    if len({row["archive_country"] for row in registry}) != len(registry):
        failures.append("duplicate archive country in registry")
    for row in registry:
        country = row["archive_country"]
        path = results_root / "admin_units" / country / "road_speed_alignment_qc.json"
        if not path.is_file():
            failures.append(f"missing QC: {country}")
            continue
        try:
            qc = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as error:
            failures.append(f"unreadable QC: {country}: {error}")
            continue
        required = (
            qc.get("status") == "PASS"
            and qc.get("country") == row["speed_country"]
            and qc.get("matched_ids") == qc.get("expected_speed_rows")
            and qc.get("matched_ids") == qc.get("speed_rows")
            and all(qc.get(name) == 0 for name in (
                "duplicate_id_rows", "malformed_id_rows", "missing_speed_ids",
                "extra_speed_ids", "geometry_mismatch_rows",
                "invalid_geometry_rows", "speed_surface_mismatch_rows"
            ))
        )
        if not required:
            failures.append(f"QC invariants failed: {country}")
        outputs.append({
            "archive_country": country,
            "speed_country": row["speed_country"],
            "qc_file": str(path),
            "qc_sha256": sha256(path),
            "source_features": qc.get("source_features"),
            "matched_ids": qc.get("matched_ids"),
            "status": qc.get("status"),
        })
    return {
        "status": "PASS" if not failures else "FAIL",
        "scope": "source_to_legacy_speed_identity_only_not_speed_model_validation",
        "expected_country_count": expected_count,
        "registry_sha256": sha256(registry_path),
        "countries_with_qc": len(outputs),
        "total_source_features": sum(item["source_features"] or 0 for item in outputs),
        "total_matched_ids": sum(item["matched_ids"] or 0 for item in outputs),
        "failures": failures,
        "outputs": outputs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--results-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = finalize(args.registry, args.results_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"C00_FINAL_{result['status']} countries={result['countries_with_qc']} matched={result['total_matched_ids']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
