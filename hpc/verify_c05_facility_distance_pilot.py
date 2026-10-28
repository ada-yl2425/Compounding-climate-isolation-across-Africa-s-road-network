"""Exhaustively verify a small-country C05 facility-distance pilot."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Geod


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pixels", type=Path, required=True)
    parser.add_argument("--facilities", type=Path, required=True)
    parser.add_argument("--country", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pixels = pd.read_parquet(args.pixels)
    pixels = pixels.loc[pixels["inside_country"]]
    facilities = pd.read_csv(args.facilities).loc[lambda d: d["country"] == args.country]
    lon = pixels["lon"].to_numpy(dtype=float)
    lat = pixels["lat"].to_numpy(dtype=float)
    approximate = pixels["nearest_facility_km_pilot"].to_numpy(dtype=float)
    full_min = np.full(len(lon), np.inf)
    geod = Geod(ellps="WGS84")
    for facility in facilities.itertuples(index=False):
        _az1, _az2, metres = geod.inv(lon, lat, np.full(len(lon), facility.lon),
                                       np.full(len(lat), facility.lat))
        full_min = np.minimum(full_min, metres / 1000.0)
    error = np.abs(approximate - full_min)
    result = {
        "status": "PASS" if len(error) and np.max(error) <= 0.1 else "FAIL",
        "country": args.country,
        "evaluated_pixels": len(error),
        "facilities": len(facilities),
        "max_abs_error_km": float(np.max(error)) if len(error) else None,
        "pixels_error_gt_0_1km": int(np.sum(error > 0.1)),
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
