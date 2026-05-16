"""
Appendix Figure: Cyclone Idai Case Validation
==============================================
Compare model-predicted road vulnerability (P95 climate scenario, result1)
with documented disruption from Cyclone Idai, Mozambique, March 2019.

Left panel  — Model prediction: district-level network efficiency loss (%) under
              P95 precipitation, Mozambique. Sofala and Manica province boundaries
              highlighted; EN6 corridor and key cities labelled.

Right panel — Documented disruption: simplified impact zone based on OCHA
              Mozambique Cyclone Idai Situation Reports (OCHA, 2019) and the
              Springer Nature peer-reviewed study (Dahl et al., 2022,
              Int J Health Geographics, doi:10.1186/s12942-022-00315-2).
              Key reported road-cut locations marked; EN6 corridor overlaid.

Validation framing: this is a spatial-consistency check, not a temporal prediction.
The P95 climatological scenario captures the same physical mechanism as Idai
(precipitation → soil saturation → road-surface failure) at a different intensity.
Overlap between model-predicted high-vulnerability districts and OCHA-reported
cut-off locations indicates that the model correctly identifies structurally
susceptible corridors.

Data source (model side): result1/finding5 district GeoPackage
References (validation side):
  - OCHA (2019). Mozambique: Cyclone Idai & Floods Situation Reports 1–19. UN OCHA.
  - Dahl et al. (2022). Int J Health Geographics, 21(1), 19.
  - World Bank (2019). After Cyclones Hit Mozambique…

Usage:
    python appendix_idai_validation.py
    python appendix_idai_validation.py --output sensitivity/appendix_idai_validation.png
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
from shapely.geometry import LineString, Point, Polygon

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_RESULT1 = Path("path/to/africa_pavement/result/result1")
BASE_RAW = Path("path/to/africa_pavement/RAW")

DISTRICT_GPKG = (
    BASE_RESULT1
    / "finding5_city_district_speed_efficiency_spatial"
    / "africa_district_road_degradation_extreme_climate.gpkg"
)
CITY_PAIRS_CSV = (
    BASE_RESULT1
    / "finding3_4_city_pair_travel_time_cumulative"
    / "within_country_city_pairs_travel_time_normal_vs_extreme.csv"
)
GADM_MOZ_L1 = BASE_RAW / "GADM_admin/gadm41_MOZ/gadm41_MOZ_1.shp"

# Province number → name mapping (derived from district_id centroid analysis)
PROVINCE_MAP = {
    1: "Cabo Delgado",
    2: "Gaza",
    3: "Inhambane",
    4: "Manica",
    5: "Maputo City",
    6: "Maputo Province",
    7: "Nampula",
    8: "Zambézia",
    9: "Sofala",
    10: "Tete",
    11: "Niassa",
}

# Key cities (lon, lat, label, label_offset)
CITIES = {
    "Beira": (34.840, -19.843, (-0.5, -0.35)),
    "Chimoio": (33.470, -19.110, (0.1, -0.35)),
    "Nhamatanda": (34.310, -19.340, (0.1, 0.15)),
    "Buzi": (34.020, -19.840, (0.1, 0.15)),
    "Dondo": (34.730, -19.610, (0.1, 0.15)),
}

# EN6 highway approximate centreline (Beira → Zimbabwe border via Chimoio)
EN6_COORDS = [
    (34.840, -19.843),  # Beira
    (34.730, -19.610),  # Dondo
    (34.310, -19.340),  # Nhamatanda
    (33.640, -19.120),  # Gondola
    (33.470, -19.110),  # Chimoio
    (32.650, -18.970),  # Zimbabwe border (Mutare vicinity)
]

# OCHA Sit-Reps 1–19 document Sofala as the primary affected province;
# Manica was secondarily affected (EN6 corridor disruption).
# We use GADM 4.1 province boundaries (loaded at runtime) instead of a hand-drawn polygon.
IDAI_AFFECTED_PROVINCES = ["Sofala", "Manica"]

# OCHA-reported specific road-cut locations (Sit-Reps 1–10)
# Format: label -> (lon, lat, label_dx, label_dy, ha)
OCHA_ROAD_CUTS = {
    "Nhamatanda\n(OCHA #3)": (34.310, -19.340, 0.18, -0.35, "left"),
    "Buzi dist.\n(OCHA #1)": (34.020, -19.840, -0.18, 0.20, "right"),
    "Dondo (OCHA #2)": (34.730, -19.610, 0.18, 0.30, "left"),
}

# Quantitative facts for the annotation box
ANNOTATION_FACTS = [
    "Beira → Chimoio (EN6): +66.8% travel time",
    "↳ 95th pctile among Mozambique city pairs",
    "",
    "MOZ_9_12 (Nhamatanda area):",
    "  Efficiency loss 46.5% → 91st pctile",
    "MOZ_9_5  (Buzi area):",
    "  Efficiency loss 43.7% → 82nd pctile",
]


# =============================================================================
# HELPERS
# =============================================================================
def load_mozambique_districts(gpkg_path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(gpkg_path)
    moz = gdf[gdf["country"] == "Mozambique"].copy()
    moz["prov_num"] = moz["district_id"].str.extract(r"MOZ_(\d+)_").astype(int)
    moz["province"] = moz["prov_num"].map(PROVINCE_MAP)

    # Compute centroids in projected CRS, keep result in WGS-84 for plotting
    proj = moz.to_crs("EPSG:32736")
    centroids_wgs = proj.geometry.centroid.to_crs("EPSG:4326")
    moz = moz.to_crs("EPSG:4326")
    moz["cx"] = centroids_wgs.x.values
    moz["cy"] = centroids_wgs.y.values

    # National percentile rank for annotation
    moz["eff_loss_pctile"] = moz["network_efficiency_loss_pct"].rank(pct=True) * 100
    return moz


def province_boundary(moz: gpd.GeoDataFrame, prov_num: int) -> gpd.GeoSeries:
    subset = moz[moz["prov_num"] == prov_num]
    return subset.dissolve().geometry


def map_extent(moz: gpd.GeoDataFrame, margin: float = 0.5):
    # Zoom to central Mozambique (Sofala/Manica corridor + context)
    # Full country extent: lon 30.4-40.8, lat -26.8 to -10.4
    # Cyclone Idai affected zone: roughly lon 31-37, lat -22 to -15
    return (30.8, 37.2, -23.0, -14.0)


# =============================================================================
# FIGURE
# =============================================================================
def make_figure(moz: gpd.GeoDataFrame, gadm_prov: gpd.GeoDataFrame, output_path: Path):
    fig, axes = plt.subplots(1, 2, figsize=(14, 9))
    fig.patch.set_facecolor("white")

    xmin, xmax, ymin, ymax = map_extent(moz)

    # ------------------------------------------------------------------
    # Colour scheme
    # ------------------------------------------------------------------
    cmap = plt.cm.YlOrRd
    levels = [0, 25, 30, 35, 40, 45, 50, 55, 60]
    norm = BoundaryNorm(levels, ncolors=cmap.N, clip=True)

    col_field = "network_efficiency_loss_pct"

    # ==================== LEFT PANEL — model prediction ====================
    ax = axes[0]
    ax.set_facecolor("#e8f4f8")

    moz.plot(
        ax=ax,
        column=col_field,
        cmap=cmap,
        norm=norm,
        edgecolor="white",
        linewidth=0.4,
    )

    # Province boundaries for Sofala (9) and Manica (4)
    for pnum, color, lw in [(9, "#1a5276", 1.8), (4, "#1a5276", 1.8)]:
        bdry = province_boundary(moz, pnum)
        gpd.GeoSeries(bdry, crs="EPSG:4326").boundary.plot(
            ax=ax, color=color, linewidth=lw, linestyle="--", zorder=5
        )

    # EN6 corridor
    en6 = LineString(EN6_COORDS)
    ax.plot(
        [c[0] for c in EN6_COORDS],
        [c[1] for c in EN6_COORDS],
        color="#154360",
        linewidth=2.2,
        linestyle="-",
        label="EN6 Beira–Chimoio corridor",
        zorder=6,
        solid_capstyle="round",
    )

    # City markers
    for name, (lon, lat, offset) in CITIES.items():
        ax.plot(lon, lat, "o", color="#1b2631", markersize=5, zorder=8)
        ax.text(
            lon + offset[0],
            lat + offset[1],
            name,
            fontsize=7.5,
            fontweight="bold",
            color="#1b2631",
            ha="left" if offset[0] > 0 else "right",
            va="center",
            zorder=9,
        )

    # Label Sofala and Manica provinces
    for pnum, label, pos in [
        (9, "SOFALA\nProv.", (35.2, -19.0)),
        (4, "MANICA\nProv.", (33.0, -17.3)),
    ]:
        ax.text(
            pos[0],
            pos[1],
            label,
            fontsize=8,
            color="#1a5276",
            fontweight="bold",
            ha="center",
            va="center",
            alpha=0.85,
            zorder=7,
            bbox=dict(
                boxstyle="round,pad=0.2", facecolor="white", alpha=0.6, edgecolor="none"
            ),
        )

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_xlabel("Longitude", fontsize=9)
    ax.set_ylabel("Latitude", fontsize=9)
    ax.set_title(
        "Model prediction\n(P95 climate scenario, baseline 2011–2020)",
        fontsize=10.5,
        fontweight="bold",
        pad=8,
    )

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.65, pad=0.02, aspect=20)
    cbar.set_label("Network efficiency loss (%)\nunder P95 precipitation", fontsize=8)
    cbar.ax.tick_params(labelsize=7.5)

    # Province boundary legend entry
    prov_line = Line2D(
        [0],
        [0],
        color="#1a5276",
        lw=1.8,
        linestyle="--",
        label="Sofala / Manica province boundary",
    )
    en6_line = Line2D(
        [0],
        [0],
        color="#154360",
        lw=2.2,
        linestyle="-",
        label="EN6 Beira–Chimoio corridor",
    )
    ax.legend(
        handles=[prov_line, en6_line], fontsize=7.5, loc="lower left", framealpha=0.85
    )

    # ==================== RIGHT PANEL — documented disruption ====================
    ax2 = axes[1]
    ax2.set_facecolor("#e8f4f8")

    # All Mozambique districts as light grey background
    moz.plot(ax=ax2, color="#d5d8dc", edgecolor="white", linewidth=0.4)

    # OCHA-documented affected provinces: Sofala + Manica (GADM 4.1 boundaries)
    affected = gadm_prov[gadm_prov["NAME_1"].isin(IDAI_AFFECTED_PROVINCES)]
    affected.plot(
        ax=ax2,
        color="#e74c3c",
        alpha=0.20,
        edgecolor="#c0392b",
        linewidth=1.6,
        linestyle="-",
        zorder=3,
    )

    # Highlight the model-predicted top-quartile districts that overlap with impact zone
    # (Sofala and Manica, top 50th pctile nationally)
    high_vuln = moz[(moz["prov_num"].isin([9, 4])) & (moz["eff_loss_pctile"] >= 60)]
    high_vuln.plot(
        ax=ax2,
        color="#c0392b",
        alpha=0.55,
        edgecolor="#922b21",
        linewidth=0.6,
        zorder=4,
    )

    # EN6 corridor
    ax2.plot(
        [c[0] for c in EN6_COORDS],
        [c[1] for c in EN6_COORDS],
        color="#154360",
        linewidth=2.2,
        linestyle="-",
        zorder=6,
        solid_capstyle="round",
    )

    # OCHA-reported road cut markers
    for label, (lon, lat, dx, dy, ha) in OCHA_ROAD_CUTS.items():
        ax2.plot(
            lon,
            lat,
            "X",
            color="#7b241c",
            markersize=9,
            markeredgecolor="white",
            markeredgewidth=0.8,
            zorder=9,
        )
        ax2.text(
            lon + dx,
            lat + dy,
            label,
            fontsize=7,
            color="#7b241c",
            va="center",
            ha=ha,
            zorder=10,
            bbox=dict(
                boxstyle="round,pad=0.15",
                facecolor="white",
                alpha=0.8,
                edgecolor="none",
            ),
        )

    # Beira city
    ax2.plot(34.840, -19.843, "o", color="#1b2631", markersize=6, zorder=8)
    ax2.text(
        34.840 - 0.12,
        -19.843 - 0.45,
        "Beira",
        fontsize=8,
        fontweight="bold",
        ha="right",
        va="top",
        zorder=9,
    )
    ax2.plot(33.470, -19.110, "o", color="#1b2631", markersize=5, zorder=8)
    ax2.text(
        33.470 + 0.15,
        -19.110 + 0.2,
        "Chimoio",
        fontsize=7.5,
        fontweight="bold",
        ha="left",
        va="bottom",
        zorder=9,
    )

    # Province outlines
    for pnum in [9, 4]:
        bdry = province_boundary(moz, pnum)
        gpd.GeoSeries(bdry, crs="EPSG:4326").boundary.plot(
            ax=ax2, color="#1a5276", linewidth=1.6, linestyle="--", zorder=5
        )

    ax2.set_xlim(xmin, xmax)
    ax2.set_ylim(ymin, ymax)
    ax2.set_xlabel("Longitude", fontsize=9)
    ax2.set_title(
        "Documented disruption: Cyclone Idai, March 2019\n"
        "(Sources: OCHA Sit-Reps 1–19; Dahl et al. 2022, Int J Health Geogr)",
        fontsize=10.5,
        fontweight="bold",
        pad=8,
    )

    # Legend for right panel
    patch_impact = mpatches.Patch(
        facecolor="#e74c3c",
        alpha=0.3,
        edgecolor="#c0392b",
        label="OCHA-reported affected provinces\n(Sofala & Manica; GADM 4.1 boundaries)",
    )
    patch_model = mpatches.Patch(
        facecolor="#c0392b",
        alpha=0.55,
        edgecolor="#922b21",
        label="Model: Sofala/Manica districts ≥60th pctile\nefficiency loss (overlap region)",
    )
    marker_cut = Line2D(
        [0],
        [0],
        marker="X",
        color="w",
        markerfacecolor="#7b241c",
        markersize=9,
        markeredgecolor="white",
        label="OCHA-reported road cut location",
    )
    en6_line2 = Line2D([0], [0], color="#154360", lw=2.2, label="EN6 corridor")
    ax2.legend(
        handles=[patch_impact, patch_model, marker_cut, en6_line2],
        fontsize=7.2,
        loc="lower left",
        framealpha=0.88,
    )

    # ------------------------------------------------------------------
    # Annotation box with key statistics
    # ------------------------------------------------------------------
    stats_text = "\n".join(ANNOTATION_FACTS)
    fig.text(
        0.5,
        0.005,
        stats_text,
        ha="center",
        va="bottom",
        fontsize=8,
        bbox=dict(
            boxstyle="round,pad=0.5",
            facecolor="#fdfefe",
            edgecolor="#aab7b8",
            linewidth=0.8,
        ),
        family="monospace",
    )

    # ------------------------------------------------------------------
    # Overall title and layout
    # ------------------------------------------------------------------
    fig.suptitle(
        "Appendix: Spatial validation against Cyclone Idai (Mozambique, March 2019)\n"
        "Model-predicted vulnerability corridors vs. OCHA-documented road disruptions",
        fontsize=12,
        fontweight="bold",
        y=0.99,
    )

    plt.tight_layout(rect=[0, 0.10, 1, 0.97])
    plt.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    print(f"Figure saved → {output_path}")
    plt.close()


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Generate Idai validation figure")
    parser.add_argument(
        "--output",
        type=str,
        default=str(Path(__file__).parent / "appendix_idai_validation.png"),
        help="Output PNG path",
    )
    args = parser.parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Loading Mozambique district data...")
    moz = load_mozambique_districts(DISTRICT_GPKG)
    print(f"  {len(moz)} districts loaded")

    print("Loading GADM province boundaries...")
    gadm_prov = gpd.read_file(GADM_MOZ_L1).to_crs("EPSG:4326")
    print(f"  {len(gadm_prov)} provinces: {list(gadm_prov['NAME_1'])}")

    # Print summary statistics for the paper text
    sofala_manica = moz[moz["prov_num"].isin([9, 4])]
    top_districts = sofala_manica.sort_values("eff_loss_pctile", ascending=False).head(
        5
    )
    print("\n=== Key districts (Sofala + Manica) for paper text ===")
    print(
        top_districts[
            [
                "district_id",
                "province",
                "network_efficiency_loss_pct",
                "eff_loss_pctile",
                "cx",
                "cy",
            ]
        ].to_string()
    )

    # Load city pair stats for Beira corridor
    df_city = pd.read_csv(CITY_PAIRS_CSV)
    beira_chimoio = df_city[
        (df_city["country"] == "Mozambique")
        & (df_city["city_A"].isin(["Beira", "Chimoio"]))
        & (df_city["city_B"].isin(["Beira", "Chimoio"]))
    ]
    if not beira_chimoio.empty:
        row = beira_chimoio.iloc[0]
        print(f"\nBeira–Chimoio (EN6): +{row['increase_pct']:.1f}% travel time")
    else:
        moz_city = df_city[df_city["country"] == "Mozambique"]
        beira = moz_city[
            (moz_city["city_A"] == "Beira") | (moz_city["city_B"] == "Beira")
        ]
        print("\nBeira city pairs:")
        print(beira[["city_A", "city_B", "increase_pct"]].to_string())

    print("\nGenerating figure...")
    make_figure(moz, gadm_prov, output_path)


if __name__ == "__main__":
    main()
