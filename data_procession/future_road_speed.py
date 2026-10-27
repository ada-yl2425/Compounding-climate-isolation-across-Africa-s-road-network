"""
future_road_speed.py
====================
Generates future road speed CSVs for robustness checks on bottleneck stability.

Mirrors the logic of data_procession/compute_road_speed.py but for a configurable
future year window instead of the 2011-2020 baseline.

Logic:
  - Load monthly pr and mrso from CORDEX NC files for the target period.
  - Compute V_normal  : HDM-4 IRI from mean precipitation,   mrso P75
  - Compute V_extreme : HDM-4 IRI from P95  precipitation,   mrso P95
  - Output format is identical to road_speed_cordex/ so bottleneck_network.py
    and bottleneck_stability.py can consume it without modification.

Usage:
    python data_procession/future_road_speed.py \\
        --base-dir <BASE_DIR> \\
        --gcm MPI-M-MPI-ESM-LR \\
        --rcp rcp26 \\
        --period 2040 \\
        --window 5

Outputs:
    <BASE_DIR>/road_speed_future/{gcm}_{rcp}_{period}/{Country}_road_speed.csv

NOTE: NC files must be accessible on the local filesystem. Remote-mounted
files can return OSError; download them first if that happens.
Available GCM/RCP combos in weather_data_raw/:
    MIROC-MIROC5  rcp26 / rcp45 / rcp85
    MPI-M-MPI-ESM-LR  rcp26 / rcp45 / rcp85
    NCC-NorESM1-M     rcp26 / rcp45 / rcp85
"""

import argparse
import gc
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from scipy.spatial import cKDTree
from tqdm import tqdm

warnings.filterwarnings("ignore")


_DEFAULT_BASE = Path("<BASE_DIR>")
RCM = "SMHI-RCA4"


HDM4_IRI_INIT = 6.0
HDM4_DT = 1 / 12
HDM4_ADT_U = 50
HDM4_ADL_U = 42
HDM4_ADH_U = 8
HDM4_MGD = 0.5

_R_NODES = np.array([6, 8, 10, 12, 14, 16, 18, 20], dtype=float)
_V_NODES = np.array([106, 80, 64, 53, 46, 40, 35, 32], dtype=float)

MRSO_PASSABLE_PERCENTILE = 75
MRSO_EXTREME_PERCENTILE = 95

PAVED_SPEED_NORMAL = 80.0
PAVED_SPEED_EXTREME = 65.0

ALL_COUNTRIES = [
    "Algeria",
    "Angola",
    "Benin",
    "Botswana",
    "BurkinaFaso",
    "Burundi",
    "Cameroon",
    "CentralAfrican",
    "Chad",
    "Congo",
    "CongoDR",
    "Djibouti",
    "Egypt",
    "Equatorial",
    "Eritrea",
    "Ethiopia",
    "Gabon",
    "Gambia",
    "Ghana",
    "Guinea",
    "GuineaBissau",
    "IvoryCoast",
    "Kenya",
    "Lesotho",
    "Liberia",
    "Libya",
    "Madagascar",
    "Malawi",
    "Mali",
    "Mauritania",
    "Morocco",
    "Mozambique",
    "Namibia",
    "Niger",
    "Nigeria",
    "Rwanda",
    "Senegal",
    "SierraLeone",
    "Somalia",
    "SouthAfrica",
    "SouthSudan",
    "Sudan",
    "Swaziland",
    "Tanzania",
    "Togo",
    "Tunisia",
    "Uganda",
    "WestSahara",
    "Zambia",
    "Zimbabwe",
]


def hdm4_unpaved_iri(mmp_m: float, kcv: float, slope_pct: float) -> float:
    rg_max = max(
        21.4 - 32.4 * (0.5 - HDM4_MGD) ** 2 + 0.97 * kcv - 7.64 * slope_pct * mmp_m,
        12.0,
    )
    p = np.exp(
        -0.001
        * (
            0.461
            + 0.0174 * HDM4_ADL_U
            + 0.0114 * HDM4_ADH_U
            - 0.0287 * HDM4_ADT_U * mmp_m
        )
        * HDM4_DT
    )
    rg = HDM4_IRI_INIT
    for _ in range(12):
        rg = rg_max - p * (rg_max - rg)
    return float(rg)


def iri_to_speed(iri: float) -> float:
    return float(np.interp(np.clip(iri, _R_NODES[0], _R_NODES[-1]), _R_NODES, _V_NODES))


def _find_nc_files(climate_dir: Path, var: str, gcm: str, rcp: str, freq: str, years):
    pattern = f"{var}_AFR-44_{gcm}_{rcp}_r1i1p1_{RCM}_v1_{freq}_*.nc"
    selected = []
    for f in sorted(climate_dir.glob(pattern)):
        tp = f.stem.split("_")[-1]
        try:
            sy = int(tp[:4])
            ey = int(tp[9:13]) if freq == "day" else int(tp[7:11])
        except (ValueError, IndexError):
            continue
        if any(sy <= y <= ey for y in years):
            selected.append(f)
    return sorted(selected)


def _load_monthly_pr(climate_dir, gcm, rcp, years):
    mon_files = _find_nc_files(climate_dir, "pr", gcm, rcp, "mon", years)
    if mon_files:
        chunks = []
        skipped = []
        for f in mon_files:
            try:
                ds = xr.open_dataset(str(f), engine="h5netcdf")
                da = (ds["pr"] * 86400 * 30).sel(time=ds["pr"].time.dt.year.isin(years))
                if len(da.time) > 0:
                    chunks.append(da.load())
                ds.close()
            except OSError as e:
                skipped.append(f.name)
        if skipped:
            print(
                f"    [WARN] Skipped unreadable files (not locally cached): {skipped}"
            )
        if not chunks:
            raise FileNotFoundError(
                f"No readable pr files for gcm={gcm} rcp={rcp}. Download the NC files first."
            )
        result = (
            xr.concat(chunks, dim="time").sortby("time")
            if len(chunks) > 1
            else chunks[0]
        )
        print(
            f"    pr: {len(result.time)} monthly steps loaded from {len(chunks)} file(s)"
        )
        return result
    day_files = _find_nc_files(climate_dir, "pr", gcm, rcp, "day", years)
    if not day_files:
        raise FileNotFoundError(
            f"No precipitation NC files found: gcm={gcm} rcp={rcp} years={list(years)[:3]}..."
        )
    print(f"    Aggregating daily → monthly ({len(day_files)} files)...")
    chunks = []
    for f in day_files:
        try:
            ds = xr.open_dataset(str(f), engine="h5netcdf")
            da = (ds["pr"] * 86400).sel(time=ds["pr"].time.dt.year.isin(years))
            if len(da.time) == 0:
                ds.close()
                continue
            chunks.append(da.resample(time="1MS").sum().load())
            ds.close()
        except OSError:
            print(f"    [WARN] Skipped: {f.name}")
    if not chunks:
        raise FileNotFoundError("No daily precipitation data for target years.")
    return xr.concat(chunks, dim="time").sortby("time")


def _load_monthly_mrso(climate_dir, gcm, rcp, years):
    mon_files = _find_nc_files(climate_dir, "mrso", gcm, rcp, "mon", years)
    if not mon_files:
        raise FileNotFoundError(f"No soil moisture NC files found: gcm={gcm} rcp={rcp}")
    chunks = []
    skipped = []
    for f in mon_files:
        try:
            ds = xr.open_dataset(str(f), engine="h5netcdf")
            da = ds["mrso"].sel(time=ds["mrso"].time.dt.year.isin(years))
            if len(da.time) > 0:
                chunks.append(da.load())
            ds.close()
        except OSError as e:
            skipped.append(f.name)
    if skipped:
        print(f"    [WARN] Skipped unreadable mrso files: {skipped}")
    if not chunks:
        raise FileNotFoundError(
            f"No readable mrso files for gcm={gcm} rcp={rcp}. Download the NC files first."
        )
    result = (
        xr.concat(chunks, dim="time").sortby("time") if len(chunks) > 1 else chunks[0]
    )
    print(
        f"    mrso: {len(result.time)} monthly steps loaded from {len(chunks)} file(s)"
    )
    return result


def _build_kdtree(da):
    if "lat" in da.coords and "lon" in da.coords:
        lats, lons = da["lat"].values, da["lon"].values
        if lats.ndim == 1:
            lons, lats = np.meshgrid(lons, lats)
        grid_shape = lats.shape
    else:
        rlat, rlon = da["rlat"].values, da["rlon"].values
        lons, lats = np.meshgrid(rlon, rlat)
        grid_shape = (da.sizes["rlat"], da.sizes["rlon"])
    tree = cKDTree(np.column_stack([lats.ravel(), lons.ravel()]))
    return tree, grid_shape


def _road_to_cell(lons, lats, tree, grid_shape):
    _, idx = tree.query(np.column_stack([lats, lons]))
    return np.unravel_index(idx, grid_shape)


def compute_future_speeds(roads_gdf: pd.DataFrame, da_pr, da_mrso) -> pd.DataFrame:
    tree_pr, shape_pr = _build_kdtree(da_pr)
    tree_mrso, shape_mrso = _build_kdtree(da_mrso)

    lons = roads_gdf["center_lon"].values
    lats = roads_gdf["center_lat"].values
    pr_r, pr_c = _road_to_cell(lons, lats, tree_pr, shape_pr)
    mrso_r, mrso_c = _road_to_cell(lons, lats, tree_mrso, shape_mrso)

    pr_road = da_pr.values[:, pr_r, pr_c]
    mrso_road = da_mrso.values[:, mrso_r, mrso_c]

    mmp_normal_mm = pr_road.mean(axis=0)
    mrso_p75 = np.percentile(mrso_road, MRSO_PASSABLE_PERCENTILE, axis=0)
    passable_normal = (mrso_road <= mrso_p75).mean(axis=0)

    mmp_extreme_mm = np.percentile(pr_road, MRSO_EXTREME_PERCENTILE, axis=0)
    mrso_p95 = np.percentile(mrso_road, MRSO_EXTREME_PERCENTILE, axis=0)
    ratio = np.where(mrso_p95 > mrso_p75, mrso_p75 / np.maximum(mrso_p95, 1e-6), 1.0)
    passable_extreme = passable_normal * ratio

    mmp_normal_m = mmp_normal_mm / 1000.0
    mmp_extreme_m = mmp_extreme_mm / 1000.0

    curvatures = (
        roads_gdf.get("curvature_deg_km", pd.Series(0.0, index=roads_gdf.index))
        .fillna(0)
        .values
    )
    slopes_deg = (
        roads_gdf.get("slope_deg", pd.Series(0.0, index=roads_gdf.index))
        .fillna(0)
        .values
    )

    results = []
    for i in tqdm(range(len(roads_gdf)), desc="  Roads", leave=False):
        kcv = float(curvatures[i])
        slope_pct = float(np.tan(np.radians(slopes_deg[i])) * 100)
        surf = str(roads_gdf.iloc[i].get("Surface", "unpaved")).lower()

        if "paved" in surf and "unpaved" not in surf:
            iri_n, v_n = None, PAVED_SPEED_NORMAL
            iri_e, v_e = None, PAVED_SPEED_EXTREME
            pr_n = 1.0
            pr_e = PAVED_SPEED_EXTREME / PAVED_SPEED_NORMAL
        else:
            iri_n = hdm4_unpaved_iri(mmp_normal_m[i], kcv, slope_pct)
            v_n = iri_to_speed(iri_n) * float(passable_normal[i])
            iri_e = hdm4_unpaved_iri(mmp_extreme_m[i], kcv, slope_pct)
            v_e = iri_to_speed(iri_e) * float(passable_extreme[i])
            pr_n = float(passable_normal[i])
            pr_e = float(passable_extreme[i])

        v_n = max(v_n, 0.5)
        v_e = max(v_e, 0.5)
        p_block = max(0.0, min(0.99, 1.0 - pr_e))

        results.append(
            {
                "road_id": roads_gdf.iloc[i]["road_id"],
                "Surface": roads_gdf.iloc[i].get("Surface", "unpaved"),
                "length_km": roads_gdf.iloc[i].get("length_km", 0.0),
                "center_lon": lons[i],
                "center_lat": lats[i],
                "IRI_normal": round(iri_n, 4) if iri_n is not None else None,
                "passable_rate_normal": round(pr_n, 4),
                "V_normal": round(v_n, 4),
                "IRI_extreme": round(iri_e, 4) if iri_e is not None else None,
                "passable_rate_extreme": round(pr_e, 4),
                "V_extreme": round(v_e, 4),
                "p_block": round(p_block, 4),
                "delta_V_pct": round((v_n - v_e) / v_n * 100, 4),
            }
        )
    return pd.DataFrame(results)


def load_roads(country: str, roads_dir: Path) -> pd.DataFrame:
    shp = roads_dir / country / f"{country}.shp"
    if not shp.exists():
        return None
    gdf = gpd.read_file(shp)
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    gdf["road_id"] = [f"{country}_road_{i}" for i in range(len(gdf))]
    gdf_m = gdf.to_crs("ESRI:102022")
    gdf["length_km"] = gdf_m.geometry.length / 1000
    gdf["center_lon"] = gdf.geometry.centroid.x
    gdf["center_lat"] = gdf.geometry.centroid.y
    surf_col = next(
        (c for c in ["Surface", "surface", "fclass"] if c in gdf.columns), None
    )
    if surf_col and surf_col != "Surface":
        gdf = gdf.rename(columns={surf_col: "Surface"})
    return gdf[gdf["length_km"] >= 0.1].reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Generate future road speed CSVs")
    parser.add_argument("--base-dir", required=True)
    parser.add_argument(
        "--climate-dir",
        default=None,
        help="Override climate NC directory (default: {base-dir}/RAW/Climate_data/weather_data_raw)",
    )
    parser.add_argument(
        "--gcm", default="MPI-M-MPI-ESM-LR", help="GCM name as used in NC filenames"
    )
    parser.add_argument("--rcp", default="rcp45", choices=["rcp26", "rcp45", "rcp85"])
    parser.add_argument(
        "--period", type=int, default=2040, help="Target year (2040, 2060, or 2080)"
    )
    parser.add_argument(
        "--window", type=int, default=5, help="Years ± around period to average over"
    )
    parser.add_argument(
        "--countries",
        nargs="*",
        default=None,
        help="Subset of countries (default: all 50)",
    )
    args = parser.parse_args()

    base = Path(args.base_dir)
    climate_dir = (
        Path(args.climate_dir)
        if args.climate_dir
        else base / "RAW" / "Climate_data" / "weather_data_raw"
    )
    roads_dir = base / "RAW" / "Road_data"
    out_dir = base / "road_speed_future" / f"{args.gcm}_{args.rcp}_{args.period}"
    out_dir.mkdir(parents=True, exist_ok=True)

    years = list(range(args.period - args.window, args.period + args.window + 1))
    countries = args.countries or ALL_COUNTRIES

    print(f"\n{'='*60}")
    print(f"  Future Road Speed — {args.gcm} {args.rcp} period={args.period}")
    print(f"  Year window: {years[0]}–{years[-1]}  ({len(years)} years)")
    print(f"  Countries: {len(countries)}")
    print(f"  Output: {out_dir}")
    print(f"{'='*60}\n")

    print("  Loading climate data...")
    try:
        da_pr = _load_monthly_pr(climate_dir, args.gcm, args.rcp, years)
        da_mrso = _load_monthly_mrso(climate_dir, args.gcm, args.rcp, years)
    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}")
        print("  NC files not found or not accessible.")
        print(
            "  Ensure weather_data_raw/ is locally accessible and contains files for:"
        )
        print(f"    var=pr/mrso  gcm={args.gcm}  rcp={args.rcp}  years~{args.period}")
        return

    print(
        f"  pr  : {da_pr.shape}  range=[{float(da_pr.min()):.1f}, {float(da_pr.max()):.1f}] mm/month"
    )
    print(
        f"  mrso: {da_mrso.shape}  range=[{float(da_mrso.min()):.1f}, {float(da_mrso.max()):.1f}] kg/m²"
    )

    ok, skipped = 0, []
    for country in countries:
        roads_gdf = load_roads(country, roads_dir)
        if roads_gdf is None or roads_gdf.empty:
            skipped.append(country)
            continue
        print(f"  {country:<20} {len(roads_gdf):>7,} segments ... ", end="", flush=True)
        try:
            df = compute_future_speeds(roads_gdf, da_pr, da_mrso)
            out_csv = out_dir / f"{country}_road_speed.csv"
            df.to_csv(out_csv, index=False)
            print(
                f"V_extreme mean={df['V_extreme'].mean():.1f}  p_block mean={df['p_block'].mean():.3f}"
            )
            ok += 1
        except Exception as e:
            print(f"ERROR: {e}")
            skipped.append(country)
        gc.collect()

    print(f"\n  Done. {ok} countries written to {out_dir}")
    if skipped:
        print(f"  Skipped: {skipped}")


if __name__ == "__main__":
    main()
