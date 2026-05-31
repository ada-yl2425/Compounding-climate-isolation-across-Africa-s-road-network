#!/usr/bin/env python3

import argparse
import sqlite3
import struct
import subprocess
from pathlib import Path
from typing import Iterable, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
QGIS_PYTHON = "/Applications/QGIS.app/Contents/MacOS/python"
BACKGROUND_SCRIPT = ROOT / "export_unpaved_background_qgis.py"
COMPOSE_SCRIPT = ROOT / "compose_unpaved_lines_hr.py"
BACKGROUND_PATH = ROOT / "_unpaved_background.png"
ROAD_COLOR_PATH = ROOT / "_unpaved_roads_color.png"
TILE_DIR = ROOT / "_unpaved_tile_cache"

DATA_CANDIDATES = [
    Path("/Users/suhang/Downloads/unpaved_delta_v (1).gpkg"),
    Path("/Users/suhang/Downloads/unpaved_delta_v.gpkg"),
    ROOT / "unpaved_delta_v.gpkg",
]

XMIN, YMIN, XMAX, YMAX = -19.24, -36.63, 52.70, 39.14
XSPAN = XMAX - XMIN
YSPAN = YMAX - YMIN

MAP_W = 3600
MAP_H = 3788
COLS = 4
ROWS = 4
LINE_WIDTH = 2
BATCH_SIZE = 4000

RED_RAMP = ["#f9ddda", "#f1b2aa", "#dd776d", "#b43d33", "#701813"]
ENV_SIZES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def resolve_data_path() -> Path:
    for path in DATA_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("No unpaved_delta_v gpkg file found in expected locations")


DATA_PATH = resolve_data_path()


def export_background() -> None:
    cmd = [
        QGIS_PYTHON,
        str(BACKGROUND_SCRIPT),
        "--output",
        str(BACKGROUND_PATH),
        "--width",
        str(MAP_W),
        "--height",
        str(MAP_H),
        "--dpi",
        "520",
        "--mode",
        "background",
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)


def bin_index(loss: float) -> int:
    if loss < 5:
        return 0
    if loss < 10:
        return 1
    if loss < 15:
        return 2
    if loss < 20:
        return 3
    return 4


def geometry_offset_and_bounds(blob: bytes) -> Tuple[int, Optional[Tuple[float, float, float, float]]]:
    flags = blob[3]
    endian = "<" if (flags & 1) else ">"
    env_code = (flags >> 1) & 0b111
    env_size = ENV_SIZES[env_code]
    bounds = None
    if env_size >= 32:
        minx, maxx, miny, maxy = struct.unpack_from(endian + "dddd", blob, 8)
        bounds = (minx, miny, maxx, maxy)
    return 8 + env_size, bounds


def iter_lines(blob: bytes) -> Iterable[np.ndarray]:
    geom_offset, _ = geometry_offset_and_bounds(blob)
    mv = memoryview(blob)
    byte_order = mv[geom_offset]
    endian = "<" if byte_order == 1 else ">"
    geom_type = struct.unpack_from(endian + "I", mv, geom_offset + 1)[0] % 1000

    if geom_type == 2:
        line_starts = [geom_offset]
    elif geom_type == 5:
        line_count = struct.unpack_from(endian + "I", mv, geom_offset + 5)[0]
        line_starts = []
        offset = geom_offset + 9
        for _ in range(line_count):
            sub_byte_order = mv[offset]
            sub_endian = "<" if sub_byte_order == 1 else ">"
            point_count = struct.unpack_from(sub_endian + "I", mv, offset + 5)[0]
            line_starts.append(offset)
            offset += 9 + point_count * 16
    else:
        return

    for start in line_starts:
        sub_byte_order = mv[start]
        sub_endian = "<" if sub_byte_order == 1 else ">"
        point_count = struct.unpack_from(sub_endian + "I", mv, start + 5)[0]
        if point_count < 2:
            continue
        dtype = np.dtype("<f8" if sub_endian == "<" else ">f8")
        coord_offset = start + 9
        coords = np.frombuffer(mv[coord_offset : coord_offset + point_count * 16], dtype=dtype).reshape(point_count, 2)
        yield coords


def tile_bounds(col: int, row: int) -> Tuple[int, int, int, int, float, float, float, float]:
    x0 = round(col * MAP_W / COLS)
    x1 = round((col + 1) * MAP_W / COLS)
    y0 = round(row * MAP_H / ROWS)
    y1 = round((row + 1) * MAP_H / ROWS)

    lon0 = XMIN + (x0 / MAP_W) * XSPAN
    lon1 = XMIN + (x1 / MAP_W) * XSPAN
    lat1 = YMAX - (y0 / MAP_H) * YSPAN
    lat0 = YMAX - (y1 / MAP_H) * YSPAN
    return x0, x1, y0, y1, lon0, lat0, lon1, lat1


def tile_path(col: int, row: int) -> Path:
    return TILE_DIR / f"tile_r{row}_c{col}.png"


def render_tile(col: int, row: int, force: bool = False) -> None:
    output = tile_path(col, row)
    if output.exists() and not force:
        print(f"skip tile r{row} c{col}: cache exists")
        return

    x0, x1, y0, y1, lon0, lat0, lon1, lat1 = tile_bounds(col, row)
    tile_w = x1 - x0
    tile_h = y1 - y0
    x_scale = (tile_w - 1) / (lon1 - lon0)
    y_scale = (tile_h - 1) / (lat1 - lat0)

    print(
        f"render tile r{row} c{col}: px=({x0},{y0})-({x1},{y1}) "
        f"bbox=({lon0:.2f},{lat0:.2f},{lon1:.2f},{lat1:.2f})"
    )

    masks = [Image.new("L", (tile_w, tile_h), 0) for _ in RED_RAMP]
    drawers = [ImageDraw.Draw(mask) for mask in masks]

    conn = sqlite3.connect(f"file:{DATA_PATH}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -200000")
    conn.execute("PRAGMA mmap_size = 1073741824")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.geom, d.delta_V_pct
        FROM unpaved_delta_v AS d
        JOIN rtree_unpaved_delta_v_geom AS r
          ON d.fid = r.id
        WHERE r.minx <= ?
          AND r.maxx >= ?
          AND r.miny <= ?
          AND r.maxy >= ?
          AND d.delta_V_pct IS NOT NULL
        """,
        (lon1, lon0, lat1, lat0),
    )

    processed = 0
    drawn = 0
    while True:
        rows = cur.fetchmany(BATCH_SIZE)
        if not rows:
            break

        for geom, loss in rows:
            processed += 1
            fixed_loss = 0.0 if loss is None or loss < 0 else float(loss)
            bidx = bin_index(fixed_loss)

            for coords in iter_lines(geom):
                xs = coords[:, 0]
                ys = coords[:, 1]
                if xs.max() < lon0 or xs.min() > lon1 or ys.max() < lat0 or ys.min() > lat1:
                    continue

                px = np.rint((xs - lon0) * x_scale).astype(np.int32)
                py = np.rint((lat1 - ys) * y_scale).astype(np.int32)
                points = list(zip(px.tolist(), py.tolist()))
                drawers[bidx].line(points, fill=255, width=LINE_WIDTH)
                drawn += 1

        if processed % 100000 == 0:
            print(f"tile r{row} c{col}: processed {processed} features, drew {drawn} polylines")

    conn.close()

    overlay = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
    for mask, color in zip(masks, RED_RAMP):
        solid = Image.new("RGBA", (tile_w, tile_h), color)
        overlay.paste(solid, (0, 0), mask)
    output.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output, dpi=(600, 600))
    print(f"saved tile r{row} c{col} -> {output.name}")


def merge_tiles() -> None:
    canvas = Image.new("RGBA", (MAP_W, MAP_H), (0, 0, 0, 0))
    for row in range(ROWS):
        for col in range(COLS):
            path = tile_path(col, row)
            if not path.exists():
                raise FileNotFoundError(f"Missing tile image: {path}")
            tile = Image.open(path).convert("RGBA")
            x0, _, y0, _, _, _, _, _ = tile_bounds(col, row)
            canvas.alpha_composite(tile, (x0, y0))
    canvas.save(ROAD_COLOR_PATH, dpi=(600, 600))
    print(f"merged overlay -> {ROAD_COLOR_PATH.name}")


def tile_sequence(only_index: Optional[int]) -> Iterable[Tuple[int, int]]:
    for row in range(ROWS):
        for col in range(COLS):
            idx = row * COLS + col
            if only_index is None or only_index == idx:
                yield col, row


def compose_final() -> None:
    subprocess.run(["python3", str(COMPOSE_SCRIPT)], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only-tile", type=int, default=None, help="0-based tile index in row-major order")
    parser.add_argument("--skip-compose", action="store_true")
    parser.add_argument("--skip-background", action="store_true")
    args = parser.parse_args()

    print(f"using data: {DATA_PATH}")

    if not args.skip_background:
        export_background()

    TILE_DIR.mkdir(parents=True, exist_ok=True)

    for col, row in tile_sequence(args.only_tile):
        render_tile(col, row, force=args.force)

    if args.only_tile is None:
        merge_tiles()
        if not args.skip_compose:
            compose_final()


if __name__ == "__main__":
    main()
