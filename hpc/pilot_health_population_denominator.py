"""Input-only C05 pilot: streamed population denominator and facility distance.

This intentionally does not construct or use a road graph, assign LCC nodes, or
compute healthcare travel times. Distances to facility *points* are descriptive
and are not a substitute for graph-based accessibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def spherical_xyz(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Unit-sphere embedding; chord distance orders spherical great circles."""
    lon_r = np.deg2rad(np.asarray(lon, dtype=np.float64))
    lat_r = np.deg2rad(np.asarray(lat, dtype=np.float64))
    cos_lat = np.cos(lat_r)
    return np.column_stack((cos_lat * np.cos(lon_r), cos_lat * np.sin(lon_r), np.sin(lat_r)))


def nearest_facility_geodesic_km(
    lon: np.ndarray,
    lat: np.ndarray,
    facility_lon: np.ndarray,
    facility_lat: np.ndarray,
    *,
    k: int = 16,
) -> np.ndarray:
    """WGS84 distance to closest of k spherical-nearest facility candidates.

    k-nearest is an acceleration, not a proof of global ellipsoidal minimum.
    The pilot must compare a sample to exhaustive distances before promotion.
    """
    from pyproj import Geod
    from scipy.spatial import cKDTree

    lon = np.asarray(lon, dtype=np.float64)
    lat = np.asarray(lat, dtype=np.float64)
    facility_lon = np.asarray(facility_lon, dtype=np.float64)
    facility_lat = np.asarray(facility_lat, dtype=np.float64)
    if not len(facility_lon):
        return np.full(len(lon), np.nan)
    k = min(max(1, k), len(facility_lon))
    tree = cKDTree(spherical_xyz(facility_lon, facility_lat))
    _chord, idx = tree.query(spherical_xyz(lon, lat), k=k)
    idx = np.asarray(idx).reshape(len(lon), k)
    geod = Geod(ellps="WGS84")
    best = np.full(len(lon), np.inf)
    for j in range(k):
        _az1, _az2, metres = geod.inv(lon, lat, facility_lon[idx[:, j]], facility_lat[idx[:, j]])
        best = np.minimum(best, metres / 1000.0)
    return best


def run(args: argparse.Namespace) -> dict:
    import geopandas as gpd
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    from osgeo import gdal, osr
    from shapely import contains_xy

    for path in (args.population_tif, args.boundary_gpkg, args.facilities_csv):
        if not path.is_file():
            raise FileNotFoundError(path)
    if args.country == "WestSahara" or args.iso3 == "ESH":
        raise ValueError("WestSahara/ESH is outside the formal 49-country scope")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    bounds = gpd.read_file(args.boundary_gpkg)
    if bounds.empty or bounds.crs is None:
        raise ValueError("Boundary is empty or lacks CRS")
    bounds = bounds.to_crs("EPSG:4326")
    geometries = [g for g in bounds.geometry if g is not None and not g.is_empty]
    if not geometries:
        raise ValueError("Boundary has no valid geometries")
    country_geometry = bounds.geometry.unary_union

    facilities = pd.read_csv(args.facilities_csv)
    facilities = facilities.loc[facilities["country"] == args.country].copy()
    if facilities.empty:
        raise ValueError(f"No reconstructed facilities for {args.country}")
    if facilities[["lon", "lat"]].isna().any().any():
        raise ValueError("Facility coordinate has NA")
    if not (facilities["lon"].between(-180, 180) & facilities["lat"].between(-90, 90)).all():
        raise ValueError("Facility coordinate is out of geographic bounds")
    flon = facilities["lon"].to_numpy(dtype=float)
    flat = facilities["lat"].to_numpy(dtype=float)

    counts = {"positive_pixels": 0, "inside_pixels": 0, "outside_pixels": 0,
              "invalid_pixels": 0, "zero_or_negative_pixels": 0}
    pop_tif = pop_inside = pop_outside = 0.0
    nearest_min = np.inf
    nearest_max = 0.0
    writer = None
    pixel_path = args.out_dir / f"{args.iso3}_population_facility_distance_pilot.parquet"
    try:
        src = gdal.Open(str(args.population_tif), gdal.GA_ReadOnly)
        if src is None:
            raise ValueError("GDAL cannot open population raster")
        crs = osr.SpatialReference(wkt=src.GetProjection())
        if crs.GetAuthorityCode(None) != "4326":
            raise ValueError(f"Expected EPSG:4326 population raster; got {src.GetProjection()}")
        band = src.GetRasterBand(1)
        nodata = band.GetNoDataValue()
        gt = src.GetGeoTransform()
        block_x, block_y = band.GetBlockSize()
        # TIFF stripes can be extremely short; cap tiles to bound memory.
        tile_x = min(max(block_x, 256), 1024)
        tile_y = min(max(block_y, 256), 1024)
        for yoff in range(0, src.RasterYSize, tile_y):
            for xoff in range(0, src.RasterXSize, tile_x):
                xsize = min(tile_x, src.RasterXSize - xoff)
                ysize = min(tile_y, src.RasterYSize - yoff)
                raw = np.asarray(band.ReadAsArray(xoff, yoff, xsize, ysize), dtype=np.float64)
                valid = np.isfinite(raw)
                if nodata is not None:
                    valid &= raw != nodata
                counts["invalid_pixels"] += int((~valid).sum())
                counts["zero_or_negative_pixels"] += int((valid & (raw <= 0)).sum())
                positive = valid & (raw > 0)
                if not positive.any():
                    continue
                rows, cols = np.nonzero(positive)
                pop = raw[rows, cols]
                full_rows = rows.astype(np.int64) + yoff
                full_cols = cols.astype(np.int64) + xoff
                lon = gt[0] + (full_cols + 0.5) * gt[1] + (full_rows + 0.5) * gt[2]
                lat = gt[3] + (full_cols + 0.5) * gt[4] + (full_rows + 0.5) * gt[5]
                inside = contains_xy(country_geometry, lon, lat)
                facility_km = np.full(len(pop), np.nan)
                if inside.any():
                    facility_km[inside] = nearest_facility_geodesic_km(
                        lon[inside], lat[inside], flon, flat
                    )
                    nearest_min = min(nearest_min, float(np.min(facility_km[inside])))
                    nearest_max = max(nearest_max, float(np.max(facility_km[inside])))
                table = pa.table({
                    "pixel_id": full_rows * src.RasterXSize + full_cols,
                    "row": full_rows,
                    "col": full_cols,
                    "lon": lon,
                    "lat": lat,
                    "population": pop,
                    "inside_country": inside,
                    "nearest_facility_km_pilot": facility_km,
                })
                if writer is None:
                    writer = pq.ParquetWriter(pixel_path, table.schema, compression="zstd")
                writer.write_table(table)
                counts["positive_pixels"] += len(pop)
                counts["inside_pixels"] += int(inside.sum())
                counts["outside_pixels"] += int((~inside).sum())
                pop_tif += float(pop.sum())
                pop_inside += float(pop[inside].sum())
                pop_outside += float(pop[~inside].sum())
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        raise ValueError("Population raster contains no positive valid pixels")
    if counts["positive_pixels"] != counts["inside_pixels"] + counts["outside_pixels"]:
        raise AssertionError("Pixel count conservation failed")
    if abs(pop_tif - (pop_inside + pop_outside)) > max(1e-4, 1e-10 * pop_tif):
        raise AssertionError("Population sum conservation failed")

    result = {
        "status": "PILOT_INPUT_ONLY_NOT_SCIENTIFIC_RELEASE",
        "country": args.country,
        "iso3": args.iso3,
        "population_positive_tif": pop_tif,
        "population_inside_country_center": pop_inside,
        "population_outside_country_center": pop_outside,
        "facility_count": len(facilities),
        "facility_distance_min_km_pilot": nearest_min if np.isfinite(nearest_min) else None,
        "facility_distance_max_km_pilot": nearest_max if counts["inside_pixels"] else None,
        **counts,
        "population_raster_crs": "EPSG:4326",
        "boundary_rule": "pixel_center_strictly_within_GADM_union",
        "facility_distance_method": "16 spherical candidates, WGS84 Geod refinement; sample exhaustive QC required",
        "input_sha256": {
            "population_tif": sha256_file(args.population_tif),
            "boundary_gpkg": sha256_file(args.boundary_gpkg),
            "facilities_csv": sha256_file(args.facilities_csv),
        },
        "pixel_parquet": str(pixel_path),
        "pixel_parquet_sha256": sha256_file(pixel_path),
        "code_sha256": sha256_file(Path(__file__)),
    }
    (args.out_dir / f"{args.iso3}_population_denominator_pilot_qc.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", required=True)
    parser.add_argument("--iso3", required=True)
    parser.add_argument("--population-tif", type=Path, required=True)
    parser.add_argument("--boundary-gpkg", type=Path, required=True)
    parser.add_argument("--facilities-csv", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
