"""
prepare_city_layer.py
=====================
Layer 1: District-level data preparation.

Logic Framework:
  1. Load road network shapefile and speed CSV by country.
  2. Perform spatial intersection using GADM level-2 administrative boundaries.
  3. Generate independent shapefiles and speed CSVs for each district.
  4. Skip districts with fewer than MIN_ROADS valid segments.
"""

import argparse
import warnings
from pathlib import Path

import geopandas as gpd
import pandas as pd

warnings.filterwarnings("ignore")

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_DIR = Path("path/to")
ROADS_DIR = BASE_DIR / "RAW/Road_data"
SPEED_DIR = BASE_DIR / "road_speed_cordex"
GADM_DIR = BASE_DIR / "RAW/GADM_admin"
OUTPUT_DIR = BASE_DIR / "web/city_layer"

MIN_ROAD_LENGTH_KM = 0.1
MIN_ROADS = 5
SURFACE_FILTER = "unpaved"

FOLDER_TO_ISO = {
    "Algeria": "DZA",
    "Angola": "AGO",
    "Benin": "BEN",
    "Botswana": "BWA",
    "BurkinaFaso": "BFA",
    "Burundi": "BDI",
    "Cameroon": "CMR",
    "CentralAfrican": "CAF",
    "Chad": "TCD",
    "Congo": "COG",
    "CongoDR": "COD",
    "Djibouti": "DJI",
    "Egypt": "EGY",
    "Equatorial": "GNQ",
    "Eritrea": "ERI",
    "Ethiopia": "ETH",
    "Gabon": "GAB",
    "Gambia": "GMB",
    "Ghana": "GHA",
    "Guinea": "GIN",
    "GuineaBissau": "GNB",
    "IvoryCoast": "CIV",
    "Kenya": "KEN",
    "Lesotho": "LSO",
    "Liberia": "LBR",
    "Libya": "LBY",
    "Madagascar": "MDG",
    "Malawi": "MWI",
    "Mali": "MLI",
    "Mauritania": "MRT",
    "Morocco": "MAR",
    "Mozambique": "MOZ",
    "Namibia": "NAM",
    "Niger": "NER",
    "Nigeria": "NGA",
    "Rwanda": "RWA",
    "Senegal": "SEN",
    "SierraLeone": "SLE",
    "Somalia": "SOM",
    "SouthAfrica": "ZAF",
    "SouthSudan": "SSD",
    "Sudan": "SDN",
    "Swaziland": "SWZ",
    "Tanzania": "TZA",
    "Togo": "TGO",
    "Tunisia": "TUN",
    "Uganda": "UGA",
    "WestSahara": "ESH",
    "Zambia": "ZMB",
    "Zimbabwe": "ZWE",
}

ALL_COUNTRIES = list(FOLDER_TO_ISO.keys())


def safe_id(gid: str) -> str:
    """Remove special characters from GADM ID for safe filenames."""
    return gid.replace(".", "_").replace("-", "_")


def process_country(country: str):
    iso = FOLDER_TO_ISO[country]
    shp_path = ROADS_DIR / country / f"{country}.shp"
    speed_path = SPEED_DIR / f"{country}_road_speed.csv"
    gadm_path = GADM_DIR / f"gadm41_{iso}" / f"gadm41_{iso}_2.shp"

    if not shp_path.exists():
        print(f"  [SKIP] Shapefile not found: {shp_path}")
        return
    if not speed_path.exists():
        print(f"  [SKIP] Speed CSV not found: {speed_path}")
        return
    if not gadm_path.exists():
        gadm_path_l1 = GADM_DIR / f"gadm41_{iso}" / f"gadm41_{iso}_1.shp"
        if gadm_path_l1.exists():
            gadm_path = gadm_path_l1
            print(
                f"  [INFO] Level-2 not found, falling back to level-1: {gadm_path_l1.name}"
            )
        else:
            print(f"  [SKIP] GADM level-2/1 not found: {gadm_path}")
            return

    print(f"\n{'=' * 55}")
    print(f"  {country} ({iso})")
    print(f"{'=' * 55}")

    roads = gpd.read_file(shp_path)
    if roads.crs is None or roads.crs.to_epsg() != 4326:
        roads = roads.to_crs("EPSG:4326")
    print(f"  Original segments: {len(roads):,}")

    roads["_orig_road_id"] = [f"{country}_road_{i}" for i in range(len(roads))]

    surf_col = next(
        (c for c in ["Surface", "surface", "fclass", "highway"] if c in roads.columns),
        None,
    )
    if surf_col:
        roads = roads[
            roads[surf_col].str.lower().str.contains(SURFACE_FILTER, na=False)
        ].copy()
        roads = roads.rename(columns={surf_col: "Surface"})
    else:
        roads["Surface"] = SURFACE_FILTER

    roads_m = roads.to_crs("ESRI:102022")
    roads["length_km"] = roads_m.geometry.length / 1000
    roads = roads[roads["length_km"] >= MIN_ROAD_LENGTH_KM].copy()
    roads = roads.reset_index(drop=True)
    print(f"  Filtered segments: {len(roads):,}")

    if roads.empty:
        print("  [SKIP] No valid road segments")
        return

    speed_df = pd.read_csv(speed_path)
    speed_lookup = speed_df.set_index("road_id").to_dict("index")
    print(f"  Speed CSV segments: {len(speed_df):,}")

    gadm = gpd.read_file(gadm_path).to_crs("EPSG:4326")
    if "GID_2" in gadm.columns:
        gid_col, name_col, prov_col = "GID_2", "NAME_2", "NAME_1"
    else:
        gid_col, name_col, prov_col = "GID_1", "NAME_1", "NAME_1"
    print(f"  Districts: {len(gadm):,}")

    # Spatial assignment based on road segment centroids
    centroids = roads.copy()
    centroids["geometry"] = roads.geometry.centroid
    gadm_cols = list(dict.fromkeys([gid_col, name_col, prov_col, "geometry"]))
    joined = gpd.sjoin(
        centroids[["_orig_road_id", "geometry"]],
        gadm[gadm_cols],
        how="left",
        predicate="within",
    )
    joined = joined[~joined.index.duplicated(keep="first")]
    roads["_district_gid"] = joined[gid_col]
    roads["_district_name"] = joined[name_col]
    roads["_province_name"] = joined[prov_col]

    # Map outer segments to nearest district
    missing_mask = roads["_district_gid"].isna()
    if missing_mask.sum() > 0:
        gadm_cents = gadm.copy()
        gadm_cents["geometry"] = gadm.geometry.centroid
        for idx in roads.index[missing_mask]:
            pt = roads.at[idx, "geometry"].centroid
            dists = gadm_cents.geometry.distance(pt)
            nearest = gadm.iloc[dists.idxmin()]
            roads.at[idx, "_district_gid"] = nearest[gid_col]
            roads.at[idx, "_district_name"] = nearest[name_col]
            roads.at[idx, "_province_name"] = nearest[prov_col]

    country_out = OUTPUT_DIR / country
    n_done = 0
    n_skip = 0

    for gid, grp in roads.groupby("_district_gid"):
        grp = grp.reset_index(drop=True)
        if len(grp) < MIN_ROADS:
            n_skip += 1
            continue

        sid = safe_id(str(gid))
        dist_dir = country_out / sid
        dist_dir.mkdir(parents=True, exist_ok=True)

        grp["road_id"] = [f"{sid}_road_{i}" for i in range(len(grp))]

        speed_rows = []
        for j, row in grp.iterrows():
            orig_id = row["_orig_road_id"]
            sp = speed_lookup.get(orig_id, {})
            speed_rows.append(
                {
                    "road_id": row["road_id"],
                    "Surface": row.get("Surface", SURFACE_FILTER),
                    "length_km": row["length_km"],
                    "center_lon": row.geometry.centroid.x,
                    "center_lat": row.geometry.centroid.y,
                    "IRI_normal": sp.get("IRI_normal", float("nan")),
                    "passable_rate_normal": sp.get("passable_rate_normal", 0.75),
                    "V_normal": sp.get("V_normal", float("nan")),
                    "IRI_extreme": sp.get("IRI_extreme", float("nan")),
                    "passable_rate_extreme": sp.get("passable_rate_extreme", 0.65),
                    "V_extreme": sp.get("V_extreme", float("nan")),
                    "p_block": sp.get("p_block", 0.0),
                    "delta_V_pct": sp.get("delta_V_pct", 0.0),
                }
            )
        speed_out = pd.DataFrame(speed_rows)

        out_cols = [
            "road_id",
            "Surface",
            "length_km",
            "_district_name",
            "_province_name",
            "geometry",
        ]
        out_cols = [c for c in out_cols if c in grp.columns]
        shp_out = grp[out_cols].copy()
        shp_out = shp_out.rename(
            columns={"_district_name": "dist_name", "_province_name": "prov_name"}
        )
        shp_out.to_file(dist_dir / f"{sid}.shp")
        speed_out.to_csv(dist_dir / f"{sid}_speed.csv", index=False)
        n_done += 1

    print(f"  Exported districts: {n_done}, Skipped (<{MIN_ROADS} segments): {n_skip}")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--country", nargs="+", help="Country folder names")
    group.add_argument("--all", action="store_true", help="Process all 50 countries")
    args = parser.parse_args()

    countries = ALL_COUNTRIES if args.all else args.country
    for c in countries:
        if c not in FOLDER_TO_ISO:
            print(f"[ERROR] Unknown country: {c}")
            continue
        process_country(c)

    print("\nCompleted.")
    print(f"Output Directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
