#!/usr/bin/env python3
"""Draw loss and post-paving recovery maps from accessibility_nodes."""

from __future__ import annotations

import argparse
import csv
import math
import sqlite3
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent
RESULT_DIR = ROOT / "result 3"
OUTPUT_STEM = "paving_loss_recovery_triptych"

DATA_CANDIDATES = [
    Path(
        "/Users/suhang/Library/Containers/com.tencent.xinWeChat/Data/Documents/"
        "xwechat_files/Suhang1995522_c823/temp/drag/paving_accessibility_heatmap.gpkg"
    ),
    ROOT / "paving_accessibility_heatmap.gpkg",
]

BACKGROUND_PATH = ROOT / "_unpaved_background.png"

XMIN, YMIN, XMAX, YMAX = -19.24, -36.63, 52.70, 39.14
XSPAN = XMAX - XMIN
YSPAN = YMAX - YMIN
MAP_W = 3600
MAP_H = 3788

DPI = 600
MARGIN_X = 170
TOP_MARGIN = 54
MAIN_TITLE_H = 138
PANEL_TITLE_H = 138
PANEL_GAP = 150
MAP_Y = TOP_MARGIN + MAIN_TITLE_H + PANEL_TITLE_H
LEGEND_TOP_GAP = 98
LEGEND_H = 430
CANVAS_W = MARGIN_X * 2 + MAP_W * 3 + PANEL_GAP * 2
CANVAS_H = MAP_Y + MAP_H + LEGEND_TOP_GAP + LEGEND_H

FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"

TEXT_DARK = "#202020"
TEXT_MID = "#666666"
TEXT_LIGHT = "#777777"

VALUE_CAP = 20.0
GAMMA = 0.48
LEGEND_TICKS = [0, 1, 2, 5, 10, 20]
VALUE_TRANSFORM = "power"
ASINH_SCALE = 1.0
TICK_UNIT = "plain"
POINT_ALPHA_SCALE = 1.0
FIGURE_TITLE = "Accessibility loss and recovery after targeted paving"
LOSS_LEGEND_TITLE = "Loss under extreme climate (%)"
RECOVERY_LEGEND_TITLE = "Recovery after paving (%)"
LEGEND_NOTE = "Only positive values are colored; zero means no loss or no recovery. Continuous stretch expands the 1-10% range."
FIELD_NOTE = "Fields: loss_extreme, recovery_001, recovery_020"

PANELS = [
    {
        "field": "loss_extreme",
        "title": "Extreme-climate loss",
        "subtitle": "loss_extreme",
        "palette": "red",
    },
    {
        "field": "recovery_001",
        "title": "Recovery after paving 0.1%",
        "subtitle": "recovery_001",
        "palette": "blue",
    },
    {
        "field": "recovery_020",
        "title": "Recovery after paving 2%",
        "subtitle": "recovery_020",
        "palette": "blue",
    },
]

PALETTES = {
    "red": [
        (0.00, "#fff0e8"),
        (0.18, "#ffd2c4"),
        (0.36, "#f7a58f"),
        (0.58, "#ee7862"),
        (0.78, "#dc4e3f"),
        (1.00, "#b72b25"),
    ],
    "blue": [
        (0.00, "#eef7fb"),
        (0.18, "#cce6f2"),
        (0.36, "#9ed0e4"),
        (0.58, "#66b0d0"),
        (0.78, "#2f8bb8"),
        (1.00, "#146a98"),
    ],
}


def resolve_data_path() -> Path:
    return resolve_data_path_from(None)


def resolve_data_path_from(data_path: Path | None) -> Path:
    if data_path is not None:
        if data_path.exists():
            return data_path
        raise FileNotFoundError(f"Input GeoPackage not found: {data_path}")
    for path in DATA_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("No paving_accessibility_heatmap.gpkg file found.")


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size=size)
    except OSError:
        return ImageFont.load_default()


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


RAMP_RGB = {
    name: [(pos, hex_to_rgb(color)) for pos, color in stops]
    for name, stops in PALETTES.items()
}


def interpolate_color(t: float, palette: str) -> tuple[int, int, int]:
    t = min(1.0, max(0.0, t))
    ramp = RAMP_RGB[palette]
    for (p0, c0), (p1, c1) in zip(ramp, ramp[1:]):
        if t <= p1:
            local = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            return tuple(int(round(c0[i] + (c1[i] - c0[i]) * local)) for i in range(3))
    return ramp[-1][1]


def value_to_t(value: float) -> float:
    if value <= 0:
        return 0.0
    clipped = min(value, VALUE_CAP)
    if VALUE_TRANSFORM == "asinh":
        return math.asinh(clipped / ASINH_SCALE) / math.asinh(VALUE_CAP / ASINH_SCALE)
    return (clipped / VALUE_CAP) ** GAMMA


def format_tick(value: float) -> str:
    if TICK_UNIT == "compact":
        if value >= VALUE_CAP:
            return f">={VALUE_CAP / 1_000_000:g}M"
        if value >= 1_000_000:
            return f"{value / 1_000_000:g}M"
        if value >= 1_000:
            return f"{value / 1_000:g}k"
        return f"{value:g}"
    if value >= VALUE_CAP:
        return f">={VALUE_CAP:g}"
    return f"{value:g}"


def map_xy(lon: float, lat: float) -> tuple[int, int]:
    x = int(round((lon - XMIN) / XSPAN * (MAP_W - 1)))
    y = int(round((YMAX - lat) / YSPAN * (MAP_H - 1)))
    return x, y


def fetch_points(data_path: Path, field: str) -> list[tuple[float, float, float]]:
    conn = sqlite3.connect(f"file:{data_path}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    try:
        cur = conn.execute(
            f"""
            SELECT lon, lat, {field}
            FROM accessibility_nodes
            WHERE lon IS NOT NULL
              AND lat IS NOT NULL
              AND {field} IS NOT NULL
            ORDER BY fid
            """
        )
        return [(float(lon), float(lat), float(value)) for lon, lat, value in cur]
    finally:
        conn.close()


def summarize_data(points_by_field: dict[str, list[tuple[float, float, float]]]) -> list[dict[str, object]]:
    def quantile(sorted_values: list[float], q: float) -> float | str:
        if not sorted_values:
            return ""
        if len(sorted_values) == 1:
            return sorted_values[0]
        pos = (len(sorted_values) - 1) * q
        low = int(math.floor(pos))
        high = int(math.ceil(pos))
        if low == high:
            return sorted_values[low]
        frac = pos - low
        return sorted_values[low] * (1 - frac) + sorted_values[high] * frac

    rows: list[dict[str, object]] = []
    for field, points in points_by_field.items():
        values = [value for _, _, value in points]
        positive = [value for value in values if value > 0]
        positive_sorted = sorted(positive)
        rows.append(
            {
                "field": field,
                "records": len(values),
                "min": min(values) if values else "",
                "max": max(values) if values else "",
                "mean": sum(values) / len(values) if values else "",
                "zero_count": len(values) - len(positive),
                "positive_count": len(positive),
                "positive_mean": sum(positive) / len(positive) if positive else "",
                "positive_max": max(positive) if positive else "",
                "positive_p50": quantile(positive_sorted, 0.50),
                "positive_p90": quantile(positive_sorted, 0.90),
                "positive_p95": quantile(positive_sorted, 0.95),
                "positive_p99": quantile(positive_sorted, 0.99),
                "count_1": sum(1 for value in values if 0 < value <= 1),
                "count_2_5": sum(1 for value in values if 1 < value <= 5),
                "count_6_10": sum(1 for value in values if 5 < value <= 10),
                "count_11_20": sum(1 for value in values if 10 < value <= 20),
                "count_gt20": sum(1 for value in values if value > 20),
            }
        )
    return rows


def render_points(points: list[tuple[float, float, float]], palette: str) -> Image.Image:
    overlay = Image.new("RGBA", (MAP_W, MAP_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    for lon, lat, value in points:
        if value <= 0:
            continue
        if lon < XMIN or lon > XMAX or lat < YMIN or lat > YMAX:
            continue

        x, y = map_xy(lon, lat)
        t = value_to_t(value)
        color = interpolate_color(t, palette)

        halo_alpha = int(round((36 + 118 * t) * POINT_ALPHA_SCALE))
        core_alpha = int(round((120 + 132 * t) * POINT_ALPHA_SCALE))
        halo_r = int(round(12 + 22 * t))
        core_r = int(round(5 + 8 * t))

        point = Image.new("RGBA", (halo_r * 2 + 1, halo_r * 2 + 1), (0, 0, 0, 0))
        point_draw = ImageDraw.Draw(point, "RGBA")
        point_draw.ellipse((0, 0, halo_r * 2, halo_r * 2), fill=(*color, halo_alpha))
        point = point.filter(ImageFilter.GaussianBlur(4.0))
        overlay.alpha_composite(point, (x - halo_r, y - halo_r))

        draw.ellipse((x - core_r, y - core_r, x + core_r, y + core_r), fill=(*color, core_alpha))

    return overlay


def draw_colorbar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    height: int,
    palette: str,
    title: str,
) -> None:
    title_font = load_font(FONT_BOLD, 48)
    tick_font = load_font(FONT_BOLD, 46)

    draw.multiline_text((x, y), title, font=title_font, fill=TEXT_DARK, spacing=8)
    bar_y = y + 128
    for i in range(width):
        t = i / (width - 1)
        color = interpolate_color(t, palette)
        draw.line((x + i, bar_y, x + i, bar_y + height), fill=color, width=1)
    draw.rounded_rectangle((x, bar_y, x + width, bar_y + height), radius=7, outline="#e2e2dc", width=3)

    for tick in LEGEND_TICKS:
        t = value_to_t(float(tick))
        tick_x = x + t * width
        draw.line((tick_x, bar_y + height, tick_x, bar_y + height + 16), fill="#555555", width=4)
        label = format_tick(float(tick))
        bbox = draw.textbbox((0, 0), label, font=tick_font)
        draw.text((tick_x - (bbox[2] - bbox[0]) / 2, bar_y + height + 26), label, font=tick_font, fill="#4f4f4f")


def add_legend(canvas: Image.Image) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    note_font = load_font(FONT_REG, 42)

    legend_y = MAP_Y + MAP_H + LEGEND_TOP_GAP
    bar_w = 1860
    bar_h = 72
    left_x = MARGIN_X
    right_x = MARGIN_X + bar_w + 280

    draw_colorbar(draw, left_x, legend_y, bar_w, bar_h, "red", LOSS_LEGEND_TITLE)
    draw_colorbar(draw, right_x, legend_y, bar_w, bar_h, "blue", RECOVERY_LEGEND_TITLE)

    note_y = legend_y + 292
    draw.text(
        (left_x, note_y),
        LEGEND_NOTE,
        font=note_font,
        fill=TEXT_MID,
    )
    draw.text(
        (CANVAS_W - 2240, note_y),
        FIELD_NOTE,
        font=note_font,
        fill=TEXT_LIGHT,
    )


def save_summary_csv(rows: list[dict[str, object]], path: Path) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def configure_variant(variant: str) -> Path | None:
    global OUTPUT_STEM, PANELS, VALUE_CAP, GAMMA, LEGEND_TICKS
    global VALUE_TRANSFORM, ASINH_SCALE, TICK_UNIT, FIGURE_TITLE
    global LOSS_LEGEND_TITLE, RECOVERY_LEGEND_TITLE, LEGEND_NOTE, FIELD_NOTE
    global POINT_ALPHA_SCALE

    if variant == "rate":
        return None

    OUTPUT_STEM = "paving_att_loss_recovery_triptych"
    PANELS = [
        {
            "field": "pw_delta_att",
            "title": "Climate-attributed loss",
            "subtitle": "pw_delta_att",
            "palette": "red",
        },
        {
            "field": "pw_rec_att_001",
            "title": "Recovery after paving 0.1%",
            "subtitle": "pw_rec_att_001",
            "palette": "blue",
        },
        {
            "field": "pw_rec_att_020",
            "title": "Recovery after paving 2%",
            "subtitle": "pw_rec_att_020",
            "palette": "blue",
        },
    ]
    VALUE_CAP = 25_000_000.0
    GAMMA = 1.0
    LEGEND_TICKS = [0, 10_000, 100_000, 1_000_000, 10_000_000, 25_000_000]
    VALUE_TRANSFORM = "asinh"
    ASINH_SCALE = 1_000.0
    TICK_UNIT = "compact"
    POINT_ALPHA_SCALE = 0.72
    FIGURE_TITLE = "Population-weighted accessibility loss and recovery"
    LOSS_LEGEND_TITLE = "Climate-attributed loss\n(population x percentage points)"
    RECOVERY_LEGEND_TITLE = "Paving-attributed recovery\n(population x percentage points)"
    LEGEND_NOTE = "Only positive values are colored. Shared asinh stretch expands small and middle weighted values; values >=25M use the darkest color."
    FIELD_NOTE = "Fields: pw_delta_att, pw_rec_att_001, pw_rec_att_020"
    return Path("/Users/suhang/Desktop/paving_accessibility_heatmap(1).gpkg")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["rate", "att"], default="rate")
    parser.add_argument("--data", type=Path, default=None)
    args = parser.parse_args()

    default_data = configure_variant(args.variant)
    data_path = resolve_data_path_from(args.data or default_data)
    if not BACKGROUND_PATH.exists():
        raise FileNotFoundError(f"Missing basemap: {BACKGROUND_PATH}")

    background = Image.open(BACKGROUND_PATH).convert("RGBA")
    if background.size != (MAP_W, MAP_H):
        raise ValueError(f"Unexpected basemap size: {background.size}")

    points_by_field = {panel["field"]: fetch_points(data_path, panel["field"]) for panel in PANELS}

    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), "white")
    draw = ImageDraw.Draw(canvas)
    main_font = load_font(FONT_BOLD, 112)
    panel_font = load_font(FONT_BOLD, 72)
    subtitle_font = load_font(FONT_REG, 42)

    draw.text((MARGIN_X, TOP_MARGIN), FIGURE_TITLE, font=main_font, fill=TEXT_DARK)

    for idx, panel_spec in enumerate(PANELS):
        panel_x = MARGIN_X + idx * (MAP_W + PANEL_GAP)
        title_y = TOP_MARGIN + MAIN_TITLE_H + 12
        letter = chr(ord("a") + idx)
        draw.text((panel_x, title_y), f"{letter}  {panel_spec['title']}", font=panel_font, fill=TEXT_DARK)
        draw.text((panel_x, title_y + 78), panel_spec["subtitle"], font=subtitle_font, fill=TEXT_MID)

        panel = background.copy()
        points = points_by_field[panel_spec["field"]]
        overlay = render_points(points, panel_spec["palette"])
        panel = Image.alpha_composite(panel, overlay)
        canvas.alpha_composite(panel, (panel_x, MAP_Y))

    add_legend(canvas)

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    output_png = RESULT_DIR / f"{OUTPUT_STEM}.png"
    output_pdf = RESULT_DIR / f"{OUTPUT_STEM}.pdf"
    output_csv = RESULT_DIR / f"{OUTPUT_STEM}_data_check.csv"

    final_rgb = canvas.convert("RGB")
    final_rgb.save(output_png, dpi=(DPI, DPI))
    final_rgb.save(output_pdf, resolution=float(DPI))
    save_summary_csv(summarize_data(points_by_field), output_csv)

    print(f"using data: {data_path}")
    print(f"variant: {args.variant}")
    print(f"stretch: transform={VALUE_TRANSFORM}, cap={VALUE_CAP:g}, gamma={GAMMA:g}, asinh_scale={ASINH_SCALE:g}; zero values are transparent")
    print(f"saved: {output_png}")
    print(f"saved: {output_pdf}")
    print(f"saved: {output_csv}")


if __name__ == "__main__":
    main()
