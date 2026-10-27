"""Verify the exact 49 archived-road inputs and legacy speed ZIP before C00 jobs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def file_hash(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(registry_path: Path, road_root: Path, speed_zip: Path, speed_sha256: str) -> dict:
    with registry_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    failures: list[str] = []
    if len(rows) != 49:
        failures.append(f"registry contains {len(rows)} countries, expected 49")
    expected_names = {row["archive_filename"] for row in rows}
    actual_names = {path.name for path in road_root.glob("*.rar") if path.is_file()}
    for name in sorted(expected_names - actual_names):
        failures.append(f"missing road archive: {name}")
    for name in sorted(actual_names - expected_names):
        failures.append(f"unexpected road archive: {name}")
    verified = []
    for row in rows:
        path = road_root / row["archive_filename"]
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size != int(row["archive_size_bytes"]):
            failures.append(f"wrong size: {path.name}: {size}")
            continue
        actual_md5 = file_hash(path, "md5")
        if actual_md5 != row["archive_figshare_md5"]:
            failures.append(f"wrong official MD5: {path.name}")
            continue
        verified.append({"filename": path.name, "size_bytes": size, "md5": actual_md5})
    actual_speed_sha = file_hash(speed_zip, "sha256") if speed_zip.is_file() else None
    if actual_speed_sha != speed_sha256:
        failures.append("legacy speed ZIP SHA-256 mismatch or missing")
    return {
        "status": "PASS" if not failures else "FAIL",
        "scope": "remote_transfer_integrity_only",
        "registry_sha256": file_hash(registry_path, "sha256"),
        "expected_road_archives": len(rows),
        "verified_road_archives": len(verified),
        "verified_road_bytes": sum(item["size_bytes"] for item in verified),
        "speed_zip_sha256": actual_speed_sha,
        "failures": failures,
        "archives": verified,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--road-root", required=True, type=Path)
    parser.add_argument("--speed-zip", required=True, type=Path)
    parser.add_argument("--speed-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.registry, args.road_root, args.speed_zip, args.speed_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"ROAD_TRANSFER_{result['status']} archives={result['verified_road_archives']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
