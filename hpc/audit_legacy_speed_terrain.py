"""Forensic zero-terrain comparison against an OLD baseline speed CSV.

Uses the submitted code's former fixed-30-day precipitation conversion solely
to identify whether archived IRI values behave as if curvature/slope were zero.
It is not a specification for the new science run and does not prove that
nonzero terrain fields were absent from an unknown historical staging table.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import xarray as xr
from scipy.spatial import cKDTree


def selected_old_rows(zip_path: Path, country: str, stride: int):
    member = f"road_speed_cordex/{country}_road_speed.csv"
    rows = []
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(member) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))
            for number, row in enumerate(reader):
                if number < 10 or number % stride == 0:
                    rows.append(row)
    return rows


def old_iri(monthly_precip_m: float) -> float:
    # Old parameters with kcv=0 and slope_pct=0.  MGD=0.5 nulls its term.
    target = max(21.4 - 32.4 * (0.5 - 0.5) ** 2, 12.0)
    rate = 0.461 + 0.0174 * 42 + 0.0114 * 8 - 0.0287 * 50 * monthly_precip_m
    p = np.exp(-0.001 * rate / 12)
    return float(target - p**12 * (target - 6.0))


def audit(climate_dir: Path, speed_zip: Path, country: str, stride: int):
    prefix = "AFR-44_MPI-M-MPI-ESM-LR_rcp45_r1i1p1_SMHI-RCA4_v1_mon_201101-202012.nc"
    with xr.open_dataset(climate_dir / f"pr_{prefix}", engine="netcdf4") as pds:
        pr = pds["pr"].load()
    with xr.open_dataset(climate_dir / f"mrso_{prefix}", engine="netcdf4") as mds:
        mrso = mds["mrso"].load()
    rows = selected_old_rows(speed_zip, country, stride)
    # Compute spatial mapping once for sampled roads. Use the archived latitude/
    # longitude grid, exactly as the old submitted script did.
    p_lat = np.asarray(pr.lat.values)
    p_lon = np.asarray(pr.lon.values)
    m_lat = np.asarray(mrso.lat.values)
    m_lon = np.asarray(mrso.lon.values)
    ptree = cKDTree(np.column_stack([p_lat.ravel(), p_lon.ravel()]))
    mtree = cKDTree(np.column_stack([m_lat.ravel(), m_lon.ravel()]))
    points = np.array(
        [[float(row["center_lat"]), float(row["center_lon"])] for row in rows]
    )
    _, p_index = ptree.query(points)
    _, m_index = mtree.query(points)
    p_r, p_c = np.unravel_index(p_index, p_lat.shape)
    m_r, m_c = np.unravel_index(m_index, m_lat.shape)
    pr_road = pr.values[:, p_r, p_c] * 86400 * 30
    soil_road = mrso.values[:, m_r, m_c]
    predicted_n = np.array([old_iri(v / 1000) for v in pr_road.mean(axis=0)])
    predicted_e = np.array(
        [old_iri(v / 1000) for v in np.percentile(pr_road, 95, axis=0)]
    )
    observed_n = np.array([float(row["IRI_normal"]) for row in rows])
    observed_e = np.array([float(row["IRI_extreme"]) for row in rows])
    abs_n = np.abs(predicted_n - observed_n)
    abs_e = np.abs(predicted_e - observed_e)
    return {
        "country": country,
        "sample_count": len(rows),
        "sample_road_ids_first_10": [row["road_id"] for row in rows[:10]],
        "max_abs_iri_normal": float(abs_n.max()),
        "max_abs_iri_extreme": float(abs_e.max()),
        "median_abs_iri_normal": float(np.median(abs_n)),
        "median_abs_iri_extreme": float(np.median(abs_e)),
        "matches_zero_terrain_at_1e_5": bool(
            np.all(abs_n < 1e-5) and np.all(abs_e < 1e-5)
        ),
        "old_precip_conversion": "fixed_30_day_month_forensic_only",
        "caveat": "This tests archived IRI against zero terrain at sample centroids; it cannot recover a missing historical staging table or endorse zero-terrain science.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--climate-dir", required=True, type=Path)
    parser.add_argument("--speed-zip", required=True, type=Path)
    parser.add_argument("--country", default="Kenya")
    parser.add_argument("--stride", type=int, default=10000)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.climate_dir, args.speed_zip, args.country, args.stride)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
