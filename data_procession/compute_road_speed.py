"""
compute_road_speed.py v2
==========================
Calculates V_normal and V_extreme for each unpaved road segment.

Logic Framework:
  - V_normal: Calculated using monthly mean precipitation + adaptive mrso threshold (P75).
  - V_extreme: Calculated using P95 monthly precipitation + P95 soil moisture impact.
  - Unpaved road speed: mmp(m/month) -> HDM-4 IRI -> V_base lookup -> V = V_base * passable_rate.
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

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_DIR = Path("path/to")
CLIMATE_DIR = BASE_DIR / "RAW/Climate_data"
ROADS_DIR = BASE_DIR / "RAW/Road_data"
OUTPUT_DIR = BASE_DIR / "road_speed_cordex"

GCM = "MPI-M-MPI-ESM-LR"
RCP = "rcp45"
RCM = "SMHI-RCA4"

BASELINE_YEARS = list(range(2011, 2021))

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

# =============================================================================
# PHYSICAL CONSTANTS
# =============================================================================
HDM4_IRI_INIT = 6.0
HDM4_DT = 1 / 12
HDM4_ADT_U = 50
HDM4_ADL_U = 42
HDM4_ADH_U = 8
HDM4_MGD = 0.5  # Mean gravel depth (m), not grading interval.

_R_NODES = np.array([6, 8, 10, 12, 14, 16, 18, 20], dtype=float)
_V_NODES = np.array([106, 80, 64, 53, 46, 40, 35, 32], dtype=float)

MRSO_PASSABLE_PERCENTILE = 75
MRSO_EXTREME_PERCENTILE = 95


# =============================================================================
# HDM-4 IRI
# =============================================================================
def hdm4_unpaved_iri(mmp_m, kcv, slope_pct, iri_start=HDM4_IRI_INIT):
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
    rg = iri_start
    for _ in range(12):
        rg = rg_max - p * (rg_max - rg)
    return float(rg)


def iri_to_speed(iri):
    return float(np.interp(np.clip(iri, _R_NODES[0], _R_NODES[-1]), _R_NODES, _V_NODES))


# =============================================================================
# NETCDF DATA HANDLING
# =============================================================================
def find_nc_files(var, gcm, rcp, rcm, freq, years):
    pattern = f"{var}_AFR-44_{gcm}_{rcp}_r1i1p1_{rcm}_v1_{freq}_*.nc"
    selected = []
    for f in sorted(CLIMATE_DIR.glob(pattern)):
        tp = f.stem.split("_")[-1]
        try:
            sy = int(tp[:4])
            ey = int(tp[9:13]) if freq == "day" else int(tp[7:11])
        except (ValueError, IndexError):
            continue
        if any(sy <= y <= ey for y in years):
            selected.append(f)
    return sorted(selected)


def load_monthly_pr(gcm, rcp, rcm, years):
    mon_files = find_nc_files("pr", gcm, rcp, rcm, "mon", years)
    if mon_files:
        ds = xr.open_mfdataset(mon_files, combine="by_coords", engine="h5netcdf")
        da = ds["pr"] * 86400 * 30
        return da.sel(time=da.time.dt.year.isin(years)).load()

    day_files = find_nc_files("pr", gcm, rcp, rcm, "day", years)
    if not day_files:
        raise FileNotFoundError(f"Precipitation data not found: {gcm} {rcp}")
    print(f"    Aggregating daily to monthly ({len(day_files)} files)...")
    chunks = []
    for f in day_files:
        ds = xr.open_dataset(f, engine="h5netcdf")
        da = (ds["pr"] * 86400).sel(time=ds["pr"].time.dt.year.isin(years))
        if len(da.time) == 0:
            ds.close()
            continue
        chunks.append(da.resample(time="1MS").sum().load())
        ds.close()
    if not chunks:
        raise FileNotFoundError("No daily precipitation data for target years.")
    return xr.concat(chunks, dim="time").sortby("time")


def load_monthly_mrso(gcm, rcp, rcm, years):
    mon_files = find_nc_files("mrso", gcm, rcp, rcm, "mon", years)
    if not mon_files:
        raise FileNotFoundError(f"Soil moisture data not found: {gcm} {rcp}")
    ds = xr.open_mfdataset(mon_files, combine="by_coords", engine="h5netcdf")
    return ds["mrso"].sel(time=ds["mrso"].time.dt.year.isin(years)).load()


def build_kdtree(da):
    if "lat" in da.coords and "lon" in da.coords:
        lats = da["lat"].values
        lons = da["lon"].values
        if lats.ndim == 1:
            lons, lats = np.meshgrid(lons, lats)
    else:
        rlon, rlat = da["rlon"].values, da["rlat"].values
        lons, lats = np.meshgrid(rlon, rlat)
    grid_shape = (da.sizes["rlat"], da.sizes["rlon"])
    tree = cKDTree(np.column_stack([lats.ravel(), lons.ravel()]))
    return tree, grid_shape


def road_to_cell(lons, lats, tree, grid_shape):
    _, idx = tree.query(np.column_stack([lats, lons]))
    return np.unravel_index(idx, grid_shape)


# =============================================================================
# CORE COMPUTATION
# =============================================================================
def compute_both_scenarios(roads_gdf, da_pr, da_mrso):
    """
    Computes normal (mean) and extreme (P95) scenarios simultaneously.
    If P95 soil moisture exceeds P75 threshold, the passable rate decays proportionally.
    """
    print("  Building KD trees...")
    tree_pr, shape_pr = build_kdtree(da_pr)
    tree_mrso, shape_mrso = build_kdtree(da_mrso)

    lons = roads_gdf["center_lon"].values
    lats = roads_gdf["center_lat"].values
    pr_r, pr_c = road_to_cell(lons, lats, tree_pr, shape_pr)
    mrso_r, mrso_c = road_to_cell(lons, lats, tree_mrso, shape_mrso)

    pr_road = da_pr.values[:, pr_r, pr_c]
    mrso_road = da_mrso.values[:, mrso_r, mrso_c]

    # Normal Scenario
    mmp_normal_mm = pr_road.mean(axis=0)
    mrso_p75 = np.percentile(mrso_road, MRSO_PASSABLE_PERCENTILE, axis=0)
    passable_normal = (mrso_road <= mrso_p75).mean(axis=0)

    # Extreme Scenario
    mmp_extreme_mm = np.percentile(pr_road, MRSO_EXTREME_PERCENTILE, axis=0)
    mrso_p95 = np.percentile(mrso_road, MRSO_EXTREME_PERCENTILE, axis=0)

    ratio = np.where(mrso_p95 > mrso_p75, mrso_p75 / np.maximum(mrso_p95, 1e-6), 1.0)
    passable_extreme = passable_normal * ratio

    mmp_normal_m = mmp_normal_mm / 1000.0
    mmp_extreme_m = mmp_extreme_mm / 1000.0

    print(f"  Calculating IRI and speed ({len(roads_gdf):,} segments)...")
    results = []
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
    road_ids = roads_gdf["road_id"].values

    for i in tqdm(range(len(roads_gdf)), desc="  Roads", leave=False):
        kcv = float(curvatures[i])
        slope_pct = float(np.tan(np.radians(slopes_deg[i])) * 100)

        iri_n = hdm4_unpaved_iri(mmp_normal_m[i], kcv, slope_pct)
        v_n = iri_to_speed(iri_n) * float(passable_normal[i])

        iri_e = hdm4_unpaved_iri(mmp_extreme_m[i], kcv, slope_pct)
        v_e = iri_to_speed(iri_e) * float(passable_extreme[i])

        results.append(
            {
                "road_id": road_ids[i],
                "IRI_normal": iri_n,
                "passable_rate_normal": float(passable_normal[i]),
                "V_normal": v_n,
                "IRI_extreme": iri_e,
                "passable_rate_extreme": float(passable_extreme[i]),
                "V_extreme": v_e,
            }
        )

    return pd.DataFrame(results)


# =============================================================================
# ROAD NETWORK PROCESSING
# =============================================================================
def load_roads(country):
    shp = ROADS_DIR / country / f"{country}.shp"
    if not shp.exists():
        raise FileNotFoundError(f"Shapefile does not exist: {shp}")

    roads = gpd.read_file(shp)
    roads["road_id"] = [f"{country}_road_{i}" for i in range(len(roads))]

    if roads.crs is None or roads.crs.to_epsg() != 4326:
        roads = roads.to_crs("EPSG:4326")

    roads_m = roads.to_crs("ESRI:102022")
    roads["length_km"] = roads_m.geometry.length / 1000
    roads["center_lon"] = roads.geometry.centroid.x
    roads["center_lat"] = roads.geometry.centroid.y

    surf_col = next(
        (c for c in ["Surface", "surface", "fclass", "highway"] if c in roads.columns),
        None,
    )

    if surf_col:
        roads = roads[
            roads[surf_col].str.lower().str.contains("unpaved", na=False)
        ].copy()
        roads = roads.rename(columns={surf_col: "Surface"})
    else:
        roads["Surface"] = "unpaved"

    roads = roads[roads["length_km"] >= 0.05].reset_index(drop=True)
    if "slope_deg" not in roads.columns:
        roads["slope_deg"] = 0.0
    if "curvature_deg_km" not in roads.columns:
        roads["curvature_deg_km"] = 0.0

    print(f"  Unpaved segments: {len(roads):,}")
    return roads


# =============================================================================
# MAIN ORCHESTRATION
# =============================================================================
def process_country(country):
    print(f"\n{'=' * 60}")
    print(f"  Processing country: {country}")
    print(
        f"  Scenario: Normal vs Extreme (P95), Baseline {BASELINE_YEARS[0]}-{BASELINE_YEARS[-1]}"
    )
    print(f"{'=' * 60}")

    try:
        roads = load_roads(country)
    except FileNotFoundError as e:
        print(f"  [Skip] {e}")
        return pd.DataFrame()

    if roads.empty:
        print("  [Skip] No unpaved segments found.")
        return pd.DataFrame()

    print(f"\n  Loading climate data ({BASELINE_YEARS[0]}-{BASELINE_YEARS[-1]})...")
    try:
        da_pr = load_monthly_pr(GCM, RCP, RCM, BASELINE_YEARS)
        da_mrso = load_monthly_mrso(GCM, RCP, RCM, BASELINE_YEARS)

        t0 = str(da_pr.time.values[0])[:7]
        t1 = str(da_pr.time.values[-1])[:7]
        print(f"  pr:   {t0} -> {t1}  ({len(da_pr.time)} months)")

        t0m = str(da_mrso.time.values[0])[:7]
        t1m = str(da_mrso.time.values[-1])[:7]
        print(f"  mrso: {t0m} -> {t1m}  ({len(da_mrso.time)} months)")
    except FileNotFoundError as e:
        print(f"  [Error] {e}")
        return pd.DataFrame()

    print("\n  Computing dual-scenario speeds...")
    df_speeds = compute_both_scenarios(roads, da_pr, da_mrso)

    df = roads[["road_id", "Surface", "length_km", "center_lon", "center_lat"]].copy()
    df = df.merge(df_speeds, on="road_id", how="left")

    df["p_block"] = (1.0 - df["passable_rate_extreme"]).clip(0, 0.99)
    df["delta_V_pct"] = np.where(
        df["V_normal"] > 0,
        (df["V_normal"] - df["V_extreme"]) / df["V_normal"] * 100,
        np.nan,
    )

    valid = df.dropna(subset=["delta_V_pct"])
    n_slower = (valid["delta_V_pct"] > 0).sum()

    print("\n  -- Results Summary --")
    print(f"  Total segments:          {len(df):,}")
    print(f"  V_normal mean:           {df['V_normal'].mean():.2f} km/h")
    print(f"  V_extreme mean:          {df['V_extreme'].mean():.2f} km/h")
    print(f"  delta_V_pct mean:        {valid['delta_V_pct'].mean():.2f}%")
    print(
        f"  Slower under extreme:    {n_slower:,} ({n_slower / len(valid) * 100:.1f}%)"
    )
    print(f"  passable_normal mean:    {df['passable_rate_normal'].mean():.3f}")
    print(f"  passable_extreme mean:   {df['passable_rate_extreme'].mean():.3f}")
    print(f"  p_block > 0.2:           {(df['p_block'] > 0.2).sum():,}")

    del da_pr, da_mrso
    gc.collect()

    return df


def main():
    parser = argparse.ArgumentParser(
        description="Compute V_normal and V_extreme for unpaved roads."
    )
    parser.add_argument("--country", nargs="+", help="Target country or countries.")
    parser.add_argument("--all", action="store_true", help="Process all countries.")
    parser.add_argument("--output_dir", type=str, default=None)
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing output files."
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.all:
        countries = ALL_COUNTRIES
    elif args.country:
        countries = args.country
    else:
        print("Please specify --country or --all")
        print("Example: python compute_road_speed.py --country Ghana")
        return

    print(f"\nTarget Countries: {countries}")
    print(
        f"GCM/RCP: {GCM} / {RCP}   Baseline: {BASELINE_YEARS[0]}-{BASELINE_YEARS[-1]}"
    )
    print(f"Output Directory: {out_dir}")

    success, failed = [], []
    for country in countries:
        out_path = out_dir / f"{country}_road_speed.csv"

        if out_path.exists() and not args.overwrite:
            print(f"\n  [Skip] {country}: Output exists (use --overwrite to force).")
            success.append(country)
            continue

        try:
            df = process_country(country)
            if df.empty:
                failed.append(country)
                continue

            df.to_csv(out_path, index=False)
            print(f"\n  ✓ Saved: {out_path.name}  ({len(df):,} segments)")
            success.append(country)

        except Exception as e:
            print(f"\n  ✗ {country}: {e}")
            import traceback

            traceback.print_exc()
            failed.append(country)
        finally:
            gc.collect()

    print(f"\n{'=' * 60}")
    print(f"  Completed: {len(success)}/{len(countries)}")
    if failed:
        print(f"  Failed: {failed}")
    print(f"  Output Directory: {out_dir}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
