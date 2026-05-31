#!/usr/bin/env python3
import os
import sqlite3
import struct
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path.cwd() / ".mplconfig"))
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.font_manager as font_manager
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.colors import LinearSegmentedColormap, PowerNorm
from matplotlib.patches import Polygon


WORKDIR = Path(__file__).resolve().parent
GPKG = Path(
    "/Users/suhang/Library/Containers/com.tencent.xinWeChat/Data/Documents/"
    "xwechat_files/Suhang1995522_c823/temp/drag/health_facility_pw_delta_t.gpkg"
)
TABLE = "health_facility_pw_delta_t"
VALUE_FIELD = "pw_delta_t"
COUNTRIES_SHP = WORKDIR / "ne_50m_admin_0_countries" / "ne_50m_admin_0_countries.shp"
OUT_PNG = WORKDIR / "africa_climate_isolation_points.png"
OUT_PDF = WORKDIR / "africa_climate_isolation_points.pdf"

MAP_PADDING_DEGREES = 1.0


def read_dbf_column(dbf_path, column):
    """Read a single text column from the shapefile DBF table."""
    values = []
    with open(dbf_path, "rb") as f:
        header = f.read(32)
        n_records = int.from_bytes(header[4:8], "little")
        header_len = int.from_bytes(header[8:10], "little")
        record_len = int.from_bytes(header[10:12], "little")

        fields = []
        offset = 1
        while True:
            descriptor = f.read(32)
            if descriptor[0] == 0x0D:
                break
            name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii", "ignore")
            length = descriptor[16]
            fields.append((name, offset, length))
            offset += length

        lookup = {name: (start, length) for name, start, length in fields}
        if column not in lookup:
            raise KeyError(f"{column} not found in {dbf_path}")

        start, length = lookup[column]
        f.seek(header_len)
        for _ in range(n_records):
            record = f.read(record_len)
            if not record or record[0:1] == b"*":
                values.append(None)
                continue
            raw = record[start : start + length]
            values.append(raw.decode("utf-8", "ignore").replace("\x00", "").strip())
    return values


def read_shp_polygon_parts(shp_path, xlim, ylim, continent="Africa"):
    """Read polygon parts from a shapefile without external GIS dependencies."""
    parts = []
    continents = read_dbf_column(shp_path.with_suffix(".dbf"), "CONTINENT")
    with open(shp_path, "rb") as f:
        f.read(100)
        record_idx = 0
        while True:
            record_header = f.read(8)
            if len(record_header) < 8:
                break
            _, content_len_words = struct.unpack(">2i", record_header)
            content = f.read(content_len_words * 2)
            is_target_continent = (
                record_idx < len(continents) and continents[record_idx] == continent
            )
            record_idx += 1
            if not is_target_continent:
                continue
            if len(content) < 44:
                continue

            shape_type = struct.unpack("<i", content[:4])[0]
            if shape_type not in (5, 15, 25):
                continue

            xmin, ymin, xmax, ymax = struct.unpack("<4d", content[4:36])
            if xmax < xlim[0] or xmin > xlim[1] or ymax < ylim[0] or ymin > ylim[1]:
                continue

            n_parts, n_points = struct.unpack("<2i", content[36:44])
            part_starts = list(struct.unpack(f"<{n_parts}i", content[44 : 44 + 4 * n_parts]))
            point_offset = 44 + 4 * n_parts
            points = np.frombuffer(
                content, dtype="<f8", count=n_points * 2, offset=point_offset
            ).reshape(-1, 2)

            for idx, start in enumerate(part_starts):
                end = part_starts[idx + 1] if idx + 1 < n_parts else n_points
                part = points[start:end]
                if len(part) >= 3:
                    parts.append(part.copy())
    return parts


def read_points():
    query = f"""
        SELECT lon, lat, {VALUE_FIELD}
        FROM {TABLE}
        WHERE lon IS NOT NULL
          AND lat IS NOT NULL
          AND {VALUE_FIELD} IS NOT NULL
    """
    with sqlite3.connect(GPKG) as con:
        df = pd.read_sql_query(query, con)
    df = df[np.isfinite(df["lon"]) & np.isfinite(df["lat"]) & np.isfinite(df[VALUE_FIELD])].copy()
    return df


def choose_english_font():
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in ("Times New Roman", "Times", "DejaVu Serif"):
        if name in available:
            return name
    return "DejaVu Serif"


def plot_bounds(df):
    xlim = (
        float(df["lon"].min()) - MAP_PADDING_DEGREES,
        float(df["lon"].max()) + MAP_PADDING_DEGREES,
    )
    ylim = (
        float(df["lat"].min()) - MAP_PADDING_DEGREES,
        float(df["lat"].max()) + MAP_PADDING_DEGREES,
    )
    return xlim, ylim


def degree_labels(values, axis):
    labels = []
    for value in values:
        if axis == "lon":
            suffix = "W" if value < 0 else "E" if value > 0 else ""
        else:
            suffix = "S" if value < 0 else "N" if value > 0 else ""
        labels.append(f"{abs(int(value))}°{suffix}")
    return labels


def smoothed_marginal_profile(df, coord, bounds, bin_width=1.0):
    bins = np.arange(np.floor(bounds[0]), np.ceil(bounds[1]) + bin_width, bin_width)
    totals, edges = np.histogram(df[coord], bins=bins, weights=df[VALUE_FIELD])
    centers = (edges[:-1] + edges[1:]) / 2
    kernel = np.array([1, 2, 3, 2, 1], dtype=float)
    kernel /= kernel.sum()
    totals = np.convolve(totals, kernel, mode="same")
    if totals.max() > 0:
        totals = totals / totals.max()
    return centers, totals


def cumulative_loss_profile(values):
    ordered = np.sort(values[values > 0])[::-1]
    facility_share = np.arange(1, len(ordered) + 1) / len(values) * 100
    loss_share = np.cumsum(ordered) / ordered.sum() * 100
    return facility_share, loss_share


def main():
    if not GPKG.exists():
        raise FileNotFoundError(GPKG)
    if not COUNTRIES_SHP.exists():
        raise FileNotFoundError(COUNTRIES_SHP)

    font_name = choose_english_font()
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": [font_name, "Times New Roman", "DejaVu Serif"],
            "axes.unicode_minus": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    df = read_points()
    xlim, ylim = plot_bounds(df)
    country_parts = read_shp_polygon_parts(COUNTRIES_SHP, xlim, ylim)
    values = df[VALUE_FIELD].to_numpy()
    vmax = float(np.nanquantile(values, 0.99))
    vmedian = float(np.nanmedian(values))
    vmax_actual = float(np.nanmax(values))

    order = np.argsort(values)
    df = df.iloc[order]
    values = values[order]

    cmap = LinearSegmentedColormap.from_list(
        "climate_isolation",
        ["#d7f0f2", "#65c3c8", "#2477a3", "#42307d", "#bf2c7a", "#f26b38", "#b11226"],
    )
    cmap.set_over("#66000d")
    norm = PowerNorm(gamma=0.42, vmin=0, vmax=vmax)

    lon_centers, lon_profile = smoothed_marginal_profile(df, "lon", xlim)
    lat_centers, lat_profile = smoothed_marginal_profile(df, "lat", ylim)
    facility_share, loss_share = cumulative_loss_profile(values)
    top_10_share = float(np.interp(10, facility_share, loss_share))

    fig = plt.figure(figsize=(10.8, 10.1), dpi=300)
    ax = fig.add_axes([0.175, 0.185, 0.765, 0.680])
    ax_lat = fig.add_axes([0.090, 0.185, 0.060, 0.680], sharey=ax)
    ax_lon = fig.add_axes([0.175, 0.125, 0.765, 0.045], sharex=ax)
    ax.set_facecolor("#f5fbff")

    land_patches = [Polygon(part, closed=True) for part in country_parts]
    ax.add_collection(
        PatchCollection(
            land_patches,
            facecolor="#f1f0e8",
            edgecolor="none",
            linewidth=0,
            zorder=1,
        )
    )
    ax.add_collection(
        LineCollection(
            country_parts,
            colors="#9b9b90",
            linewidths=0.35,
            alpha=0.9,
            zorder=2,
        )
    )

    scatter = ax.scatter(
        df["lon"],
        df["lat"],
        c=values,
        s=3.2,
        cmap=cmap,
        norm=norm,
        alpha=0.82,
        linewidths=0,
        zorder=3,
        rasterized=True,
    )

    ax.add_collection(
        LineCollection(
            country_parts,
            colors="#5e5e58",
            linewidths=0.28,
            alpha=0.65,
            zorder=4,
        )
    )

    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal", adjustable="box")
    xticks = np.arange(-20, 56, 10)
    yticks = np.arange(-30, 41, 10)
    xticks = xticks[(xticks >= xlim[0]) & (xticks <= xlim[1])]
    yticks = yticks[(yticks >= ylim[0]) & (yticks <= ylim[1])]
    ax.set_xticks(xticks)
    ax.set_yticks(yticks)
    ax.set_xticklabels([])
    ax.set_yticklabels([])
    ax.tick_params(length=0)
    ax.grid(color="#d8e3e7", linewidth=0.45, linestyle="--", zorder=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.suptitle(
        "Climate-induced health-facility isolation across Africa",
        fontsize=22,
        y=0.970,
        weight="bold",
    )
    fig.text(
        0.060,
        0.932,
        f"Facility-level estimates are coloured by {VALUE_FIELD}; values above the 99th percentile ({vmax:.3f}) are capped for visual contrast.",
        ha="left",
        va="bottom",
        fontsize=12.5,
        color="#4a4a4a",
    )

    ax_lat.fill_betweenx(
        lat_centers,
        0,
        lat_profile,
        color="#c75546",
        alpha=0.92,
        linewidth=0,
    )
    ax_lat.plot(lat_profile, lat_centers, color="#9f332c", linewidth=1.4)
    ax_lat.set_xlim(1.35, 0)
    ax_lat.set_ylim(*ylim)
    ax_lat.set_xticks([])
    ax_lat.set_yticks(yticks)
    ax_lat.set_yticklabels(degree_labels(yticks, "lat"), fontsize=11.5)
    ax_lat.yaxis.tick_right()
    ax_lat.tick_params(axis="y", length=5, width=1.0, pad=7)
    ax_lat.set_ylabel("Latitude", fontsize=13, labelpad=12)
    ax_lat.set_title("Latitudinal\nprofile", fontsize=12.5, pad=8)
    for side in ("top", "bottom", "left"):
        ax_lat.spines[side].set_visible(False)
    ax_lat.spines["right"].set_color("#777777")
    ax_lat.spines["right"].set_linewidth(0.8)

    ax_lon.fill_between(
        lon_centers,
        0,
        lon_profile,
        color="#c75546",
        alpha=0.92,
        linewidth=0,
    )
    ax_lon.plot(lon_centers, lon_profile, color="#9f332c", linewidth=1.4)
    ax_lon.set_xlim(*xlim)
    ax_lon.set_ylim(0, 1.45)
    ax_lon.set_yticks([])
    ax_lon.set_xticks(xticks)
    ax_lon.set_xticklabels(degree_labels(xticks, "lon"), fontsize=11.5)
    ax_lon.tick_params(axis="x", length=5, width=1.0, pad=7)
    ax_lon.set_xlabel("Longitude", fontsize=13, labelpad=7)
    ax_lon.text(
        0.98,
        0.88,
        "Longitudinal profile",
        transform=ax_lon.transAxes,
        ha="right",
        va="top",
        fontsize=12.5,
        color="#4a4a4a",
    )
    for side in ("top", "left", "right"):
        ax_lon.spines[side].set_visible(False)
    ax_lon.spines["bottom"].set_color("#777777")
    ax_lon.spines["bottom"].set_linewidth(0.8)

    inset = ax.inset_axes([0.055, 0.205, 0.315, 0.245])
    inset.set_facecolor((1, 1, 1, 0.92))
    keep = facility_share <= 20
    inset.plot(facility_share[keep], loss_share[keep], color="#263f4f", linewidth=2.0)
    inset.scatter([10], [top_10_share], s=18, color="#263f4f", zorder=3)
    inset.axvline(10, color="#777777", linewidth=0.8, linestyle="--")
    inset.axhline(top_10_share, color="#777777", linewidth=0.8, linestyle="--")
    inset.text(
        0.97,
        0.10,
        f"Top 10%: {top_10_share:.1f}%",
        transform=inset.transAxes,
        ha="right",
        va="bottom",
        fontsize=9.5,
        color="#263f4f",
    )
    inset.set_xlim(0, 20)
    inset.set_ylim(0, 100)
    inset.set_title("Concentration of loss", fontsize=11.5, pad=3)
    inset.set_xlabel("Facilities ranked by loss (%)", fontsize=9.5, labelpad=1)
    inset.set_ylabel("Cumulative loss (%)", fontsize=9.5, labelpad=2)
    inset.tick_params(axis="both", labelsize=8.8, length=2.5, pad=1.5)
    inset.grid(color="#e1e5e8", linewidth=0.5, linestyle="-", zorder=0)
    for spine in inset.spines.values():
        spine.set_color("#5e5e58")
        spine.set_linewidth(0.7)

    cax = ax.inset_axes([0.055, 0.075, 0.350, 0.028])
    cbar = fig.colorbar(scatter, cax=cax, orientation="horizontal", extend="max")
    cbar.set_label("Accessibility loss (pw_delta_t)", fontsize=9.5, labelpad=2)
    ticks = [0, 0.05, 0.10, 0.20, vmax]
    ticks = sorted({round(t, 4) for t in ticks if 0 <= t <= vmax})
    cbar.set_ticks(ticks)
    cbar.set_ticklabels([f"{t:.3f}" for t in ticks])
    cbar.ax.tick_params(labelsize=8.8, length=2.5, pad=1.5)
    cbar.outline.set_linewidth(0.7)

    ax.tick_params(axis="both", which="both", labelleft=False, labelbottom=False)
    plt.setp(ax.get_xticklabels(), visible=False)
    plt.setp(ax.get_yticklabels(), visible=False)

    fig.savefig(OUT_PNG, dpi=600, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT_PDF, bbox_inches="tight", facecolor="white")
    print(f"Saved {OUT_PNG}")
    print(f"Saved {OUT_PDF}")
    print(f"n={len(df)} median={vmedian:.6f} q99={vmax:.6f} max={vmax_actual:.6f}")
    print(f"xlim={xlim} ylim={ylim} africa_parts={len(country_parts)}")


if __name__ == "__main__":
    main()
