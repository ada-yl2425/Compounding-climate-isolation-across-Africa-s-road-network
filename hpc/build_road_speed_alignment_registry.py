"""Create the 49-country C00 audit registry from verified archive metadata."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import zipfile


ALIASES = {"CentralAfrian": "CentralAfrican"}
EXCLUDED = {"WestSahara"}
FIELDS = (
    "array_index", "archive_country", "speed_country", "archive_filename",
    "archive_size_bytes", "archive_figshare_md5", "speed_zip_member",
)


def build_registry(figshare_csv: Path, speed_zip: Path, archive_root: Path) -> list[dict]:
    with zipfile.ZipFile(speed_zip) as archive:
        members = set(archive.namelist())
    rows = []
    seen_archive = set()
    seen_speed = set()
    with figshare_csv.open(newline="", encoding="utf-8-sig") as source:
        for record in csv.DictReader(source):
            filename = record["filename"]
            if not filename.endswith(".rar"):
                raise ValueError(f"not a RAR archive: {filename}")
            archive_country = filename.removesuffix(".rar")
            if archive_country in EXCLUDED:
                continue
            speed_country = ALIASES.get(archive_country, archive_country)
            member = f"road_speed_cordex/{speed_country}_road_speed.csv"
            if member not in members:
                raise ValueError(f"missing speed CSV member: {member}")
            if archive_country in seen_archive or speed_country in seen_speed:
                raise ValueError(f"duplicate country mapping: {archive_country}/{speed_country}")
            if record["local_and_icloud_md5_match"].lower() != "true":
                raise ValueError(f"source verification not PASS: {filename}")
            path = archive_root / filename
            expected_bytes = int(record["size_bytes"])
            if not path.is_file() or path.stat().st_size != expected_bytes:
                raise ValueError(f"archive absent or wrong size: {path}")
            seen_archive.add(archive_country)
            seen_speed.add(speed_country)
            rows.append({
                "archive_country": archive_country,
                "speed_country": speed_country,
                "archive_filename": filename,
                "archive_size_bytes": expected_bytes,
                "archive_figshare_md5": record["figshare_md5"],
                "speed_zip_member": member,
            })
    rows.sort(key=lambda row: row["archive_country"])
    if len(rows) != 49:
        raise ValueError(f"expected 49 official result countries, got {len(rows)}")
    for index, row in enumerate(rows):
        row["array_index"] = index
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--figshare-csv", required=True, type=Path)
    parser.add_argument("--speed-zip", required=True, type=Path)
    parser.add_argument("--archive-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = build_registry(args.figshare_csv, args.speed_zip, args.archive_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"C00_REGISTRY_PASS countries={len(rows)} excluded=WestSahara aliases={ALIASES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
