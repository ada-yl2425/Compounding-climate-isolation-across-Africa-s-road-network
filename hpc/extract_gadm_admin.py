"""Extract a reproducible country L2 (or L1 fallback) from GADM 4.1.

The global ``gadm_410.gpkg`` has one layer of finest-available polygons with
GID_0 through GID_5 columns.  Selecting its rows is *not* equivalent to
obtaining L2 boundaries: finer polygons must be dissolved by GID_2.  Countries
without any GID_2 (for example Libya and Lesotho) fall back to GID_1.

This script processes one country at a time; it does not run road, population,
or reviewer-result calculations.  Use a run-specific output path.  A failed QC
produces a JSON report but no geometry output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

AREA_CRS = "EPSG:6933"  # equal-area metres; suitable for African country checks
DEFAULT_AREA_TOLERANCE_KM2 = 0.05


def _nonempty(series):
    return series.fillna("").astype(str).str.strip()


def _union(geometries):
    from shapely import union_all

    return union_all(list(geometries))


def aggregate_country(
    source, country: str, *, area_tolerance_km2: float = DEFAULT_AREA_TOLERANCE_KM2
):
    """Return dissolved GeoDataFrame and QC for one already-loaded country.

    ``source`` may contain other countries (small fixtures), but production
    callers should use an OGR SQL ``where`` filter when reading the global GPKG.
    Geometry is never repaired silently: invalid inputs fail the gate.
    """
    import geopandas as gpd

    country = country.upper()
    if not re.fullmatch(r"[A-Z]{3}", country):
        raise ValueError("country must be a three-letter uppercase ISO code")
    if area_tolerance_km2 < 0:
        raise ValueError("area_tolerance_km2 must be nonnegative")
    if source.crs is None or source.crs.to_epsg() != 4326:
        raise ValueError("GADM source must declare EPSG:4326")
    required = {"GID_0", "GID_1", "GID_2", "NAME_0", "NAME_1", "NAME_2"}
    missing = sorted(required.difference(source.columns))
    if missing:
        raise ValueError(f"GADM source missing columns: {missing}")

    rows = source.loc[_nonempty(source["GID_0"]) == country].copy()
    if rows.empty:
        raise ValueError(f"no GADM polygons for {country}")
    if rows.geometry.isna().any() or rows.geometry.is_empty.any():
        raise ValueError(f"{country}: null/empty source geometry")
    invalid = int((~rows.geometry.is_valid).sum())
    if invalid:
        raise ValueError(
            f"{country}: {invalid} invalid source geometries; no silent repair"
        )

    gid1 = _nonempty(rows["GID_1"])
    gid2 = _nonempty(rows["GID_2"])
    if (gid1 == "").any():
        raise ValueError(f"{country}: GID_1 missing in some source rows")
    if (gid2 != "").all():
        level, key = 2, "GID_2"
    elif (gid2 == "").all():
        level, key = 1, "GID_1"
    else:
        raise ValueError(
            f"{country}: mixed empty/nonempty GID_2; choose an explicit policy"
        )

    rows["GID_0"] = country
    rows["GID_1"] = gid1
    rows["GID_2"] = gid2
    rows["admin_gid"] = rows[key]
    if not rows["admin_gid"].str.startswith(country + ".").all():
        raise ValueError(f"{country}: administrative GIDs do not match country prefix")

    # All original attributes carried to a dissolved unit must agree.  This
    # catches accidental ID collisions and non-identical source versions.
    attributes = ["GID_0", "GID_1", "GID_2", "NAME_0", "NAME_1", "NAME_2"]
    for column in attributes:
        if level == 1 and column in {"GID_2", "NAME_2"}:
            continue
        differing = rows.groupby("admin_gid", dropna=False)[column].nunique(
            dropna=False
        )
        if (differing > 1).any():
            raise ValueError(f"{country}: conflicting {column} within {key} group")

    rows["source_rows"] = 1
    agg = {column: "first" for column in attributes}
    agg["source_rows"] = "sum"
    dissolved = rows.dissolve(by="admin_gid", aggfunc=agg, sort=True).reset_index()
    dissolved.insert(1, "admin_level", level)
    dissolved = gpd.GeoDataFrame(
        dissolved[["admin_gid", "admin_level", *attributes, "source_rows", "geometry"]],
        geometry="geometry",
        crs=source.crs,
    )
    if (
        dissolved["admin_gid"].duplicated().any()
        or not dissolved.geometry.is_valid.all()
    ):
        raise ValueError(f"{country}: dissolved GID/geometry validity failed")

    # Compare *unions*, not summed areas alone: a source polygon split into
    # finer administrative units should have exactly the same country extent.
    source_m = rows.to_crs(AREA_CRS)
    target_m = dissolved.to_crs(AREA_CRS)
    source_union = _union(source_m.geometry)
    target_union = _union(target_m.geometry)
    to_km2 = 1e-6
    symmetric_difference_km2 = (
        source_union.symmetric_difference(target_union).area * to_km2
    )
    source_overlap_km2 = max(
        0.0, (source_m.geometry.area.sum() - source_union.area) * to_km2
    )
    target_overlap_km2 = max(
        0.0, (target_m.geometry.area.sum() - target_union.area) * to_km2
    )
    area_delta_km2 = abs(source_union.area - target_union.area) * to_km2
    qc = {
        "status": "PASS",
        "country": country,
        "admin_level": level,
        "group_key": key,
        "source_crs": str(source.crs),
        "output_crs": str(dissolved.crs),
        "area_crs": AREA_CRS,
        "source_rows": len(rows),
        "target_unique_admin_gid": len(dissolved),
        "source_unique_admin_gid": int(rows["admin_gid"].nunique()),
        "source_union_area_km2": source_union.area * to_km2,
        "target_union_area_km2": target_union.area * to_km2,
        "area_delta_km2": area_delta_km2,
        "symmetric_difference_km2": symmetric_difference_km2,
        "source_overlap_km2": source_overlap_km2,
        "target_overlap_km2": target_overlap_km2,
        "area_tolerance_km2": area_tolerance_km2,
        "invalid_source_geometries": invalid,
        "invalid_target_geometries": 0,
    }
    checks = (
        symmetric_difference_km2,
        area_delta_km2,
        source_overlap_km2,
        target_overlap_km2,
    )
    if any(value > area_tolerance_km2 for value in checks):
        qc["status"] = "FAIL"
        qc["failures"] = [
            key
            for key in (
                "symmetric_difference_km2",
                "area_delta_km2",
                "source_overlap_km2",
                "target_overlap_km2",
            )
            if qc[key] > area_tolerance_km2
        ]
    return dissolved, qc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract(
    input_path: Path,
    output_path: Path,
    report_path: Path,
    country: str,
    *,
    layer: str = "gadm_410",
    area_tolerance_km2: float = DEFAULT_AREA_TOLERANCE_KM2,
) -> dict:
    """Read one country via GDAL attribute filter, QC, then write output."""
    import geopandas as gpd

    country = country.upper()
    if not re.fullmatch(r"[A-Z]{3}", country):
        raise ValueError("country must be a three-letter uppercase ISO code")
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if output_path.suffix.lower() not in {".gpkg", ".parquet"}:
        raise ValueError("output must be .gpkg or .parquet")
    if output_path.exists() or report_path.exists():
        raise FileExistsError(
            "output/report already exists; use a fresh run-specific path"
        )
    if output_path.resolve() == report_path.resolve():
        raise ValueError("output and report paths must differ")

    source = gpd.read_file(input_path, layer=layer, where=f"GID_0 = '{country}'")
    if not source.empty and (_nonempty(source["GID_0"]) != country).any():
        raise RuntimeError("OGR did not honor the country WHERE filter")
    output, qc = aggregate_country(
        source, country, area_tolerance_km2=area_tolerance_km2
    )
    qc["source_file"] = str(input_path.resolve())
    qc["source_layer"] = layer
    qc["output_file"] = str(output_path.resolve()) if qc["status"] == "PASS" else None
    qc["output_layer"] = (
        f"gadm41_{country}_{qc['admin_level']}"
        if output_path.suffix.lower() == ".gpkg"
        else None
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    if qc["status"] == "PASS":
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix.lower() == ".gpkg":
            output.to_file(
                output_path, layer=qc["output_layer"], driver="GPKG", index=False
            )
        else:
            output.to_parquet(output_path, index=False, compression="zstd")
        qc["output_sha256"] = _sha256(output_path)
        qc["output_bytes"] = output_path.stat().st_size
    report_path.write_text(
        json.dumps(qc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return qc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, type=Path, help="Extracted gadm_410.gpkg"
    )
    parser.add_argument(
        "--country", required=True, help="Three-letter GADM GID_0, e.g. KEN"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="New .gpkg or .parquet"
    )
    parser.add_argument("--report", required=True, type=Path, help="New QC JSON")
    parser.add_argument("--layer", default="gadm_410")
    parser.add_argument(
        "--area-tolerance-km2", type=float, default=DEFAULT_AREA_TOLERANCE_KM2
    )
    args = parser.parse_args()
    qc = extract(
        args.input,
        args.output,
        args.report,
        args.country,
        layer=args.layer,
        area_tolerance_km2=args.area_tolerance_km2,
    )
    print(
        json.dumps(
            {
                "status": qc["status"],
                "country": qc["country"],
                "level": qc["admin_level"],
                "source_rows": qc["source_rows"],
                "target_unique": qc["target_unique_admin_gid"],
                "report": str(args.report),
            },
            sort_keys=True,
        )
    )
    return 0 if qc["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
