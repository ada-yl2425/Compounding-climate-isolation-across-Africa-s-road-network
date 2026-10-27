"""Facility-set and snap-threshold robustness audit for health accessibility.

The default health-access pipeline uses all health CSV rows, snaps facilities within
50 km to road nodes, and maps WorldPop pixels to nearest network nodes within
50 km. This script audits those construction choices before any full Dijkstra
rerun: facility exclusions, approximate population exclusion, and existing
headline health metrics.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from sensitivity.config import (
    COUNTRIES,
    HEALTH_SNAP_KM,
    WORLDPOP_PREFIX,
    add_common_path_args,
    resolve_paths,
)
from sensitivity.io_utils import ensure_dir, finite_numeric, weighted_mean, write_table

FACILITY_SETS = {
    "hospital_only": ["hospital"],
    "hospital_clinic_healthcentre": [
        "hospital",
        "clinic",
        "health centre",
        "health center",
        "health_centre",
        "healthcare",
    ],
    "plus_pharmacy": [
        "hospital",
        "clinic",
        "health centre",
        "health center",
        "health_centre",
        "healthcare",
        "pharmacy",
    ],
}


def load_health(path: Path, country: str) -> pd.DataFrame | None:
    csv_path = path / f"{country}_health.csv"
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path)
    if not {"lon", "lat"}.issubset(df.columns):
        return None
    df = df.dropna(subset=["lon", "lat"]).copy()
    df["lon"] = finite_numeric(df["lon"])
    df["lat"] = finite_numeric(df["lat"])
    df["_text"] = (
        df.get("amenity", "").astype(str).str.lower()
        + " "
        + df.get("name", "").astype(str).str.lower()
    )
    return df


def filter_facilities(df: pd.DataFrame, facility_set: str) -> pd.DataFrame:
    terms = FACILITY_SETS[facility_set]
    pattern = "|".join(terms)
    return df[df["_text"].str.contains(pattern, regex=True, na=False)].copy()


def road_nodes_from_shp(
    path: Path, country: str, unpaved_only: bool = True
) -> np.ndarray | None:
    shp = path / country / f"{country}.shp"
    if not shp.exists():
        return None
    import geopandas as gpd

    gdf = gpd.read_file(shp)
    if gdf.empty:
        return None
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    if unpaved_only:
        surf_col = next(
            (
                c
                for c in ["Surface", "surface", "fclass", "highway"]
                if c in gdf.columns
            ),
            None,
        )
        if surf_col:
            gdf = gdf[
                gdf[surf_col].astype(str).str.lower().str.contains("unpaved", na=False)
            ].copy()
    coords = []
    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            continue
        try:
            lines = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
            for line in lines:
                coords.append(line.coords[0])
                coords.append(line.coords[-1])
        except Exception:
            continue
    if not coords:
        return None
    arr = np.asarray(coords, dtype=float)
    return np.unique(np.round(arr, 6), axis=0)


def road_nodes_from_cached_accessibility(path: Path, country: str) -> np.ndarray | None:
    csv_path = path / f"node_accessibility_{country}.csv"
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path, usecols=["lon", "lat"])
    except Exception:
        return None
    df = df.dropna(subset=["lon", "lat"])
    if df.empty:
        return None
    return df[["lon", "lat"]].to_numpy(dtype=float)


def load_road_nodes(paths, country: str, source: str) -> np.ndarray | None:
    if source in {"cached", "auto"}:
        nodes = road_nodes_from_cached_accessibility(
            paths.health_accessibility, country
        )
        if nodes is not None:
            return nodes
    if source in {"shp", "auto"}:
        return road_nodes_from_shp(paths.road_data, country)
    raise ValueError(f"Unknown node source: {source}")


def facility_snap_audit(
    health_df: pd.DataFrame, nodes: np.ndarray, country: str
) -> list[dict]:
    tree = cKDTree(nodes)
    rows = []
    for set_name in FACILITY_SETS:
        sub = filter_facilities(health_df, set_name)
        if sub.empty:
            for threshold in HEALTH_SNAP_KM:
                rows.append(
                    {
                        "country": country,
                        "facility_set": set_name,
                        "threshold_km": threshold,
                        "n_facilities": 0,
                        "n_within_threshold": 0,
                        "excluded_facility_pct": np.nan,
                        "median_snap_distance_km": np.nan,
                    }
                )
            continue
        dists, _ = tree.query(sub[["lon", "lat"]].values)
        dist_km = dists * 111.0
        for threshold in HEALTH_SNAP_KM:
            within = dist_km <= threshold
            rows.append(
                {
                    "country": country,
                    "facility_set": set_name,
                    "threshold_km": threshold,
                    "n_facilities": int(len(sub)),
                    "n_within_threshold": int(within.sum()),
                    "excluded_facility_pct": round(
                        float((1.0 - within.mean()) * 100), 3
                    ),
                    "median_snap_distance_km": round(float(np.median(dist_km)), 3),
                }
            )
    return rows


def population_snap_audit(
    pop_path: Path,
    nodes: np.ndarray,
    country: str,
    max_pixels: int,
) -> list[dict]:
    try:
        import rasterio
    except Exception:
        return []
    if not pop_path.exists():
        return []

    with rasterio.open(pop_path) as src:
        data = src.read(1).astype(np.float32)
        nodata = src.nodata
        transform = src.transform
    if nodata is not None:
        data[data == nodata] = 0.0
    data[data < 0] = 0.0
    data = np.nan_to_num(data, nan=0.0)
    rows, cols = np.where(data > 0)
    if len(rows) == 0:
        return []
    pix_pop = data[rows, cols].astype(float)
    if len(rows) > max_pixels:
        rng = np.random.default_rng(42)
        probs = pix_pop / pix_pop.sum()
        idx = rng.choice(len(rows), size=max_pixels, replace=False, p=probs)
        rows, cols, pix_pop = rows[idx], cols[idx], pix_pop[idx]

    pix_lons = transform.c + (cols + 0.5) * transform.a
    pix_lats = transform.f + (rows + 0.5) * transform.e
    tree = cKDTree(nodes)
    dists, _ = tree.query(np.column_stack([pix_lons, pix_lats]))
    dist_km = dists * 111.0
    total_pop = float(pix_pop.sum())
    out = []
    for threshold in HEALTH_SNAP_KM:
        kept = pix_pop[dist_km <= threshold].sum()
        out.append(
            {
                "country": country,
                "population_mapping": "nearest_node",
                "threshold_km": threshold,
                "sampled_pixels": int(len(pix_pop)),
                "sampled_population": round(total_pop, 3),
                "population_within_threshold": round(float(kept), 3),
                "excluded_population_pct": (
                    round(float((1.0 - kept / total_pop) * 100), 3)
                    if total_pop > 0
                    else np.nan
                ),
            }
        )
    return out


def summarize_existing_health(summary_path: Path, out_dir: Path) -> pd.DataFrame | None:
    if not summary_path.exists():
        return None
    df = pd.read_csv(summary_path)
    required = {
        "country",
        "total_population",
        "isochrone_shrinkage_T60min",
        "tail_gap_ratio",
    }
    if not required.issubset(df.columns):
        return None
    df = df.copy()
    df["total_population"] = finite_numeric(df["total_population"])
    df["isochrone_shrinkage_T60min"] = finite_numeric(df["isochrone_shrinkage_T60min"])
    df["tail_gap_ratio"] = pd.to_numeric(df["tail_gap_ratio"], errors="coerce")
    out = pd.DataFrame(
        [
            {
                "variant": "default_cached_web2",
                "n_countries": int(df["country"].nunique()),
                "one_hour_coverage_loss_pop_weighted_pct": round(
                    weighted_mean(
                        df["isochrone_shrinkage_T60min"] * 100,
                        df["total_population"],
                    ),
                    3,
                ),
                "mean_tail_gap_ratio": round(float(df["tail_gap_ratio"].mean()), 3),
                "countries_with_TGR_gt_1": int((df["tail_gap_ratio"] > 1).sum()),
                "median_spearman_rho": (
                    round(
                        float(
                            pd.to_numeric(
                                df.get("spearman_rho"), errors="coerce"
                            ).median()
                        ),
                        4,
                    )
                    if "spearman_rho" in df.columns
                    else np.nan
                ),
            }
        ]
    )
    write_table(out, out_dir / "existing_health_headline_metrics.csv")
    return out


def build_interpretation_summary(
    facility_df: pd.DataFrame,
    population_df: pd.DataFrame | None,
    existing: pd.DataFrame | None,
    out_dir: Path,
) -> pd.DataFrame:
    rows = []
    focus = facility_df[
        (facility_df["threshold_km"] == 50.0)
        & (facility_df["facility_set"] == "hospital_clinic_healthcentre")
    ]
    if not focus.empty:
        rows.append(
            {
                "robustness_question": "Facility exclusion under 50 km rule",
                "evidence": (
                    f"Across {focus['country'].nunique()} countries, excluded facility "
                    f"share ranges from {focus['excluded_facility_pct'].min():.1f}% "
                    f"to {focus['excluded_facility_pct'].max():.1f}%, median "
                    f"{focus['excluded_facility_pct'].median():.1f}%."
                ),
                "interpretation": "construction-sensitive; report country distribution",
            }
        )
    if population_df is not None and not population_df.empty:
        pop50 = population_df[population_df["threshold_km"] == 50.0]
        rows.append(
            {
                "robustness_question": "Population exclusion under 50 km rule",
                "evidence": (
                    f"In this run, excluded sampled population ranges from "
                    f"{pop50['excluded_population_pct'].min():.1f}% to "
                    f"{pop50['excluded_population_pct'].max():.1f}%, median "
                    f"{pop50['excluded_population_pct'].median():.1f}%."
                ),
                "interpretation": "potential remote-population undercount; needs explicit limitation/sensitivity table",
            }
        )
    if existing is not None and not existing.empty:
        row = existing.iloc[0]
        rows.append(
            {
                "robustness_question": "Cached health-access headline",
                "evidence": (
                    f"Default cached output gives 1h coverage loss "
                    f"{row['one_hour_coverage_loss_pop_weighted_pct']:.2f}%, "
                    f"mean TGR {row['mean_tail_gap_ratio']:.2f}, "
                    f"{int(row['countries_with_TGR_gt_1'])} countries with TGR>1."
                ),
                "interpretation": "headline exists, but facility/population construction must be stress-tested before final claim",
            }
        )
    out = pd.DataFrame(rows)
    write_table(out, out_dir / "interpretation_summary.csv")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_path_args(parser)
    parser.add_argument("--countries", nargs="*", default=None)
    parser.add_argument(
        "--skip-population",
        action="store_true",
        help="Skip WorldPop pixel audit; facility audit still runs.",
    )
    parser.add_argument(
        "--node-source",
        choices=["auto", "cached", "shp"],
        default="auto",
        help="Use cached health-accessibility nodes when available; fallback to shapefile.",
    )
    parser.add_argument(
        "--max-pop-pixels",
        type=int,
        default=250_000,
        help="Population-weighted pixel sample cap per country for the audit.",
    )
    parser.add_argument(
        "--run-tag",
        default=None,
        help="Optional subdirectory name under 03_health_access for subset runs.",
    )
    args = parser.parse_args()

    paths = resolve_paths(args.base_dir, args.output_dir)
    out_dir = paths.output_root / "03_health_access"
    if args.run_tag:
        out_dir = out_dir / args.run_tag
    out_dir = ensure_dir(out_dir)
    countries = args.countries or COUNTRIES

    facility_rows = []
    population_rows = []
    missing = defaultdict(list)
    for country in countries:
        print(f"  {country} ...", flush=True)
        health_df = load_health(paths.health_data, country)
        nodes = load_road_nodes(paths, country, args.node_source)
        if health_df is None:
            missing["health_csv"].append(country)
            continue
        if nodes is None:
            missing["road_nodes"].append(country)
            continue
        facility_rows.extend(facility_snap_audit(health_df, nodes, country))
        if not args.skip_population:
            prefix = WORLDPOP_PREFIX.get(country, "")
            if prefix:
                pop_path = paths.pop_data / f"{prefix}_ppp_2020_UNadj_constrained.tif"
                population_rows.extend(
                    population_snap_audit(pop_path, nodes, country, args.max_pop_pixels)
                )

    facility_df = pd.DataFrame(facility_rows)
    write_table(facility_df, out_dir / "facility_snap_threshold_audit.csv")
    population_df = pd.DataFrame(population_rows) if population_rows else None
    if population_rows:
        write_table(
            population_df,
            out_dir / "population_snap_threshold_audit.csv",
        )

    existing = summarize_existing_health(
        paths.health_accessibility / "country_accessibility_summary.csv", out_dir
    )

    if missing:
        missing_df = pd.DataFrame(
            [{"kind": k, "country": c} for k, vals in missing.items() for c in vals]
        )
        write_table(missing_df, out_dir / "missing_health_audit_inputs.csv")
    interp = build_interpretation_summary(facility_df, population_df, existing, out_dir)

    print("Health robustness audit written to:", out_dir)
    if existing is not None:
        print(existing.to_string(index=False))
    print("\nInterpretation:")
    print(interp.to_string(index=False))
    if not facility_df.empty:
        focus = facility_df[
            (facility_df["threshold_km"] == 50.0)
            & (facility_df["facility_set"] == "hospital_clinic_healthcentre")
        ]
        print("\n50 km facility exclusion, hospital+clinic+health centre:")
        print(
            focus[["country", "n_facilities", "excluded_facility_pct"]]
            .head(12)
            .to_string(index=False)
        )


if __name__ == "__main__":
    main()
