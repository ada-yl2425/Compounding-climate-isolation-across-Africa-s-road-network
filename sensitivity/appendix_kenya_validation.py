"""
Appendix Figure: Kenya Floods Case Validation
==============================================
Compare model-predicted road vulnerability (P95 climate scenario, web_1 result1)
with documented road disruptions from Kenya heavy rains and flooding, April–May 2024.

Event:   Kenya heavy rains and flooding, April–May 2024
Sources: OCHA Kenya Flash Updates 1–6 (April–May 2024); ACAPS Briefing Note
         (14 May 2024); Kenya National Highways Authority (KeNHA) statements.

Key documented disruption:
  - A3 Nairobi–Garissa highway submerged at Mororo section, Tana River County
    (OCHA Flash Update #4, 3 May 2024; duration ≥ 10 days)
  - All road access to Garissa, Wajir, Mandera counties cut off
  - 30 health facilities in 7 counties inaccessible
  - Affected population: 306,520 (March–May 2024)

Model findings for the same corridor (result1 data):
  - Garissa County districts (KEN_7): 99–100th pctile nationally
  - Tana River County (KEN_40): 97th pctile
  - Wajir County (KEN_46): 98.6th pctile
  - Nairobi → Garissa (A3): +46.8% travel time, Garissa → Mombasa: +67.2%

Usage:
    python appendix_kenya_validation.py
    python appendix_kenya_validation.py --output figures/appendix_kenya_validation.png
"""

import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm
from matplotlib.lines import Line2D

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_RESULT1 = Path("path/to/africa_pavement/result/result1")
BASE_RAW    = Path("path/to/africa_pavement/RAW")

DISTRICT_GPKG  = BASE_RESULT1 / "finding5_city_district_speed_efficiency_spatial" / "africa_district_road_degradation_extreme_climate.gpkg"
CITY_PAIRS_CSV = BASE_RESULT1 / "finding3_4_city_pair_travel_time_cumulative" / "within_country_city_pairs_travel_time_normal_vs_extreme.csv"
GADM_KEN_L1    = BASE_RAW / "GADM_admin/gadm41_KEN/gadm41_KEN_1.shp"

# OCHA Flash Updates 1–6 (April–May 2024): counties with documented road loss
# Sources: OCHA Kenya Flash Update #4 (3 May 2024), #6 (17 May 2024)
OCHA_AFFECTED_COUNTIES = ["Garissa", "Tana River", "Wajir", "Mandera", "Kilifi", "Kwale", "Lamu"]

# District province-number → GADM county mapping for Kenya
# KEN_X → county X in GADM (1-indexed); verified by centroid coordinates
# KEN_7 = Garissa, KEN_40 = Tana River, KEN_46 = Wajir, KEN_19 = Kwale, KEN_14 = Kilifi
HIGH_VULN_PROVINCE_NUMS = [7, 14, 19, 39, 40, 46]

# Key cities (lon, lat, label_offset_x, label_offset_y)
CITIES = {
    "Nairobi":  (36.820, -1.292,  0.2, -0.25),
    "Garissa":  (39.648, -0.454,  0.2,  0.15),
    "Mombasa":  (39.668, -4.050, -0.2, -0.30),
    "Wajir":    (40.058,  1.748,  0.2,  0.15),
}

# A3 Highway: Nairobi → Garissa (documented submerged section)
A3_COORDS = [
    (36.820, -1.292),   # Nairobi
    (37.070, -1.030),   # Thika
    (38.060, -0.940),   # Mwingi
    (39.648, -0.454),   # Garissa
]

# Garissa → Mombasa coastal corridor (through Tana River County)
COASTAL_CORRIDOR = [
    (39.648, -0.454),   # Garissa
    (40.100, -1.500),   # Mororo / Tana River crossing  ← A3 SUBMERGED HERE
    (40.100, -3.210),   # Malindi
    (39.668, -4.050),   # Mombasa
]

# OCHA-documented specific disruption points
# Format: label -> (lon, lat, dx, dy, ha)
OCHA_DISRUPTIONS = {
    "Mororo (A3 submerged)\nOCHA Flash Update #4":  (40.100, -1.500,  0.20, 0.0,  "left"),
    "Garissa county\nroads cut off":                 (39.648, -0.454, -0.25, 0.30, "right"),
    "Wajir – all road\naccess disrupted":            (40.058,  1.748,  0.20, 0.0,  "left"),
}

# Map zoom extent (Kenya relevant corridor)
MAP_EXTENT = (34.5, 42.5, -5.5, 4.5)

ANNOTATION_FACTS = [
    "Nairobi → Garissa (A3):  +46.8% travel time",
    "Garissa → Mombasa:       +67.2% travel time",
    "",
    "KEN_7  (Garissa County):   99–100th pctile",
    "KEN_40 (Tana River County): 97th pctile",
    "KEN_46 (Wajir County):     98.6th pctile",
]


# =============================================================================
# HELPERS
# =============================================================================
def load_kenya_districts(gpkg_path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(gpkg_path)
    ken = gdf[gdf["country"] == "Kenya"].copy()
    ken["prov_num"] = ken["district_id"].str.extract(r"KEN_(\d+)_").astype(int)

    proj = ken.to_crs("EPSG:32737")
    c = proj.geometry.centroid.to_crs("EPSG:4326")
    ken = ken.to_crs("EPSG:4326")
    ken["cx"] = c.x.values
    ken["cy"] = c.y.values
    ken["eff_loss_pctile"] = ken["network_efficiency_loss_pct"].rank(pct=True) * 100
    return ken


# =============================================================================
# FIGURE
# =============================================================================
def make_figure(ken: gpd.GeoDataFrame, gadm_county: gpd.GeoDataFrame, output_path: Path):
    fig, axes = plt.subplots(1, 2, figsize=(14, 9))
    fig.patch.set_facecolor("white")

    xmin, xmax, ymin, ymax = MAP_EXTENT
    cmap = plt.cm.YlOrRd
    levels = [0, 25, 30, 35, 40, 45, 50, 55, 62]
    norm = BoundaryNorm(levels, ncolors=cmap.N, clip=True)

    # ==================== LEFT PANEL — model prediction ====================
    ax = axes[0]
    ax.set_facecolor("#e8f4f8")

    ken.plot(ax=ax, column="network_efficiency_loss_pct",
             cmap=cmap, norm=norm, edgecolor="white", linewidth=0.3)

    # Highlight high-vulnerability province groups with bold boundary
    high = ken[ken["prov_num"].isin(HIGH_VULN_PROVINCE_NUMS)]
    high_dissolved = high.dissolve(by="prov_num")
    high_dissolved.boundary.plot(ax=ax, color="#1a5276", linewidth=1.6,
                                 linestyle="--", zorder=5)

    # Road corridors
    ax.plot([c[0] for c in A3_COORDS], [c[1] for c in A3_COORDS],
            color="#154360", linewidth=2.0, linestyle="-", zorder=6,
            label="A3 Nairobi–Garissa corridor", solid_capstyle="round")
    ax.plot([c[0] for c in COASTAL_CORRIDOR], [c[1] for c in COASTAL_CORRIDOR],
            color="#1a5276", linewidth=1.6, linestyle="--", zorder=6,
            label="Garissa–Mombasa coastal route", solid_capstyle="round")

    # City markers
    for name, (lon, lat, dx, dy) in CITIES.items():
        ax.plot(lon, lat, "o", color="#1b2631", markersize=5, zorder=8)
        ax.text(lon + dx, lat + dy, name, fontsize=7.5, fontweight="bold",
                color="#1b2631", ha="left" if dx > 0 else "right",
                va="center", zorder=9)

    # County label for the most affected corridor
    ax.text(39.8, 0.5, "GARISSA\nCounty", fontsize=7.5, color="#1a5276",
            fontweight="bold", ha="center", va="center", alpha=0.9, zorder=7,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.6, edgecolor="none"))
    ax.text(40.1, -1.1, "TANA RIVER\nCounty", fontsize=7.5, color="#1a5276",
            fontweight="bold", ha="left", va="center", alpha=0.9, zorder=7,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.6, edgecolor="none"))

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_xlabel("Longitude", fontsize=9)
    ax.set_ylabel("Latitude", fontsize=9)
    ax.set_title("Model prediction\n(P95 climate scenario, baseline 2011–2020)",
                 fontsize=10.5, fontweight="bold", pad=8)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.65, pad=0.02, aspect=20)
    cbar.set_label("Network efficiency loss (%)\nunder P95 precipitation", fontsize=8)
    cbar.ax.tick_params(labelsize=7.5)

    bdry_line = Line2D([0], [0], color="#1a5276", lw=1.6, linestyle="--",
                       label="High-vuln. county boundary (≥95th pctile)")
    a3_line = Line2D([0], [0], color="#154360", lw=2.0, label="A3 Nairobi–Garissa")
    coast_line = Line2D([0], [0], color="#1a5276", lw=1.6, linestyle="--",
                        label="Garissa–Mombasa coastal route")
    ax.legend(handles=[bdry_line, a3_line, coast_line], fontsize=7.2,
              loc="lower left", framealpha=0.88)

    # ==================== RIGHT PANEL — documented disruption ====================
    ax2 = axes[1]
    ax2.set_facecolor("#e8f4f8")

    ken.plot(ax=ax2, color="#d5d8dc", edgecolor="white", linewidth=0.3)

    # OCHA-documented affected counties (GADM boundaries)
    affected = gadm_county[gadm_county["NAME_1"].isin(OCHA_AFFECTED_COUNTIES)]
    affected.plot(ax=ax2, color="#e74c3c", alpha=0.22, edgecolor="#c0392b",
                  linewidth=1.5, zorder=3)

    # Model high-vulnerability districts within affected counties
    high_vuln = ken[(ken["prov_num"].isin(HIGH_VULN_PROVINCE_NUMS)) &
                    (ken["eff_loss_pctile"] >= 90)]
    high_vuln.plot(ax=ax2, color="#c0392b", alpha=0.55, edgecolor="#922b21",
                   linewidth=0.5, zorder=4)

    # Road corridors
    ax2.plot([c[0] for c in A3_COORDS], [c[1] for c in A3_COORDS],
             color="#154360", linewidth=2.0, linestyle="-", zorder=6,
             solid_capstyle="round")
    ax2.plot([c[0] for c in COASTAL_CORRIDOR], [c[1] for c in COASTAL_CORRIDOR],
             color="#1a5276", linewidth=1.6, linestyle="--", zorder=6,
             solid_capstyle="round")

    # Cities
    for name, (lon, lat, dx, dy) in CITIES.items():
        ax2.plot(lon, lat, "o", color="#1b2631", markersize=5, zorder=8)
        ax2.text(lon + dx, lat + dy, name, fontsize=7.5, fontweight="bold",
                 color="#1b2631", ha="left" if dx > 0 else "right",
                 va="center", zorder=9)

    # OCHA disruption markers
    for label, (lon, lat, dx, dy, ha) in OCHA_DISRUPTIONS.items():
        ax2.plot(lon, lat, "X", color="#7b241c", markersize=9,
                 markeredgecolor="white", markeredgewidth=0.8, zorder=9)
        ax2.text(lon + dx, lat + dy, label, fontsize=6.8, color="#7b241c",
                 va="center", ha=ha, zorder=10,
                 bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                           alpha=0.82, edgecolor="none"))

    ax2.set_xlim(xmin, xmax)
    ax2.set_ylim(ymin, ymax)
    ax2.set_xlabel("Longitude", fontsize=9)
    ax2.set_title(
        "Documented disruption: Kenya floods, April–May 2024\n"
        "(Sources: OCHA Flash Updates 1–6; ACAPS Briefing Note 14 May 2024)",
        fontsize=10.5, fontweight="bold", pad=8)

    patch_ocha = mpatches.Patch(facecolor="#e74c3c", alpha=0.28, edgecolor="#c0392b",
        label="OCHA-documented affected counties\n(GADM 4.1 boundaries)")
    patch_model = mpatches.Patch(facecolor="#c0392b", alpha=0.55, edgecolor="#922b21",
        label="Model: ≥90th pctile eff. loss\n(overlap region)")
    marker_x = Line2D([0], [0], marker="X", color="w", markerfacecolor="#7b241c",
        markersize=9, markeredgecolor="white", label="OCHA-reported road disruption")
    a3_l = Line2D([0], [0], color="#154360", lw=2.0, label="A3 corridor")
    coast_l = Line2D([0], [0], color="#1a5276", lw=1.6, linestyle="--",
                     label="Garissa–Mombasa route")
    ax2.legend(handles=[patch_ocha, patch_model, marker_x, a3_l, coast_l],
               fontsize=7.0, loc="lower left", framealpha=0.88)

    # ------------------------------------------------------------------
    # Stats annotation
    # ------------------------------------------------------------------
    fig.text(0.5, 0.005, "\n".join(ANNOTATION_FACTS), ha="center", va="bottom",
             fontsize=8, family="monospace",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#fdfefe",
                       edgecolor="#aab7b8", linewidth=0.8))

    fig.suptitle(
        "Appendix: Spatial validation against Kenya floods (April–May 2024)\n"
        "Model-predicted vulnerability corridors vs. OCHA-documented road disruptions",
        fontsize=12, fontweight="bold", y=0.99)

    plt.tight_layout(rect=[0, 0.10, 1, 0.97])
    plt.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    print(f"Figure saved → {output_path}")
    plt.close()


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Generate Kenya flood validation figure")
    parser.add_argument("--output", type=str,
                        default=str(Path(__file__).parent / "appendix_kenya_validation.png"))
    args = parser.parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Loading Kenya district data...")
    ken = load_kenya_districts(DISTRICT_GPKG)
    print(f"  {len(ken)} districts loaded")

    print("Loading GADM Kenya county boundaries...")
    gadm_county = gpd.read_file(GADM_KEN_L1).to_crs("EPSG:4326")
    print(f"  {len(gadm_county)} counties")

    # Summary for paper text
    target = ken[ken["prov_num"].isin(HIGH_VULN_PROVINCE_NUMS)]
    print("\n=== High-vulnerability corridor districts ===")
    print(target.sort_values("eff_loss_pctile", ascending=False)[
        ["district_id", "prov_num", "network_efficiency_loss_pct",
         "eff_loss_pctile", "cx", "cy"]].head(12).to_string())

    df_city = pd.read_csv(CITY_PAIRS_CSV)
    ken_city = df_city[df_city["country"] == "Kenya"]
    key_pairs = ken_city[
        ken_city["city_A"].isin(["Nairobi", "Garissa", "Mombasa"]) |
        ken_city["city_B"].isin(["Nairobi", "Garissa", "Mombasa"])
    ].sort_values("increase_pct", ascending=False)
    print("\n=== Key corridor city pairs ===")
    print(key_pairs[["city_A", "city_B", "t_normal_h",
                      "t_extreme_h", "increase_pct"]].head(10).to_string())

    print("\nGenerating figure...")
    make_figure(ken, gadm_county, output_path)


if __name__ == "__main__":
    main()
