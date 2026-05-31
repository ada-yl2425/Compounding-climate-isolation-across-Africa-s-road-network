#!/opt/homebrew/Cellar/python@3.11/3.11.14_1/Frameworks/Python.framework/Versions/3.11/bin/python3.11
"""
Result 1.1 cross-country accessibility loss map.

This version deliberately focuses only on cross-country accessibility loss:
    - grey country basemap with country boundaries
    - red linework for connected cross-country city pairs
    - true city coordinates from Natural Earth populated places

Run:
    /opt/homebrew/Cellar/python@3.11/3.11.14_1/Frameworks/Python.framework/Versions/3.11/bin/python3.11 result1_1_cross_country_loss_map.py
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import unicodedata
from pathlib import Path

OUTPUT_DIR = Path("/Users/suhang/Downloads/同步空间/工作文件/0-1博后论文/4.非洲路网可达性/插图绘制/result 1.1")
os.environ.setdefault("MPLCONFIGDIR", str(OUTPUT_DIR / "_mplconfig"))
(OUTPUT_DIR / "_mplconfig").mkdir(parents=True, exist_ok=True)

import geopandas as gpd
import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize


DATA_DIR = Path(
    "/Users/suhang/Downloads/同步空间/工作文件/0-1博后论文/4.非洲路网可达性/过程文件/result/result1/"
    "finding1_cross_country_road_degradation_heatmap"
)
CITY_SHP = OUTPUT_DIR / "ne_10m_populated_places" / "ne_10m_populated_places.shp"

PAIR_CSV = DATA_DIR / "cross_country_capital_pairs_normal_vs_extreme.csv"
SUMMARY_CSV = DATA_DIR / "cross_country_od_summary_stats.csv"

OUT_SCRIPT_CHECK = OUTPUT_DIR / "result1_1_cross_country_loss_checks.txt"
OUT_COORDS = OUTPUT_DIR / "result1_1_cross_country_city_coordinates.csv"
OUT_PNG = OUTPUT_DIR / "result1_1_cross_country_loss_map.png"
OUT_PDF = OUTPUT_DIR / "result1_1_cross_country_loss_map.pdf"

CM_TO_INCH = 1 / 2.54
FIGSIZE = (9.5 * CM_TO_INCH, 13.0 * CM_TO_INCH)
DPI = 600
BASE_FONT_SIZE = 9.5
COUNTRY_LABEL_SIZE = 7.2
MAP_CRS = "+proj=aea +lat_1=-18 +lat_2=21 +lat_0=0 +lon_0=20 +datum=WGS84 +units=m +no_defs"

LINE_VALUE_COL = "increase_pct"

CITY_TO_ISO3 = {
    "Abidjan": "CIV",
    "Abuja": "NGA",
    "Accra": "GHA",
    "Addis Ababa": "ETH",
    "Alexandria": "EGY",
    "Algiers": "DZA",
    "Antananarivo": "MDG",
    "Asmara": "ERI",
    "Bamako": "MLI",
    "Banghazi": "LBY",
    "Bangui": "CAF",
    "Banjul": "GMB",
    "Benin City": "NGA",
    "Benoni": "ZAF",
    "Bir Lehlou": "ESH",
    "Bissau": "GNB",
    "Bloemfontein": "ZAF",
    "Brazzaville": "COG",
    "Bujumbura": "BDI",
    "Cairo": "EGY",
    "Cape Town": "ZAF",
    "Casablanca": "MAR",
    "Conakry": "GIN",
    "Cotonou": "BEN",
    "Dakar": "SEN",
    "Dar es Salaam": "TZA",
    "Djibouti": "DJI",
    "Dodoma": "TZA",
    "Douala": "CMR",
    "Durban": "ZAF",
    "Fez": "MAR",
    "Freetown": "SLE",
    "Gaborone": "BWA",
    "Harare": "ZWE",
    "Huambo": "AGO",
    "Ibadan": "NGA",
    "Ilorin": "NGA",
    "Johannesburg": "ZAF",
    "Juba": "SSD",
    "Kaduna": "NGA",
    "Kampala": "UGA",
    "Kananga": "COD",
    "Kano": "NGA",
    "Khartoum": "SDN",
    "Kigali": "RWA",
    "Kinshasa": "COD",
    "Kumasi": "GHA",
    "Laayoune": "ESH",
    "Lagos": "NGA",
    "Libreville": "GAB",
    "Lilongwe": "MWI",
    "Lobamba": "SWZ",
    "Lomé": "TGO",
    "Luanda": "AGO",
    "Lubumbashi": "COD",
    "Lusaka": "ZMB",
    "Maiduguri": "NGA",
    "Malabo": "GNQ",
    "Maputo": "MOZ",
    "Marrakesh": "MAR",
    "Maseru": "LSO",
    "Mbuji-Mayi": "COD",
    "Mogadishu": "SOM",
    "Mombasa": "KEN",
    "Monrovia": "LBR",
    "N'Djamena": "TCD",
    "Nairobi": "KEN",
    "Niamey": "NER",
    "Nouakchott": "MRT",
    "Ogbomosho": "NGA",
    "Oran": "DZA",
    "Ouagadougou": "BFA",
    "Port Elizabeth": "ZAF",
    "Port Harcourt": "NGA",
    "Porto-Novo": "BEN",
    "Pretoria": "ZAF",
    "Rabat": "MAR",
    "Tripoli": "LBY",
    "Tunis": "TUN",
    "Vereeniging": "ZAF",
    "Windhoek": "NAM",
    "Yamoussoukro": "CIV",
    "Yaoundé": "CMR",
    "Zaria": "NGA",
}

ISO_EQUIV = {"ESH": "SAH", "SWZ": "SWZ"}
MANUAL_CITY_COORDS = {
    "Laayoune": (-13.2033, 27.1536),
}


def require_files(paths: list[Path]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required file(s):\n" + "\n".join(missing))


def require_columns(df: pd.DataFrame, cols: list[str], label: str) -> None:
    missing = [col for col in cols if col not in df.columns]
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("'", "").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_natural_earth_lowres() -> Path:
    candidates = [
        Path("/opt/homebrew/lib/python3.11/site-packages/pyogrio/tests/fixtures/naturalearth_lowres/naturalearth_lowres.shp"),
        Path("/usr/local/lib/python3.11/site-packages/pyogrio/tests/fixtures/naturalearth_lowres/naturalearth_lowres.shp"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Local Natural Earth country shapefile not found.")


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    require_files([PAIR_CSV, SUMMARY_CSV, CITY_SHP, find_natural_earth_lowres()])

    pairs = pd.read_csv(PAIR_CSV)
    summary = pd.read_csv(SUMMARY_CSV)
    city_points = gpd.read_file(CITY_SHP)
    countries = gpd.read_file(find_natural_earth_lowres())

    require_columns(
        pairs,
        ["city_A", "city_B", "t_normal_h", "t_extreme_h", LINE_VALUE_COL, "conn_type", "severe_increase"],
        "cross-country pair CSV",
    )
    require_columns(summary, ["n_city_pairs", "n_connected", "mean_travel_increase_pct"], "summary CSV")
    require_columns(
        city_points,
        ["NAME", "NAMEASCII", "ADM0_A3", "ADM0NAME", "LATITUDE", "LONGITUDE", "POP_MAX", "geometry"],
        "Natural Earth populated places",
    )

    return pairs, summary, city_points, countries


def prepare_links(pairs: pd.DataFrame) -> pd.DataFrame:
    links = pairs.loc[pairs["conn_type"].eq("connected") & pairs[LINE_VALUE_COL].notna()].copy()
    links["iso_A"] = links["city_A"].map(CITY_TO_ISO3)
    links["iso_B"] = links["city_B"].map(CITY_TO_ISO3)
    links["same_country"] = links["iso_A"].eq(links["iso_B"])
    links = links.loc[~links["same_country"]].copy()

    if links["iso_A"].isna().any() or links["iso_B"].isna().any():
        unmapped = sorted(
            set(links.loc[links["iso_A"].isna(), "city_A"].tolist())
            | set(links.loc[links["iso_B"].isna(), "city_B"].tolist())
        )
        raise ValueError(f"Cross-country city names missing ISO3 mapping: {unmapped}")

    return links


def build_city_coordinate_table(links: pd.DataFrame, city_points: gpd.GeoDataFrame) -> pd.DataFrame:
    unique_city_rows = pd.concat(
        [
            links[["city_A", "iso_A", "level_A"]].rename(
                columns={"city_A": "city", "iso_A": "iso3", "level_A": "level"}
            ),
            links[["city_B", "iso_B", "level_B"]].rename(
                columns={"city_B": "city", "iso_B": "iso3", "level_B": "level"}
            ),
        ],
        ignore_index=True,
    ).drop_duplicates(subset=["city", "iso3"]).reset_index(drop=True)

    city_points = city_points.copy()
    city_points["norm_name"] = city_points["NAME"].map(normalize_name)
    city_points["norm_ascii"] = city_points["NAMEASCII"].map(normalize_name)

    records: list[dict[str, object]] = []
    missing: list[str] = []

    for _, row in unique_city_rows.iterrows():
        iso3 = str(row["iso3"])
        city = str(row["city"])
        level = str(row["level"])
        target_iso = ISO_EQUIV.get(iso3, iso3)
        norm_city = normalize_name(city)

        candidates = city_points.loc[
            city_points["ADM0_A3"].eq(target_iso)
            & (
                city_points["norm_name"].eq(norm_city)
                | city_points["norm_ascii"].eq(norm_city)
            )
        ].copy()

        if candidates.empty:
            if city in MANUAL_CITY_COORDS:
                lon, lat = MANUAL_CITY_COORDS[city]
                records.append(
                    {
                        "city": city,
                        "iso3": iso3,
                        "level": level,
                        "matched_name": city,
                        "matched_country": iso3,
                        "longitude": float(lon),
                        "latitude": float(lat),
                    }
                )
                continue
            missing.append(f"{city} [{iso3}]")
            continue

        candidates = candidates.sort_values(
            by=["POP_MAX", "MEGACITY", "WORLDCITY", "FEATURECLA"],
            ascending=[False, False, False, True],
        )
        best = candidates.iloc[0]
        records.append(
            {
                "city": city,
                "iso3": iso3,
                "level": level,
                "matched_name": best["NAME"],
                "matched_country": best["ADM0NAME"],
                "longitude": float(best["LONGITUDE"]),
                "latitude": float(best["LATITUDE"]),
            }
        )

    if missing:
        raise ValueError("Cities missing Natural Earth coordinates:\n" + "\n".join(missing))

    coords = pd.DataFrame(records).drop_duplicates(subset=["city", "iso3"]).reset_index(drop=True)
    coords.to_csv(OUT_COORDS, index=False)
    return coords


def attach_projected_coordinates(links: pd.DataFrame, coords: pd.DataFrame) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    coord_gdf = gpd.GeoDataFrame(
        coords.copy(),
        geometry=gpd.points_from_xy(coords["longitude"], coords["latitude"]),
        crs="EPSG:4326",
    ).to_crs(MAP_CRS)

    lookup = {
        (row["city"], row["iso3"]): (row.geometry.x, row.geometry.y)
        for _, row in coord_gdf.iterrows()
    }

    linked = links.copy()
    linked["x_A"] = linked.apply(lambda row: lookup[(row["city_A"], row["iso_A"])][0], axis=1)
    linked["y_A"] = linked.apply(lambda row: lookup[(row["city_A"], row["iso_A"])][1], axis=1)
    linked["x_B"] = linked.apply(lambda row: lookup[(row["city_B"], row["iso_B"])][0], axis=1)
    linked["y_B"] = linked.apply(lambda row: lookup[(row["city_B"], row["iso_B"])][1], axis=1)
    return linked, coord_gdf


def prepare_countries(countries: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    africa = countries.loc[countries["continent"].eq("Africa")].copy()
    africa = africa.rename(columns={"iso_a3": "iso3", "name": "country_name"})
    if africa.crs is None:
        africa = africa.set_crs("EPSG:4326")
    return africa.to_crs(MAP_CRS)


def quadratic_arc(x0: float, y0: float, x1: float, y1: float, curvature: float, n: int = 56) -> np.ndarray:
    dx = x1 - x0
    dy = y1 - y0
    dist = math.hypot(dx, dy)
    if dist == 0:
        return np.array([[x0, y0], [x1, y1]])

    mx = (x0 + x1) / 2.0
    my = (y0 + y1) / 2.0
    px = -dy / dist
    py = dx / dist
    cx = mx + px * dist * curvature
    cy = my + py * dist * curvature

    t = np.linspace(0.0, 1.0, n)
    x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t**2 * x1
    y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t**2 * y1
    return np.column_stack([x, y])


def build_line_collection(links: pd.DataFrame, cmap: mpl.colors.Colormap, norm: Normalize) -> LineCollection:
    ordered = links.sort_values(LINE_VALUE_COL).reset_index(drop=True)
    values = ordered[LINE_VALUE_COL].to_numpy(dtype=float)
    v_low = float(np.nanpercentile(values, 10))
    v_high = float(np.nanpercentile(values, 95))
    if not np.isfinite(v_low) or not np.isfinite(v_high) or v_low == v_high:
        v_low = float(np.nanmin(values))
        v_high = float(np.nanmax(values))
    if v_low == v_high:
        v_high = v_low + 1.0

    segments = []
    colors = []
    widths = []
    dist_values = np.hypot(
        ordered["x_B"].to_numpy(dtype=float) - ordered["x_A"].to_numpy(dtype=float),
        ordered["y_B"].to_numpy(dtype=float) - ordered["y_A"].to_numpy(dtype=float),
    )
    d_low = float(np.nanpercentile(dist_values, 10))
    d_high = float(np.nanpercentile(dist_values, 90))
    if not np.isfinite(d_low) or not np.isfinite(d_high) or d_low == d_high:
        d_low = float(np.nanmin(dist_values))
        d_high = float(np.nanmax(dist_values))
    if d_low == d_high:
        d_high = d_low + 1.0

    for _, row in ordered.iterrows():
        stable_hash = int(
            hashlib.md5(
                f"{row['city_A']}|{row['city_B']}|{row['iso_A']}|{row['iso_B']}".encode("utf-8")
            ).hexdigest(),
            16,
        )
        sign = 1 if stable_hash % 2 == 0 else -1

        x0, y0 = float(row["x_A"]), float(row["y_A"])
        x1, y1 = float(row["x_B"]), float(row["y_B"])
        dist = math.hypot(x1 - x0, y1 - y0)
        curvature = sign * float(np.interp(dist, [d_low, d_high], [0.22, 0.11]))
        segments.append(quadratic_arc(x0, y0, x1, y1, curvature=curvature, n=64))
        value = float(row[LINE_VALUE_COL])
        colors.append(cmap(norm(value)))
        widths.append(float(np.interp(value, [v_low, v_high], [0.28, 0.98])))

    return LineCollection(
        segments,
        colors=colors,
        linewidths=widths,
        alpha=0.29,
        capstyle="round",
        joinstyle="round",
        zorder=3,
        rasterized=True,
    )


def save_checks(links: pd.DataFrame, coords: pd.DataFrame, summary: pd.DataFrame) -> None:
    lines = []
    lines.append("Result 1.1 cross-country accessibility loss map checks")
    lines.append("=" * 52)
    lines.append("")
    lines.append(f"Connected cross-country city pairs drawn: {len(links):,}")
    lines.append(f"Unique mapped city coordinates: {len(coords):,}")
    lines.append(f"Mean cross-country travel-time increase: {links[LINE_VALUE_COL].mean():.2f}%")
    lines.append(f"Min / max increase: {links[LINE_VALUE_COL].min():.2f}% / {links[LINE_VALUE_COL].max():.2f}%")
    lines.append("")
    lines.append("Summary CSV row")
    lines.append(summary.to_string(index=False))
    lines.append("")
    lines.append("Top countries by line participation")
    degree = pd.concat([links["iso_A"], links["iso_B"]]).value_counts()
    lines.append(degree.head(20).to_string())
    lines.append("")
    lines.append("Mapped cities")
    lines.append(coords.sort_values(["iso3", "city"]).to_string(index=False))
    OUT_SCRIPT_CHECK.write_text("\n".join(lines) + "\n", encoding="utf-8")


def draw_map(
    countries: gpd.GeoDataFrame,
    links: pd.DataFrame,
    coord_gdf: gpd.GeoDataFrame,
) -> None:
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

    # Desaturated mauve-ink ramp for loss emphasis without red/yellow/blue/green semantics.
    line_cmap = LinearSegmentedColormap.from_list(
        "nature_loss_mauve",
        ["#efe8ee", "#d8c8d6", "#b99bb7", "#84657f", "#4d3846"],
    )
    line_norm = Normalize(vmin=0.0, vmax=80.0)

    fig = plt.figure(figsize=FIGSIZE, dpi=DPI)
    ax = fig.add_axes([0.05, 0.22, 0.90, 0.72])

    countries.plot(
        ax=ax,
        color="#f3f1ec",
        edgecolor="#c7c2bb",
        linewidth=0.55,
        zorder=1,
    )

    line_collection = build_line_collection(links, line_cmap, line_norm)
    ax.add_collection(line_collection)

    coord_gdf.plot(
        ax=ax,
        color="#877d84",
        markersize=4.6,
        alpha=0.42,
        zorder=4,
    )

    minx, miny, maxx, maxy = countries.total_bounds
    xpad = (maxx - minx) * 0.05
    ypad = (maxy - miny) * 0.04
    ax.set_xlim(minx - xpad, maxx + xpad)
    ax.set_ylim(miny - ypad, maxy + ypad)
    ax.set_aspect("equal")
    ax.axis("off")

    fig.text(0.08, 0.145, "Cross-country travel-time increase (%)", ha="left", va="center", fontsize=BASE_FONT_SIZE)

    cax = fig.add_axes([0.14, 0.095, 0.68, 0.022])
    colorbar = mpl.colorbar.ColorbarBase(cax, cmap=line_cmap, norm=line_norm, orientation="horizontal")
    colorbar.set_ticks([0, 20, 40, 60, 80])
    colorbar.ax.tick_params(labelsize=BASE_FONT_SIZE, length=2.5, pad=2.0)
    colorbar.outline.set_linewidth(0.45)

    fig.text(
        0.08,
        0.030,
        f"n = {len(links):,} connected pairs",
        ha="left",
        va="center",
        fontsize=BASE_FONT_SIZE,
        color="#2e2e2e",
    )
    fig.text(
        0.92,
        0.030,
        "Darker hues = stronger losses",
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
    pairs, summary, city_points, countries_raw = load_inputs()
    links = prepare_links(pairs)
    coords = build_city_coordinate_table(links, city_points)
    linked, coord_gdf = attach_projected_coordinates(links, coords)
    countries = prepare_countries(countries_raw)
    save_checks(linked, coords, summary)
    draw_map(countries, linked, coord_gdf)
    print(f"Saved PNG: {OUT_PNG}")
    print(f"Saved PDF: {OUT_PDF}")
    print(f"Saved checks: {OUT_SCRIPT_CHECK}")
    print(f"Saved city coordinates: {OUT_COORDS}")


if __name__ == "__main__":
    main()
