"""
prepare_africa_layer.py
=======================
Layer 3: Africa-level node preparation.

Logic Framework:
  Extracts core O-D nodes for the entire continent from ne_10m_populated_places.
  Categories included:
    1. National capitals (Admin-0 capital).
    2. Megacities (MEGACITY == 1) excluding existing capitals.
  These nodes form the foundation for continent-wide accessibility matrix computation.
"""

import warnings
from pathlib import Path

import geopandas as gpd
import pandas as pd

warnings.filterwarnings("ignore")


BASE_DIR = Path("path/to/your/base/directory")
NE_PATH = BASE_DIR / "RAW/ne_10m_populated_places/ne_10m_populated_places.shp"
OUTPUT_DIR = BASE_DIR / "web/africa_layer"

FOLDER_META = {
    "Algeria": ("Algeria", "DZA"),
    "Angola": ("Angola", "AGO"),
    "Benin": ("Benin", "BEN"),
    "Botswana": ("Botswana", "BWA"),
    "BurkinaFaso": ("Burkina Faso", "BFA"),
    "Burundi": ("Burundi", "BDI"),
    "Cameroon": ("Cameroon", "CMR"),
    "CentralAfrican": ("Central African Republic", "CAF"),
    "Chad": ("Chad", "TCD"),
    "Congo": ("Congo (Brazzaville)", "COG"),
    "CongoDR": ("Congo (Kinshasa)", "COD"),
    "Djibouti": ("Djibouti", "DJI"),
    "Egypt": ("Egypt", "EGY"),
    "Equatorial": ("Equatorial Guinea", "GNQ"),
    "Eritrea": ("Eritrea", "ERI"),
    "Ethiopia": ("Ethiopia", "ETH"),
    "Gabon": ("Gabon", "GAB"),
    "Gambia": ("The Gambia", "GMB"),
    "Ghana": ("Ghana", "GHA"),
    "Guinea": ("Guinea", "GIN"),
    "GuineaBissau": ("Guinea Bissau", "GNB"),
    "IvoryCoast": ("Ivory Coast", "CIV"),
    "Kenya": ("Kenya", "KEN"),
    "Lesotho": ("Lesotho", "LSO"),
    "Liberia": ("Liberia", "LBR"),
    "Libya": ("Libya", "LBY"),
    "Madagascar": ("Madagascar", "MDG"),
    "Malawi": ("Malawi", "MWI"),
    "Mali": ("Mali", "MLI"),
    "Mauritania": ("Mauritania", "MRT"),
    "Morocco": ("Morocco", "MAR"),
    "Mozambique": ("Mozambique", "MOZ"),
    "Namibia": ("Namibia", "NAM"),
    "Niger": ("Niger", "NER"),
    "Nigeria": ("Nigeria", "NGA"),
    "Rwanda": ("Rwanda", "RWA"),
    "Senegal": ("Senegal", "SEN"),
    "SierraLeone": ("Sierra Leone", "SLE"),
    "Somalia": ("Somalia", "SOM"),
    "SouthAfrica": ("South Africa", "ZAF"),
    "SouthSudan": ("South Sudan", "SSD"),
    "Sudan": ("Sudan", "SDN"),
    "Swaziland": ("eSwatini", "SWZ"),
    "Tanzania": ("Tanzania", "TZA"),
    "Togo": ("Togo", "TGO"),
    "Tunisia": ("Tunisia", "TUN"),
    "Uganda": ("Uganda", "UGA"),
    "WestSahara": ("Western Sahara", "ESH"),
    "Zambia": ("Zambia", "ZMB"),
    "Zimbabwe": ("Zimbabwe", "ZWE"),
}

NE_NAMES = {v[0] for v in FOLDER_META.values()}
NE_TO_FOLDER = {v[0]: k for k, v in FOLDER_META.items()}
NE_TO_ISO = {v[0]: v[1] for v in FOLDER_META.values()}

CAPITAL_CLASSES = {"Admin-0 capital", "Admin-0 capital alt"}


def load_africa(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return gdf[gdf["ADM0NAME"].isin(NE_NAMES)].copy()


def extract_capitals(africa: gpd.GeoDataFrame) -> pd.DataFrame:
    print("Extracting national capitals...")
    rows = []
    for _, row in africa[africa["FEATURECLA"].isin(CAPITAL_CLASSES)].iterrows():
        ne_name = row["ADM0NAME"]
        iso3 = NE_TO_ISO.get(ne_name, "")
        rows.append(
            {
                "node_id": f"{iso3}_capital",
                "name": row["NAME"],
                "type": "capital",
                "country_folder": NE_TO_FOLDER.get(ne_name, ""),
                "iso3": iso3,
                "lon": float(row["LONGITUDE"]),
                "lat": float(row["LATITUDE"]),
                "pop_max": int(row["POP_MAX"]),
            }
        )

    df = pd.DataFrame(rows)
    df["_rank"] = df["node_id"].apply(lambda x: 0 if not x.endswith("_alt") else 1)
    df = (
        df.sort_values(["iso3", "_rank"])
        .drop_duplicates(subset="iso3", keep="first")
        .drop(columns="_rank")
        .reset_index(drop=True)
    )
    print(f"  Found {len(df)} national capitals")
    return df


def extract_megacities(africa: gpd.GeoDataFrame, capital_names: set) -> pd.DataFrame:
    print("Extracting non-capital megacities...")
    mega = africa[
        (africa["MEGACITY"] == 1) & (~africa["NAME"].isin(capital_names))
    ].copy()

    rows = []
    for _, row in mega.iterrows():
        ne_name = row["ADM0NAME"]
        iso3 = NE_TO_ISO.get(ne_name, "")
        name = row["NAME"]
        rows.append(
            {
                "node_id": f"megacity_{name.replace(' ', '_')}",
                "name": name,
                "type": "megacity",
                "country_folder": NE_TO_FOLDER.get(ne_name, ""),
                "iso3": iso3,
                "lon": float(row["LONGITUDE"]),
                "lat": float(row["LATITUDE"]),
                "pop_max": int(row["POP_MAX"]),
            }
        )

    df = (
        pd.DataFrame(rows)
        .sort_values("pop_max", ascending=False)
        .reset_index(drop=True)
    )
    print(f"  Found {len(df)} non-capital megacities")
    return df


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    gdf = gpd.read_file(NE_PATH)
    africa = load_africa(gdf)

    capitals = extract_capitals(africa)
    cap_path = OUTPUT_DIR / "africa_capitals.csv"
    capitals.to_csv(cap_path, index=False)
    print(f"  Saved: {cap_path.name}")

    capital_names = set(capitals["name"])
    megacities = extract_megacities(africa, capital_names)
    mega_path = OUTPUT_DIR / "africa_megacities.csv"
    megacities.to_csv(mega_path, index=False)
    print(f"  Saved: {mega_path.name}")
    print("  Megacity list:")
    for _, r in megacities.iterrows():
        print(f"    {r['name']:20s} ({r['iso3']})  pop={r['pop_max']:,}")

    merged = pd.concat([capitals, megacities], ignore_index=True)
    merged_path = OUTPUT_DIR / "africa_nodes.csv"
    merged.to_csv(merged_path, index=False)

    print(f"\nMerged node file: {merged_path.name}")
    print(f"  Capitals:   {(merged['type'] == 'capital').sum()}")
    print(f"  Megacities: {(merged['type'] == 'megacity').sum()}")
    print(f"  Total:      {len(merged)}")
    print(f"\nComplete. Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
