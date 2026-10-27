#!/usr/bin/env python3
"""
Result 1.1 district amplification-ratio choropleth.

Fine-resolution polygon fill using district_od_fill.gpkg.
Primary fill variable:
    amplification_ratio = network accessibility-loss amplification relative
    to direct road degradation.
"""

from __future__ import annotations

import os
from pathlib import Path

OUTPUT_DIR = Path("<FIGURE_OUTPUT_ROOT>/result 1.1")
os.environ.setdefault("MPLCONFIGDIR", str(OUTPUT_DIR / "_mplconfig"))
(OUTPUT_DIR / "_mplconfig").mkdir(parents=True, exist_ok=True)

import geopandas as gpd
import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Rectangle

DISTRICT_GPKG = Path("<LOCAL_INPUT_ROOT>/" "input_files/district_od_fill.gpkg")
OUT_PNG = OUTPUT_DIR / "result1_1_district_amplification_map.png"
OUT_PDF = OUTPUT_DIR / "result1_1_district_amplification_map.pdf"
OUT_CHECKS = OUTPUT_DIR / "result1_1_district_amplification_map_checks.txt"

CM_TO_INCH = 1 / 2.54
FIGSIZE = (9.5 * CM_TO_INCH, 13.0 * CM_TO_INCH)
DPI = 600
BASE_FONT_SIZE = 9.5
MAP_CRS = (
    "+proj=aea +lat_1=-18 +lat_2=21 +lat_0=0 +lon_0=20 +datum=WGS84 +units=m +no_defs"
)
VALUE_COL = "amplification_ratio"
VALUE_LABEL = "Amplification ratio (x)"
VALUE_MIN_VALID = 0.0
BOUNDS = [0, 4, 8, 16, 32, 64]
TICK_POSITIONS = [2, 6, 12, 24, 48]
TICK_LABELS = ["0-4", "4-8", "8-16", "16-32", "32-64+"]


def require_files(paths: list[Path]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required file(s):\n" + "\n".join(missing))


def find_natural_earth_lowres() -> Path:
    candidates = [
        Path("<PYOGRIO_FIXTURE_ROOT>/naturalearth_lowres/naturalearth_lowres.shp"),
        Path("<PYOGRIO_FIXTURE_ROOT>/naturalearth_lowres/naturalearth_lowres.shp"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Local Natural Earth low-resolution country boundary file not found."
    )


def load_inputs() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    require_files([DISTRICT_GPKG, find_natural_earth_lowres()])
    districts = gpd.read_file(DISTRICT_GPKG)
    countries = gpd.read_file(find_natural_earth_lowres())

    required = [
        "district_id",
        "country",
        VALUE_COL,
        "dE_pct",
        "mean_road_degradation_pct",
        "geometry",
    ]
    missing = [col for col in required if col not in districts.columns]
    if missing:
        raise ValueError(f"district gpkg missing required columns: {missing}")

    if districts.crs is None:
        districts = districts.set_crs("EPSG:4326")
    if countries.crs is None:
        countries = countries.set_crs("EPSG:4326")

    africa = countries.loc[countries["continent"].eq("Africa")].copy()
    africa = africa.to_crs(MAP_CRS)
    districts = districts.to_crs(MAP_CRS)
    return districts, africa


def split_valid_invalid(
    districts: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    valid = districts.loc[
        districts[VALUE_COL].notna() & (districts[VALUE_COL] > VALUE_MIN_VALID)
    ].copy()
    invalid = districts.loc[
        ~(districts[VALUE_COL].notna() & (districts[VALUE_COL] > VALUE_MIN_VALID))
    ].copy()
    return valid, invalid


def save_checks(districts: gpd.GeoDataFrame) -> None:
    valid, invalid = split_valid_invalid(districts)
    values = valid[VALUE_COL]

    lines = []
    lines.append("Result 1.1 district amplification-ratio map checks")
    lines.append("=" * 49)
    lines.append("")
    lines.append(f"District polygons total: {len(districts):,}")
    lines.append(f"District polygons with valid fill: {len(valid):,}")
    lines.append(f"District polygons without valid fill: {len(invalid):,}")
    lines.append(f"Valid value range: {values.min():.2f}x - {values.max():.2f}x")
    lines.append(f"Mean across valid polygons: {values.mean():.2f}x")
    lines.append(f"Median across valid polygons: {values.median():.2f}x")
    lines.append(f"95th percentile: {values.quantile(0.95):.2f}x")
    lines.append(
        f"Values above top bin (> {BOUNDS[-1]:.0f}x): {(values > BOUNDS[-1]).sum():,}"
    )
    lines.append(
        f"Non-positive values treated as no fill: {(districts[VALUE_COL] <= VALUE_MIN_VALID).sum():,}"
    )
    lines.append("")
    lines.append("Top countries by valid polygon count")
    lines.append(valid["country"].value_counts().head(20).to_string())
    lines.append("")
    lines.append("Top countries by mean amplification_ratio")
    lines.append(
        valid.groupby("country")[VALUE_COL]
        .mean()
        .sort_values(ascending=False)
        .head(20)
        .round(2)
        .to_string()
    )
    lines.append("")
    lines.append("Invalid-fill countries")
    lines.append(
        invalid["country"].value_counts().to_string() if not invalid.empty else "None"
    )
    OUT_CHECKS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def draw_map(districts: gpd.GeoDataFrame, countries: gpd.GeoDataFrame) -> None:
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
            "font.size": BASE_FONT_SIZE,
            "axes.titlesize": BASE_FONT_SIZE,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )

    colors = ["#fbf4d8", "#f1df9d", "#e3c46a", "#c89a3c", "#8b6217"]
    cmap = ListedColormap(colors, name="district_amplification_yellow_steps")
    norm = BoundaryNorm(BOUNDS, cmap.N, clip=True)

    fig = plt.figure(figsize=FIGSIZE, dpi=DPI)
    ax = fig.add_axes([0.06, 0.28, 0.88, 0.62])

    no_fill_color = "#f5f2ed"
    district_edge = "#efe8e1"
    country_edge = "#c7c2bb"

    valid, invalid = split_valid_invalid(districts)

    if not invalid.empty:
        invalid.plot(
            ax=ax,
            color=no_fill_color,
            edgecolor=district_edge,
            linewidth=0.06,
            hatch="////",
            zorder=1,
        )

    valid[VALUE_COL] = valid[VALUE_COL].clip(lower=BOUNDS[0], upper=BOUNDS[-1])
    valid.plot(
        ax=ax,
        column=VALUE_COL,
        cmap=cmap,
        norm=norm,
        edgecolor=district_edge,
        linewidth=0.05,
        zorder=2,
    )

    countries.boundary.plot(ax=ax, color=country_edge, linewidth=0.42, zorder=3)

    minx, miny, maxx, maxy = districts.total_bounds
    xpad = (maxx - minx) * 0.05
    ypad = (maxy - miny) * 0.04
    ax.set_xlim(minx - xpad, maxx + xpad)
    ax.set_ylim(miny - ypad, maxy + ypad)
    ax.set_aspect("equal")
    ax.axis("off")

    no_fill_ax = fig.add_axes([0.08, 0.20, 0.30, 0.04])
    no_fill_ax.axis("off")
    no_fill_ax.add_patch(
        Rectangle(
            (0.00, 0.20),
            0.18,
            0.58,
            facecolor=no_fill_color,
            edgecolor=country_edge,
            linewidth=0.45,
            hatch="////",
            transform=no_fill_ax.transAxes,
        )
    )
    no_fill_ax.text(
        0.25,
        0.50,
        "No fill",
        ha="left",
        va="center",
        fontsize=BASE_FONT_SIZE,
        transform=no_fill_ax.transAxes,
    )

    fig.text(0.08, 0.145, VALUE_LABEL, ha="left", va="center", fontsize=BASE_FONT_SIZE)

    cax = fig.add_axes([0.14, 0.095, 0.68, 0.024])
    colorbar = mpl.colorbar.ColorbarBase(
        cax,
        cmap=cmap,
        norm=norm,
        boundaries=BOUNDS,
        ticks=TICK_POSITIONS,
        spacing="uniform",
        orientation="horizontal",
    )
    colorbar.set_ticklabels(TICK_LABELS)
    colorbar.ax.tick_params(labelsize=BASE_FONT_SIZE, length=0, pad=3.0)
    colorbar.outline.set_linewidth(0.45)

    fig.text(
        0.92,
        0.040,
        "Darker hues = stronger amplification",
        ha="right",
        va="center",
        fontsize=BASE_FONT_SIZE - 0.4,
        color="#6b6761",
    )

    fig.savefig(OUT_PNG, dpi=DPI, facecolor="white")
    fig.savefig(OUT_PDF, facecolor="white")
    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    districts, countries = load_inputs()
    save_checks(districts)
    draw_map(districts, countries)
    print(f"Saved PNG: {OUT_PNG}")
    print(f"Saved PDF: {OUT_PDF}")
    print(f"Saved checks: {OUT_CHECKS}")


if __name__ == "__main__":
    main()
