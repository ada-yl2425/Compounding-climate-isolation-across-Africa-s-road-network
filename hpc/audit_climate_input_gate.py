"""Read-only metadata/identity gate for the paper's CORDEX monthly inputs.

This does not calculate road speeds or endorse any HDM parameter.  It verifies
the exact 16 source files needed for baseline, six future model/period pairs,
and the SI RCP8.5 check against their retained SHA-256 manifest.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import xarray as xr


SCENARIOS = (
    ("MPI-M-MPI-ESM-LR", "rcp45", 2011, 2020, "baseline"),
    ("MPI-M-MPI-ESM-LR", "rcp45", 2041, 2050, "future"),
    ("MPI-M-MPI-ESM-LR", "rcp45", 2061, 2070, "future"),
    ("MPI-M-MPI-ESM-LR", "rcp45", 2081, 2090, "future"),
    ("MIROC-MIROC5", "rcp45", 2041, 2050, "future"),
    ("MIROC-MIROC5", "rcp45", 2061, 2070, "future"),
    ("MIROC-MIROC5", "rcp45", 2081, 2090, "future"),
    ("MPI-M-MPI-ESM-LR", "rcp85", 2081, 2090, "si_s8"),
)

EXPECTED_UNITS = {"pr": "kg m-2 s-1", "mrso": "kg m-2"}


def expected_files():
    for gcm, rcp, first, last, purpose in SCENARIOS:
        for variable in ("pr", "mrso"):
            name = (
                f"{variable}_AFR-44_{gcm}_{rcp}_r1i1p1_"
                f"SMHI-RCA4_v1_mon_{first}01-{last}12.nc"
            )
            yield name, variable, gcm, rcp, first, last, purpose


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_hash_registry(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream)
        rows = list(reader)
    if rows[0] != ["filename", "sha256"]:
        raise ValueError(f"Unexpected hash registry header: {rows[0]!r}")
    return {name: digest for name, digest in rows[1:]}


def inspect_file(path, variable, gcm, rcp, first, last, expected_hash):
    result = {"file": path.name, "status": "FAIL", "errors": []}
    errors = result["errors"]
    if not path.is_file():
        errors.append("missing_file")
        return result

    result["bytes"] = path.stat().st_size
    result["sha256"] = file_sha256(path)
    if not expected_hash:
        errors.append("missing_hash_registry_entry")
    elif result["sha256"] != expected_hash:
        errors.append("sha256_mismatch")

    try:
        with xr.open_dataset(path, engine="h5netcdf") as ds:
            result["dimensions"] = dict(ds.sizes)
            result["calendar"] = ds.time.encoding.get("calendar")
            result["time_bounds_name"] = ds.time.attrs.get("bounds")
            result["variable_units"] = ds[variable].attrs.get("units")
            result["attributes"] = {
                key: ds.attrs.get(key)
                for key in (
                    "CORDEX_domain",
                    "model_id",
                    "driving_model_id",
                    "experiment_id",
                    "frequency",
                )
            }
            year_month = list(
                zip(ds.time.dt.year.values.tolist(), ds.time.dt.month.values.tolist())
            )
            expected_months = [
                (year, month)
                for year in range(first, last + 1)
                for month in range(1, 13)
            ]
            result["first_month"] = year_month[0] if year_month else None
            result["last_month"] = year_month[-1] if year_month else None
            result["month_count"] = len(year_month)
            if year_month != expected_months:
                errors.append("month_sequence_mismatch")
            if ds.sizes.get("time") != 120:
                errors.append("not_120_months")
            if result["variable_units"] != EXPECTED_UNITS[variable]:
                errors.append("variable_units_mismatch")
            if result["attributes"] != {
                "CORDEX_domain": "AFR-44",
                "model_id": "SMHI-RCA4",
                "driving_model_id": gcm,
                "experiment_id": rcp,
                "frequency": "mon",
            }:
                errors.append("model_member_or_frequency_mismatch")
            if ds.sizes.get("rlat") != 201 or ds.sizes.get("rlon") != 194:
                errors.append("grid_shape_mismatch")
            bounds_name = result["time_bounds_name"]
            if not bounds_name or bounds_name not in ds:
                errors.append("missing_time_bounds")
            else:
                bounds = ds[bounds_name]
                if bounds.ndim != 2 or bounds.shape != (120, 2):
                    errors.append("time_bounds_shape_mismatch")
                else:
                    bdim = bounds.dims[1]
                    seconds = (
                        bounds.isel({bdim: 1}) - bounds.isel({bdim: 0})
                    ) / np.timedelta64(1, "s")
                    days = np.asarray(seconds.values) / 86400
                    result["month_duration_days"] = sorted(
                        set(days.astype(int).tolist())
                    )
                    if not np.all(np.isfinite(days)) or not np.all(
                        (days >= 28) & (days <= 31) & (days == np.floor(days))
                    ):
                        errors.append("invalid_time_bound_durations")
    except Exception as exc:
        errors.append(f"read_error:{type(exc).__name__}:{exc}")

    result["status"] = "PASS" if not errors else "FAIL"
    return result


def audit(climate_dir: Path, hash_registry: Path):
    hashes = load_hash_registry(hash_registry)
    files = []
    for name, variable, gcm, rcp, first, last, purpose in expected_files():
        item = inspect_file(
            climate_dir / name,
            variable,
            gcm,
            rcp,
            first,
            last,
            hashes.get(name),
        )
        item["purpose"] = purpose
        files.append(item)
    return {
        "status": "PASS" if all(f["status"] == "PASS" for f in files) else "FAIL",
        "scope": "paper_baseline_future_main_and_si_s8_16_netcdf",
        "files": files,
        "pass_count": sum(f["status"] == "PASS" for f in files),
        "fail_count": sum(f["status"] != "PASS" for f in files),
        "caveat": "File identity/metadata only; not road-slope/curvature, IRI, monthly-iteration or old-run provenance.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--climate-dir", required=True, type=Path)
    parser.add_argument("--hash-registry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.climate_dir, args.hash_registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"CLIMATE_INPUT_GATE_{report['status']} "
        f"{report['pass_count']}/{len(report['files'])} {args.output}"
    )
    raise SystemExit(report["fail_count"] > 0)


if __name__ == "__main__":
    main()
