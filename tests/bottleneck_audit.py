"""
bottleneck_audit.py  —  Step 0: Data Audit

Checks that all required input files exist for every country before
the expensive network-building step.

Usage:
    python tests/bottleneck_audit.py --base <BASE_DIR>
"""

import argparse
from pathlib import Path

import pandas as pd

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


def audit_data(
    roads_dir: Path, speed_dir: Path, pop_dir: Path, out_dir: Path
) -> pd.DataFrame:
    """Verify all required datasets exist per country."""
    print(f"\n{'='*60}\n  STEP 0 — Data Audit\n{'='*60}")
    rows = []
    for country, iso3 in FOLDER_TO_ISO.items():
        shp = roads_dir / country / f"{country}.shp"
        spd = speed_dir / f"{country}_road_speed.csv"
        tif = pop_dir / f"{iso3.lower()}_ppp_2020_UNadj_constrained.tif"
        rows.append(
            dict(
                country=country,
                iso3=iso3,
                shp=shp.exists(),
                speed_csv=spd.exists(),
                worldpop_tif=tif.exists(),
            )
        )

    df = pd.DataFrame(rows)
    print(f"  Countries: {len(df)}")
    print(f"  Shapefile OK  : {df['shp'].sum()} / {len(df)}")
    print(f"  Speed CSV OK  : {df['speed_csv'].sum()} / {len(df)}")
    print(f"  WorldPop .tif : {df['worldpop_tif'].sum()} / {len(df)}")

    missing_pop = df[~df["worldpop_tif"]]["country"].tolist()
    if missing_pop:
        print(f"  [WARN] Missing pop : {missing_pop}")

    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "00_data_audit.csv", index=False)
    print(f"  Saved → 00_data_audit.csv")
    return df


def main():
    parser = argparse.ArgumentParser(description="Bottleneck Data Audit")
    parser.add_argument(
        "--base", required=True, help="Base directory (africa_pavement)"
    )
    args = parser.parse_args()

    base = Path(args.base)
    audit_data(
        roads_dir=base / "RAW" / "Road_data",
        speed_dir=base / "road_speed_cordex",
        pop_dir=base / "RAW" / "Pop_data",
        out_dir=base / "web" / "network_results" / "bottleneck_paving",
    )


if __name__ == "__main__":
    main()
