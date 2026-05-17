"""
prepare_country_layer.py
========================
Layer 2: Country-level node preparation.

Logic Framework:
  Extracts key city points for each country from ne_10m_populated_places.
  Hierarchical classification: national_capital / provincial_capital / major_city.
  This step does not interact with the road network directly. Spatial snapping
  to the road network is handled during the pipeline runtime.
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
BASE_DIR = Path("path/to/your/base/directory")
NE_PATH = BASE_DIR / "RAW/ne_10m_populated_places/ne_10m_populated_places.shp"
OUTPUT_DIR = BASE_DIR / "web/country_layer"

POP_THRESHOLD_DEFAULT = 100_000

FOLDER_TO_NE = {
    "Algeria": "Algeria",
    "Angola": "Angola",
    "Benin": "Benin",
    "Botswana": "Botswana",
    "BurkinaFaso": "Burkina Faso",
    "Burundi": "Burundi",
    "Cameroon": "Cameroon",
    "CentralAfrican": "Central African Republic",
    "Chad": "Chad",
    "Congo": "Congo (Brazzaville)",
    "CongoDR": "Congo (Kinshasa)",
    "Djibouti": "Djibouti",
    "Egypt": "Egypt",
    "Equatorial": "Equatorial Guinea",
    "Eritrea": "Eritrea",
    "Ethiopia": "Ethiopia",
    "Gabon": "Gabon",
    "Gambia": "The Gambia",
    "Ghana": "Ghana",
    "Guinea": "Guinea",
    "GuineaBissau": "Guinea Bissau",
    "IvoryCoast": "Ivory Coast",
    "Kenya": "Kenya",
    "Lesotho": "Lesotho",
    "Liberia": "Liberia",
    "Libya": "Libya",
    "Madagascar": "Madagascar",
    "Malawi": "Malawi",
    "Mali": "Mali",
    "Mauritania": "Mauritania",
    "Morocco": "Morocco",
    "Mozambique": "Mozambique",
    "Namibia": "Namibia",
    "Niger": "Niger",
    "Nigeria": "Nigeria",
    "Rwanda": "Rwanda",
    "Senegal": "Senegal",
    "SierraLeone": "Sierra Leone",
    "Somalia": "Somalia",
    "SouthAfrica": "South Africa",
    "SouthSudan": "South Sudan",
    "Sudan": "Sudan",
    "Swaziland": "eSwatini",
    "Tanzania": "Tanzania",
    "Togo": "Togo",
    "Tunisia": "Tunisia",
    "Uganda": "Uganda",
    "WestSahara": "Western Sahara",
    "Zambia": "Zambia",
    "Zimbabwe": "Zimbabwe",
}

NATIONAL_CAP_CLASSES = {"Admin-0 capital", "Admin-0 capital alt"}
PROVINCIAL_CAP_CLASSES = {"Admin-1 capital", "Admin-1 region capital"}


def classify_level(row, pop_threshold: int) -> str:
    fc = row["FEATURECLA"]
    if fc in NATIONAL_CAP_CLASSES:
        return "national_capital"
    if fc in PROVINCIAL_CAP_CLASSES:
        return "provincial_capital"
    if row["POP_MAX"] >= pop_threshold:
        return "major_city"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pop-threshold",
        type=int,
        default=POP_THRESHOLD_DEFAULT,
        help="Minimum population for a major_city (default 100,000)",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading ne_10m_populated_places ...")
    gdf = gpd.read_file(NE_PATH)
    print(f"  Total global cities: {len(gdf):,}")

    all_rows = []

    for folder, ne_name in FOLDER_TO_NE.items():
        subset = gdf[gdf["ADM0NAME"] == ne_name].copy()
        if subset.empty:
            print(f"  [WARN] {folder} ({ne_name}) has no city data")
            continue

        rows = []
        for _, row in subset.iterrows():
            level = classify_level(row, args.pop_threshold)
            if level is None:
                continue
            rows.append(
                {
                    "country_folder": folder,
                    "city_name": row["NAME"],
                    "level": level,
                    "adm1_name": row.get("ADM1NAME", ""),
                    "lon": row["LONGITUDE"],
                    "lat": row["LATITUDE"],
                    "pop_max": int(row["POP_MAX"]),
                }
            )

        if not rows:
            print(f"  [WARN] {folder}: No eligible cities found")
            continue

        df = pd.DataFrame(rows)
        level_order = {
            "national_capital": 0,
            "provincial_capital": 1,
            "major_city": 2,
        }
        df["_lrank"] = df["level"].map(level_order)
        df = df.sort_values("_lrank").drop_duplicates(subset="city_name", keep="first")
        df = df.drop(columns="_lrank").reset_index(drop=True)

        df = df.sort_values(["level", "city_name"]).reset_index(drop=True)
        out_path = OUTPUT_DIR / f"{folder}_city_nodes.csv"
        df.to_csv(out_path, index=False)

        n_cap = (df["level"] == "national_capital").sum()
        n_prov = (df["level"] == "provincial_capital").sum()
        n_maj = (df["level"] == "major_city").sum()
        print(
            f"  {folder}: {n_cap} Nat Cap, {n_prov} Prov Cap, {n_maj} Major -> {out_path.name}"
        )
        all_rows.append(df)

    if all_rows:
        merged = pd.concat(all_rows, ignore_index=True)
        merged_path = OUTPUT_DIR / "all_city_nodes.csv"
        merged.to_csv(merged_path, index=False)
        print(f"\nMerged file: {merged_path}")
        print(f"  Total city nodes:     {len(merged):,}")
        print(
            f"  National capitals:    {(merged['level'] == 'national_capital').sum()}"
        )
        print(
            f"  Provincial capitals:  {(merged['level'] == 'provincial_capital').sum()}"
        )
        print(f"  Major cities:         {(merged['level'] == 'major_city').sum()}")

    print(f"\nComplete. Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
