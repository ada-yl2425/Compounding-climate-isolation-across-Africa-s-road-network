"""Read-only metadata audit of the staged Kenya engineering-pilot inputs.

This does not calculate road speeds or reviewer results. Run only after
``hpc.verify_manifest`` has reported PASS on the same input root.
"""

from __future__ import annotations

import argparse
import csv
import json
import zipfile
from pathlib import Path


def inspect(root: Path) -> dict:
    import rasterio
    import xarray as xr

    climate = root / "01_sources/climate/CORDEX_AFR44_SMHI-RCA4_v1"
    records: dict = {"status": "PASS", "climate": {}, "rasters": {}, "health": {}, "zip": {}}
    failures: list[str] = []

    for variable in ("pr", "mrso"):
        matches = list(climate.glob(f"{variable}_AFR-44_MPI-M-MPI-ESM-LR_rcp45_*_mon_201101-202012.nc"))
        if len(matches) != 1:
            failures.append(f"{variable}: expected one NetCDF, found {len(matches)}")
            continue
        with xr.open_dataset(matches[0], engine="h5netcdf") as ds:
            if variable not in ds:
                failures.append(f"{variable}: variable absent")
                continue
            da = ds[variable]
            times = ds.indexes["time"]
            months = [(int(t.year), int(t.month)) for t in times]
            expected = [(year, month) for year in range(2011, 2021) for month in range(1, 13)]
            if months != expected:
                failures.append(f"{variable}: time is not exactly 2011-01 through 2020-12")
            records["climate"][variable] = {
                "file": str(matches[0].relative_to(root)),
                "shape": list(da.shape),
                "dims": list(da.dims),
                "units": da.attrs.get("units"),
                "calendar": ds["time"].encoding.get("calendar", ds["time"].attrs.get("calendar")),
                "time_count": len(times),
                "first_month": f"{months[0][0]:04d}-{months[0][1]:02d}",
                "last_month": f"{months[-1][0]:04d}-{months[-1][1]:02d}",
            }

    for name, rel in {
        "worldpop": "01_sources/population/WorldPop_2020_UNadj_constrained_candidate/ken_ppp_2020_UNadj_constrained.tif",
        "slope": "01_sources/terrain/pending_provenance/africa_slope_1km.tif",
        "elevation": "01_sources/terrain/pending_provenance/africa_elevation_1km.tif",
    }.items():
        with rasterio.open(root / rel) as src:
            records["rasters"][name] = {
                "file": rel,
                "crs": str(src.crs),
                "width": src.width,
                "height": src.height,
                "count": src.count,
                "dtype": src.dtypes[0],
                "nodata": src.nodata,
                "bounds": list(src.bounds),
                "tags": src.tags(),
            }
            if src.crs is None:
                failures.append(f"{name}: missing CRS")

    health_rel = "01_sources/health_facilities/legacy_gpkg_reconstruction_v1/health_facilities_from_legacy_gpkg.csv"
    with (root / health_rel).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        required = {"country", "lon", "lat"}
        if not required.issubset(header):
            failures.append("health: missing country/lon/lat columns")
        total = kenya = invalid = 0
        for row in reader:
            total += 1
            kenya += row.get("country") == "Kenya"
            try:
                lon, lat = float(row["lon"]), float(row["lat"])
                invalid += not (-180 <= lon <= 180 and -90 <= lat <= 90)
            except (KeyError, ValueError, TypeError):
                invalid += 1
        records["health"] = {"file": health_rel, "columns": header, "rows": total, "kenya_rows": kenya, "invalid_coordinates": invalid}
        if invalid:
            failures.append(f"health: {invalid} invalid coordinate rows")

    zip_rel = "02_derived_checkpoints/legacy_reference/web_components/africa_layer.zip"
    with zipfile.ZipFile(root / zip_rel) as archive:
        records["zip"] = {"file": zip_rel, "members": archive.namelist(), "bad_member": archive.testzip()}
        if records["zip"]["bad_member"] is not None:
            failures.append("legacy city ZIP: CRC failure")

    records["failures"] = failures
    records["status"] = "PASS" if not failures else "FAIL"
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = inspect(args.root)
    payload = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
