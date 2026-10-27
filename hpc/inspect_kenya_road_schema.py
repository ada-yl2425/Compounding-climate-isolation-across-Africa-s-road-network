"""Read-only schema/CRS audit of one extracted road archive; no road modeling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def inspect(shapefile: Path) -> dict:
    import fiona
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform

    companions = {suffix: shapefile.with_suffix(suffix).is_file() for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg")}
    with fiona.open(shapefile) as source:
        sample_indices = (0, 8, 12, 16)
        sample = []
        sample_length_km = []
        sample_center_lonlat = []
        to_africa_m = Transformer.from_crs(source.crs, "ESRI:102022", always_xy=True)
        to_lonlat = Transformer.from_crs(source.crs, "EPSG:4326", always_xy=True)
        for index in sample_indices:
            feature = source[index]
            sample.append({key: str(value) for key, value in feature["properties"].items()})
            geometry = shape(feature["geometry"])
            sample_length_km.append(transform(to_africa_m.transform, geometry).length / 1000)
            center = transform(to_lonlat.transform, geometry).centroid
            sample_center_lonlat.append([center.x, center.y])
        result = {
            "status": "PASS" if all(companions.values()) and source.crs else "FAIL",
            "shapefile": str(shapefile),
            "companions": companions,
            "driver": source.driver,
            "crs": source.crs.to_string() if source.crs else None,
            "bounds": list(source.bounds),
            "feature_count": len(source),
            "schema": source.schema,
            "sample_indices": sample_indices,
            "sample_properties": sample,
            "sample_length_km_esri102022": sample_length_km,
            "sample_center_lonlat": sample_center_lonlat,
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
