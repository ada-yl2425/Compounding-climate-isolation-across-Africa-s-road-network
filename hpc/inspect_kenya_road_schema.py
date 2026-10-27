"""Read-only schema/CRS audit of one extracted road archive; no road modeling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def inspect(shapefile: Path) -> dict:
    import fiona

    companions = {suffix: shapefile.with_suffix(suffix).is_file() for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg")}
    with fiona.open(shapefile) as source:
        sample = []
        for index, feature in enumerate(source):
            if index == 3:
                break
            sample.append({key: str(value) for key, value in feature["properties"].items()})
        result = {
            "status": "PASS" if all(companions.values()) and source.crs else "FAIL",
            "shapefile": str(shapefile),
            "companions": companions,
            "driver": source.driver,
            "crs": source.crs.to_string() if source.crs else None,
            "bounds": list(source.bounds),
            "feature_count": len(source),
            "schema": source.schema,
            "sample_properties": sample,
            "note": "Archive schema only; stable edge IDs, geometry validity and model fields are not yet approved.",
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shapefile", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = inspect(args.shapefile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
