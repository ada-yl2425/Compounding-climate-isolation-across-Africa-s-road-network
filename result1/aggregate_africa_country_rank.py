"""
aggregate_africa_country_rank.py
=================================
Aggregates Africa-layer OD results and road-speed data to country level,
producing two ranked tables:

  1. africa_country_efficiency_loss.csv
       Country ranking by mean OD travel-time increase under extreme weather.

  2. africa_country_amplification.csv
       Country ranking by network amplification ratio:
       amplification = mean_OD_increase_pct / mean_road_speed_drop_pct
       Values > 1 mean the network amplifies the climate signal beyond the
       direct road-speed effect.

Methodology
-----------
Road-level input degradation (per country):
  speed_drop_pct = (V_normal - V_extreme) / V_normal × 100
  Averaged over all road segments in that country.

OD-level output degradation (per country):
  For each connected OD pair (city_A, city_B), the pair is attributed to a
  country if at least one endpoint belongs to that country.  The mean
  increase_pct across those pairs is the country's OD degradation.

Amplification ratio:
  amplification = od_mean_increase_pct / road_mean_speed_drop_pct
"""

from pathlib import Path

import pandas as pd
import numpy as np

# =============================================================================
# CONFIGURATION  (override via --base-dir at runtime)
# =============================================================================
BASE_DIR = Path("path/to/your/base/directory")
SPEED_DIR = BASE_DIR / "road_speed_cordex"
NODES_CSV = BASE_DIR / "web/africa_layer/africa_nodes.csv"
OD_PAIRS_CSV = BASE_DIR / "web/network_results/africa_layer/africa_od_pairs.csv"
OUTPUT_DIR = BASE_DIR / "web/network_results/africa_layer"

# country_folder name → ISO-3 (matches FOLDER_TO_ISO in run_africa_layer.py)
FOLDER_TO_ISO = {
    "Algeria": "DZA", "Angola": "AGO", "Benin": "BEN", "Botswana": "BWA",
    "BurkinaFaso": "BFA", "Burundi": "BDI", "Cameroon": "CMR",
    "CentralAfrican": "CAF", "Chad": "TCD", "Congo": "COG", "CongoDR": "COD",
    "Djibouti": "DJI", "Egypt": "EGY", "Equatorial": "GNQ", "Eritrea": "ERI",
    "Ethiopia": "ETH", "Gabon": "GAB", "Gambia": "GMB", "Ghana": "GHA",
    "Guinea": "GIN", "GuineaBissau": "GNB", "IvoryCoast": "CIV",
    "Kenya": "KEN", "Lesotho": "LSO", "Liberia": "LBR", "Libya": "LBY",
    "Madagascar": "MDG", "Malawi": "MWI", "Mali": "MLI", "Mauritania": "MRT",
    "Morocco": "MAR", "Mozambique": "MOZ", "Namibia": "NAM", "Niger": "NER",
    "Nigeria": "NGA", "Rwanda": "RWA", "Senegal": "SEN",
    "SierraLeone": "SLE", "Somalia": "SOM", "SouthAfrica": "ZAF",
    "SouthSudan": "SSD", "Sudan": "SDN", "Swaziland": "SWZ",
    "Tanzania": "TZA", "Togo": "TGO", "Tunisia": "TUN", "Uganda": "UGA",
    "WestSahara": "ESH", "Zambia": "ZMB", "Zimbabwe": "ZWE",
}


# =============================================================================
# STEP 1 — Road-level speed degradation per country
# =============================================================================
def compute_road_degradation(speed_dir: Path) -> pd.DataFrame:
    print(f"\n[1] Computing road-level speed degradation from {speed_dir.name}/")
    rows = []
    for folder, iso3 in FOLDER_TO_ISO.items():
        csv_path = speed_dir / f"{folder}_road_speed.csv"
        if not csv_path.exists():
            print(f"  SKIP {folder}: speed CSV not found")
            continue
        df = pd.read_csv(csv_path, usecols=["V_normal", "V_extreme", "p_block"])
        df["V_normal"] = pd.to_numeric(df["V_normal"], errors="coerce")
        df["V_extreme"] = pd.to_numeric(df["V_extreme"], errors="coerce")
        df["p_block"] = pd.to_numeric(df["p_block"], errors="coerce").fillna(0)
        df = df.dropna(subset=["V_normal", "V_extreme"])
        df = df[df["V_normal"] > 0]

        speed_drop = (df["V_normal"] - df["V_extreme"]) / df["V_normal"] * 100
        rows.append(
            {
                "country_folder": folder,
                "iso3": iso3,
                "n_road_segments": len(df),
                "road_mean_speed_drop_pct": speed_drop.mean(),
                "road_median_speed_drop_pct": speed_drop.median(),
                "road_mean_p_block": df["p_block"].mean(),
            }
        )

    result = pd.DataFrame(rows)
    print(f"  Loaded {len(result)} countries, {result['n_road_segments'].sum():,} road segments total")
    return result


# =============================================================================
# STEP 2 — OD-level travel-time degradation per country
# =============================================================================
def compute_od_degradation(od_pairs_csv: Path, nodes_csv: Path) -> pd.DataFrame:
    print(f"\n[2] Computing OD-level degradation from {od_pairs_csv.name}")

    od = pd.read_csv(od_pairs_csv)
    nodes = pd.read_csv(nodes_csv, usecols=["name", "iso3", "country_folder"])

    city_to_iso = dict(zip(nodes["name"], nodes["iso3"]))
    city_to_folder = dict(zip(nodes["name"], nodes["country_folder"]))

    connected = od[od["conn_type"] == "connected"].copy()
    print(f"  Connected pairs: {len(connected):,} / {len(od):,} total")

    # Attribute each pair to both endpoint countries
    rows = []
    for _, r in connected.iterrows():
        inc = r["increase_pct"]
        if pd.isna(inc):
            continue
        for city_col in ("city_A", "city_B"):
            iso3 = city_to_iso.get(r[city_col])
            folder = city_to_folder.get(r[city_col])
            if iso3:
                rows.append({"iso3": iso3, "country_folder": folder, "increase_pct": inc})

    df_long = pd.DataFrame(rows)
    grouped = (
        df_long.groupby(["iso3", "country_folder"])["increase_pct"]
        .agg(
            od_n_pairs="count",
            od_mean_increase_pct="mean",
            od_median_increase_pct="median",
            od_p75_increase_pct=lambda x: x.quantile(0.75),
            od_max_increase_pct="max",
        )
        .reset_index()
    )
    print(f"  Countries with OD data: {len(grouped)}")
    return grouped


# =============================================================================
# STEP 3 — Merge and compute amplification
# =============================================================================
def compute_amplification(road_df: pd.DataFrame, od_df: pd.DataFrame) -> pd.DataFrame:
    print("\n[3] Computing amplification ratios")
    merged = od_df.merge(road_df, on=["iso3", "country_folder"], how="inner")

    merged["amplification_ratio"] = (
        merged["od_mean_increase_pct"] / merged["road_mean_speed_drop_pct"]
    )

    # Continent baseline for reference
    continent_od_mean = merged["od_mean_increase_pct"].mean()
    continent_road_mean = merged["road_mean_speed_drop_pct"].mean()
    continent_amp = continent_od_mean / continent_road_mean
    print(f"  Continent mean OD increase:        {continent_od_mean:.2f}%")
    print(f"  Continent mean road speed drop:    {continent_road_mean:.2f}%")
    print(f"  Continent amplification ratio:     {continent_amp:.2f}x")

    return merged


# =============================================================================
# MAIN
# =============================================================================
def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default=None)
    args = parser.parse_args()

    global BASE_DIR, SPEED_DIR, NODES_CSV, OD_PAIRS_CSV, OUTPUT_DIR
    if args.base_dir:
        BASE_DIR = Path(args.base_dir)
        SPEED_DIR = BASE_DIR / "road_speed_cordex"
        NODES_CSV = BASE_DIR / "web/africa_layer/africa_nodes.csv"
        OD_PAIRS_CSV = BASE_DIR / "web/network_results/africa_layer/africa_od_pairs.csv"
        OUTPUT_DIR = BASE_DIR / "web/network_results/africa_layer"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    road_df = compute_road_degradation(SPEED_DIR)
    od_df = compute_od_degradation(OD_PAIRS_CSV, NODES_CSV)
    merged = compute_amplification(road_df, od_df)

    # Table 1: efficiency loss ranking
    loss_cols = [
        "iso3", "country_folder",
        "od_mean_increase_pct", "od_median_increase_pct",
        "od_p75_increase_pct", "od_max_increase_pct",
        "od_n_pairs",
        "road_mean_speed_drop_pct", "n_road_segments",
    ]
    loss_table = (
        merged[loss_cols]
        .sort_values("od_mean_increase_pct", ascending=False)
        .reset_index(drop=True)
    )
    loss_table.index += 1
    loss_table.index.name = "rank"

    loss_path = OUTPUT_DIR / "africa_country_efficiency_loss.csv"
    loss_table.to_csv(loss_path)
    print(f"\n  Saved: {loss_path.name}")
    print("\n  Top 10 by OD efficiency loss:")
    for rank, r in loss_table.head(10).iterrows():
        print(
            f"    {rank:>2}. {r['iso3']}  OD increase: {r['od_mean_increase_pct']:.1f}%"
            f"  road drop: {r['road_mean_speed_drop_pct']:.1f}%"
            f"  amp: {r['od_mean_increase_pct']/r['road_mean_speed_drop_pct']:.2f}x"
        )

    # Table 2: amplification ranking
    amp_cols = [
        "iso3", "country_folder",
        "amplification_ratio",
        "od_mean_increase_pct", "road_mean_speed_drop_pct",
        "road_mean_p_block", "od_n_pairs", "n_road_segments",
    ]
    amp_table = (
        merged[amp_cols]
        .sort_values("amplification_ratio", ascending=False)
        .reset_index(drop=True)
    )
    amp_table.index += 1
    amp_table.index.name = "rank"

    amp_path = OUTPUT_DIR / "africa_country_amplification.csv"
    amp_table.to_csv(amp_path)
    print(f"\n  Saved: {amp_path.name}")
    print("\n  Top 10 by amplification ratio:")
    for rank, r in amp_table.head(10).iterrows():
        print(
            f"    {rank:>2}. {r['iso3']}  amp: {r['amplification_ratio']:.2f}x"
            f"  OD: {r['od_mean_increase_pct']:.1f}%"
            f"  road: {r['road_mean_speed_drop_pct']:.1f}%"
            f"  p_block: {r['road_mean_p_block']:.3f}"
        )


if __name__ == "__main__":
    main()
