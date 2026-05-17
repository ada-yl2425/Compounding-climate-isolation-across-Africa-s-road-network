"""Health-access variant grid for robustness test.

This script avoids a full multi-source Dijkstra rerun for every facility
definition. It uses cached node-level health accessibility, rebuilds facility
anchors for a 3 x 3 x 2 variant grid, and applies a local access-distance
adjustment to the cached travel-time surface.

Outputs are intended as a sensitivity layer, not as a replacement for the
original health-access pipeline.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial import cKDTree

from sensitivity.config import (
    COUNTRIES,
    HEALTH_SNAP_KM,
    WORLDPOP_PREFIX,
    add_common_path_args,
    resolve_paths,
)
from sensitivity.health_access_sensitivity import (
    FACILITY_SETS,
    filter_facilities,
    load_health,
)
from sensitivity.io_utils import ensure_dir, finite_numeric, weighted_mean, write_table


POPULATION_MAPPINGS = ["nearest_node", "nearest_segment_proxy"]
DEFAULT_FACILITY_SET = "plus_pharmacy"
DEFAULT_THRESHOLD_KM = 50.0
ACCESS_SPEED_NORMAL_KMH = 40.0
ACCESS_SPEED_EXTREME_KMH = 30.0
DEG_TO_KM = 111.0


@dataclass
class PopulationSample:
    lon: np.ndarray
    lat: np.ndarray
    weight: np.ndarray
    total_population: float
    sampled_pixels: int


@dataclass
class CountryContext:
    country: str
    nodes: pd.DataFrame
    node_xy: np.ndarray
    node_tree: cKDTree
    segment_xy: np.ndarray
    segment_tree: cKDTree
    segment_to_node_idx: np.ndarray
    health: pd.DataFrame
    population: PopulationSample | None
    total_population: float
    segment_source: str


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not mask.any():
        return float("nan")
    v = values[mask]
    w = weights[mask]
    order = np.argsort(v)
    v = v[order]
    w = w[order]
    cutoff = q * w.sum()
    return float(v[np.searchsorted(np.cumsum(w), cutoff, side="left")])


def grid_center(values: pd.Series) -> pd.Series:
    return np.floor(values.astype(float) * 2.0) / 2.0 + 0.25


def load_node_accessibility(path: Path, country: str) -> pd.DataFrame | None:
    csv_path = path / f"node_accessibility_{country}.csv"
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path)
    required = {"lon", "lat", "t_normal", "t_extreme", "population"}
    if not required.issubset(df.columns):
        return None
    df = df.dropna(subset=["lon", "lat"]).copy()
    df["lon"] = finite_numeric(df["lon"])
    df["lat"] = finite_numeric(df["lat"])
    df["t_normal"] = finite_numeric(df["t_normal"])
    df["t_extreme"] = finite_numeric(df["t_extreme"])
    df["population"] = finite_numeric(df["population"])
    return df.reset_index(drop=True)


def cached_midpoint_segment_points(
    node_xy: np.ndarray, max_points: int
) -> tuple[np.ndarray, str]:
    if len(node_xy) == 0:
        return np.empty((0, 2), dtype=float), "empty_cached_nodes"
    k = min(4, len(node_xy))
    _, idx = cKDTree(node_xy).query(node_xy, k=k)
    if idx.ndim == 1:
        return node_xy.copy(), "cached_nodes_only"
    pts = [node_xy]
    for j in range(1, idx.shape[1]):
        pts.append((node_xy + node_xy[idx[:, j]]) / 2.0)
    arr = np.unique(np.round(np.vstack(pts), 5), axis=0)
    if len(arr) > max_points:
        rng = np.random.default_rng(42)
        arr = arr[rng.choice(len(arr), size=max_points, replace=False)]
        return arr, "cached_node_neighbor_midpoint_sample"
    return arr, "cached_node_neighbor_midpoint"


def road_segment_proxy_points(
    paths, country: str, max_points: int
) -> tuple[np.ndarray, str]:
    shp = paths.road_data / country / f"{country}.shp"
    if not shp.exists():
        return np.empty((0, 2), dtype=float), "missing_shp"
    try:
        import geopandas as gpd
    except Exception:
        return np.empty((0, 2), dtype=float), "geopandas_unavailable"

    try:
        gdf = gpd.read_file(shp)
        if gdf.empty:
            return np.empty((0, 2), dtype=float), "empty_shp"
        if gdf.crs is None or gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs("EPSG:4326")
    except Exception:
        return np.empty((0, 2), dtype=float), "read_failed"

    pts: list[tuple[float, float]] = []
    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            continue
        lines = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
        for line in lines:
            if line.is_empty:
                continue
            coords = list(line.coords)
            if not coords:
                continue
            pts.append(coords[0])
            pts.append(coords[-1])
            try:
                mid = line.interpolate(0.5, normalized=True)
                pts.append((mid.x, mid.y))
            except Exception:
                pass

    if not pts:
        return np.empty((0, 2), dtype=float), "no_line_points"
    arr = np.unique(np.round(np.asarray(pts, dtype=float), 5), axis=0)
    if len(arr) > max_points:
        rng = np.random.default_rng(42)
        arr = arr[rng.choice(len(arr), size=max_points, replace=False)]
        return arr, "segment_endpoint_midpoint_sample"
    return arr, "segment_endpoint_midpoint"


def load_population_sample(
    paths,
    country: str,
    max_pixels: int,
) -> PopulationSample | None:
    prefix = WORLDPOP_PREFIX.get(country, "")
    if not prefix:
        return None
    pop_path = paths.pop_data / f"{prefix}_ppp_2020_UNadj_constrained.tif"
    if not pop_path.exists():
        return None
    try:
        import rasterio
    except Exception:
        return None

    with rasterio.open(pop_path) as src:
        data = src.read(1).astype(np.float64)
        nodata = src.nodata
        transform = src.transform
    if nodata is not None:
        data[data == nodata] = 0.0
    data = np.nan_to_num(data, nan=0.0)
    data[data < 0] = 0.0
    rows, cols = np.where(data > 0)
    if len(rows) == 0:
        return None
    pix_pop = data[rows, cols]
    total_pop = float(pix_pop.sum())
    if total_pop <= 0:
        return None

    sampled = False
    if len(rows) > max_pixels:
        rng = np.random.default_rng(42)
        idx = rng.choice(
            len(rows),
            size=max_pixels,
            replace=False,
            p=pix_pop / total_pop,
        )
        rows, cols, pix_pop = rows[idx], cols[idx], pix_pop[idx]
        sampled = True

    lon = transform.c + (cols + 0.5) * transform.a
    lat = transform.f + (rows + 0.5) * transform.e
    weight = np.ones(len(rows), dtype=float) if sampled else pix_pop.astype(float)
    return PopulationSample(
        lon=lon.astype(float),
        lat=lat.astype(float),
        weight=weight,
        total_population=total_pop,
        sampled_pixels=int(len(rows)),
    )


def build_country_context(
    paths,
    country: str,
    max_pop_pixels: int,
    max_segment_points: int,
    segment_source: str,
) -> CountryContext | None:
    nodes = load_node_accessibility(paths.health_accessibility, country)
    health = load_health(paths.health_data, country)
    if nodes is None or health is None or nodes.empty:
        return None

    node_xy = nodes[["lon", "lat"]].to_numpy(dtype=float)
    node_tree = cKDTree(node_xy)
    if segment_source == "cached_midpoint":
        segment_xy, source = cached_midpoint_segment_points(node_xy, max_segment_points)
    elif segment_source == "shp_endpoint_midpoint":
        segment_xy, source = road_segment_proxy_points(
            paths, country, max_segment_points
        )
    else:
        raise ValueError(segment_source)
    if segment_xy.size == 0:
        segment_xy = node_xy
        source = f"{source}_fallback_cached_nodes"
    segment_tree = cKDTree(segment_xy)
    _, segment_to_node_idx = node_tree.query(segment_xy)
    pop = load_population_sample(paths, country, max_pop_pixels)
    total_population = (
        float(nodes["population"].sum()) if pop is None else pop.total_population
    )

    return CountryContext(
        country=country,
        nodes=nodes,
        node_xy=node_xy,
        node_tree=node_tree,
        segment_xy=segment_xy,
        segment_tree=segment_tree,
        segment_to_node_idx=np.asarray(segment_to_node_idx, dtype=int),
        health=health,
        population=pop,
        total_population=total_population,
        segment_source=source,
    )


def network_tree(
    ctx: CountryContext, mapping: str
) -> tuple[cKDTree, np.ndarray, np.ndarray]:
    if mapping == "nearest_node":
        return ctx.node_tree, ctx.node_xy, np.arange(len(ctx.node_xy), dtype=int)
    if mapping == "nearest_segment_proxy":
        return ctx.segment_tree, ctx.segment_xy, ctx.segment_to_node_idx
    raise ValueError(mapping)


def facility_selection(
    ctx: CountryContext,
    facility_set: str,
    threshold_km: float,
    mapping: str,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    facilities = filter_facilities(ctx.health, facility_set)
    if facilities.empty:
        return facilities, np.empty((0, 2), dtype=float), np.array([], dtype=bool)

    tree, xy, point_to_node = network_tree(ctx, mapping)
    d_deg, idx = tree.query(facilities[["lon", "lat"]].to_numpy(dtype=float))
    dist_km = d_deg * DEG_TO_KM
    keep = dist_km <= threshold_km
    if not keep.any():
        return facilities, np.empty((0, 2), dtype=float), keep

    snapped_xy = xy[idx[keep]]
    if mapping == "nearest_node":
        anchor_nodes = idx[keep]
    else:
        anchor_nodes = point_to_node[idx[keep]]
    node_anchor_xy = ctx.node_xy[np.unique(anchor_nodes)]
    return facilities, np.unique(np.vstack([snapped_xy, node_anchor_xy]), axis=0), keep


def nearest_anchor_distance(ctx: CountryContext, anchors_xy: np.ndarray) -> np.ndarray:
    if anchors_xy.size == 0:
        return np.full(len(ctx.node_xy), np.inf, dtype=float)
    d_deg, _ = cKDTree(anchors_xy).query(ctx.node_xy)
    return d_deg * DEG_TO_KM


def population_mapping(
    ctx: CountryContext, mapping: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    if ctx.population is None:
        return (
            np.arange(len(ctx.nodes), dtype=int),
            np.zeros(len(ctx.nodes), dtype=float),
            ctx.nodes["population"].to_numpy(dtype=float),
            0,
        )
    sample_xy = np.column_stack([ctx.population.lon, ctx.population.lat])
    if mapping == "nearest_node":
        d_deg, idx = ctx.node_tree.query(sample_xy)
        return (
            idx.astype(int),
            d_deg * DEG_TO_KM,
            ctx.population.weight,
            ctx.population.sampled_pixels,
        )
    if mapping == "nearest_segment_proxy":
        d_deg, seg_idx = ctx.segment_tree.query(sample_xy)
        idx = ctx.segment_to_node_idx[seg_idx]
        return (
            idx.astype(int),
            d_deg * DEG_TO_KM,
            ctx.population.weight,
            ctx.population.sampled_pixels,
        )
    raise ValueError(mapping)


def country_variant_metrics(
    ctx: CountryContext,
    facility_set: str,
    threshold_km: float,
    mapping: str,
    default_anchor_cache: dict[str, np.ndarray],
) -> tuple[dict, dict, pd.DataFrame]:
    facilities, anchors, keep = facility_selection(
        ctx, facility_set, threshold_km, mapping
    )
    default_key = mapping
    if default_key not in default_anchor_cache:
        _, default_anchors, _ = facility_selection(
            ctx, DEFAULT_FACILITY_SET, DEFAULT_THRESHOLD_KM, mapping
        )
        default_anchor_cache[default_key] = nearest_anchor_distance(
            ctx, default_anchors
        )
    default_dist = default_anchor_cache[default_key]
    variant_dist = nearest_anchor_distance(ctx, anchors)

    n_total = int(len(facilities))
    n_within = int(keep.sum()) if len(keep) else 0
    pop_node_idx, pop_dist_km, pop_weight, sampled_pixels = population_mapping(
        ctx, mapping
    )
    included_pop_mask = pop_dist_km <= threshold_km

    exclusion = {
        "country": ctx.country,
        "facility_set": facility_set,
        "population_mapping": mapping,
        "threshold_km": threshold_km,
        "facilities_total": n_total,
        "facilities_excluded_at_threshold": n_total - n_within,
        "excluded_facility_pct": (
            round(float((1.0 - n_within / n_total) * 100), 3) if n_total > 0 else np.nan
        ),
        "sampled_pixels": sampled_pixels,
        "population_total_est": round(ctx.total_population, 3),
        "population_excluded_at_threshold": np.nan,
        "excluded_population_pct": np.nan,
        "segment_source": (
            ctx.segment_source if mapping == "nearest_segment_proxy" else "cached_nodes"
        ),
    }

    if pop_weight.sum() > 0:
        excluded_share = 1.0 - float(np.average(included_pop_mask, weights=pop_weight))
        exclusion["excluded_population_pct"] = round(excluded_share * 100, 3)
        exclusion["population_excluded_at_threshold"] = round(
            ctx.total_population * excluded_share, 3
        )

    if (
        n_within == 0
        or not np.isfinite(variant_dist).any()
        or not included_pop_mask.any()
    ):
        metrics = {
            "country": ctx.country,
            "facility_set": facility_set,
            "threshold_km": threshold_km,
            "population_mapping": mapping,
            "n_facilities": n_total,
            "n_facility_anchors": n_within,
            "included_population_est": np.nan,
            "one_hour_coverage_loss": np.nan,
            "mean_tail_gap_ratio": np.nan,
            "tail_gap_ratio": np.nan,
            "pwmtt_delta": np.nan,
            "normal_covered_pop_1h": np.nan,
            "extreme_covered_pop_1h": np.nan,
            "status": "no_anchors_or_population",
        }
        return (
            metrics,
            exclusion,
            selected_facilities_for_regression(
                facilities, keep, facility_set, threshold_km, mapping, ctx.country
            ),
        )

    node_delta_dist = np.nan_to_num(
        variant_dist - default_dist, nan=0.0, posinf=0.0, neginf=0.0
    )
    t_normal_nodes = np.maximum(
        0.0,
        ctx.nodes["t_normal"].to_numpy(dtype=float)
        + node_delta_dist / ACCESS_SPEED_NORMAL_KMH,
    )
    t_extreme_nodes = np.maximum(
        0.0,
        ctx.nodes["t_extreme"].to_numpy(dtype=float)
        + node_delta_dist / ACCESS_SPEED_EXTREME_KMH,
    )

    idx = pop_node_idx[included_pop_mask]
    weights = pop_weight[included_pop_mask]
    sample_total_w = float(pop_weight.sum())
    total_w = float(weights.sum())
    included_share = total_w / sample_total_w if sample_total_w > 0 else np.nan
    included_population_est = (
        ctx.total_population * included_share if np.isfinite(included_share) else np.nan
    )
    t_normal = t_normal_nodes[idx]
    t_extreme = t_extreme_nodes[idx]
    delta_t = t_extreme - t_normal

    normal_cov_w = float(weights[t_normal <= 1.0].sum())
    extreme_cov_w = float(weights[t_extreme <= 1.0].sum())
    normal_cov = (
        ctx.total_population * normal_cov_w / sample_total_w
        if sample_total_w > 0
        else np.nan
    )
    extreme_cov = (
        ctx.total_population * extreme_cov_w / sample_total_w
        if sample_total_w > 0
        else np.nan
    )
    shrink = (normal_cov - extreme_cov) / normal_cov if normal_cov > 0 else np.nan
    p50_delta = weighted_quantile(delta_t, weights, 0.50)
    p90_delta = weighted_quantile(delta_t, weights, 0.90)
    tgr = p90_delta / p50_delta if np.isfinite(p50_delta) and p50_delta > 0 else np.nan

    metrics = {
        "country": ctx.country,
        "facility_set": facility_set,
        "threshold_km": threshold_km,
        "population_mapping": mapping,
        "n_facilities": n_total,
        "n_facility_anchors": n_within,
        "included_population_est": round(float(included_population_est), 3),
        "one_hour_coverage_loss": (
            round(float(shrink), 6) if np.isfinite(shrink) else np.nan
        ),
        "mean_tail_gap_ratio": round(float(tgr), 6) if np.isfinite(tgr) else np.nan,
        "tail_gap_ratio": round(float(tgr), 6) if np.isfinite(tgr) else np.nan,
        "pwmtt_delta": round(float(np.average(delta_t, weights=weights)), 6),
        "normal_covered_pop_1h": round(float(normal_cov), 3),
        "extreme_covered_pop_1h": round(float(extreme_cov), 3),
        "status": "ok",
    }
    return (
        metrics,
        exclusion,
        selected_facilities_for_regression(
            facilities, keep, facility_set, threshold_km, mapping, ctx.country
        ),
    )


def selected_facilities_for_regression(
    facilities: pd.DataFrame,
    keep: np.ndarray,
    facility_set: str,
    threshold_km: float,
    mapping: str,
    country: str,
) -> pd.DataFrame:
    if facilities.empty or len(keep) == 0 or not keep.any():
        return pd.DataFrame(
            columns=[
                "country",
                "lon",
                "lat",
                "facility_set",
                "threshold_km",
                "population_mapping",
            ]
        )
    out = facilities.loc[keep, ["lon", "lat"]].copy()
    out["country"] = country
    out["facility_set"] = facility_set
    out["threshold_km"] = threshold_km
    out["population_mapping"] = mapping
    return out


def aggregate_variant_summary(
    country_df: pd.DataFrame, default_country: pd.DataFrame
) -> pd.DataFrame:
    default = default_country[
        ["country", "isochrone_shrinkage_T60min", "tail_gap_ratio"]
    ].copy()
    rows = []
    for keys, sub in country_df.groupby(
        ["facility_set", "threshold_km", "population_mapping"]
    ):
        ok = sub[sub["status"] == "ok"].copy()
        if ok.empty:
            continue
        weights = finite_numeric(ok["included_population_est"])
        one_hour = finite_numeric(ok["one_hour_coverage_loss"])
        tgr = pd.to_numeric(ok["tail_gap_ratio"], errors="coerce")
        merged = ok.merge(default, on="country", how="left")
        cov_rho = (
            merged[["one_hour_coverage_loss", "isochrone_shrinkage_T60min"]]
            .corr(method="spearman")
            .iloc[0, 1]
        )
        if (
            "tail_gap_ratio_x" in merged.columns
            and "tail_gap_ratio_y" in merged.columns
        ):
            tgr_rho = (
                merged[["tail_gap_ratio_x", "tail_gap_ratio_y"]]
                .corr(method="spearman")
                .iloc[0, 1]
            )
        else:
            tgr_rho = np.nan
        rows.append(
            {
                "facility_set": keys[0],
                "threshold_km": keys[1],
                "population_mapping": keys[2],
                "n_countries_ok": int(ok["country"].nunique()),
                "one_hour_coverage_loss_pct": round(
                    weighted_mean(one_hour * 100.0, weights), 3
                ),
                "mean_tail_gap_ratio": round(float(tgr.mean(skipna=True)), 3),
                "countries_with_TGR_gt_1": int((tgr > 1.0).sum()),
                "country_rank_spearman_vs_default_coverage": (
                    round(float(cov_rho), 4) if np.isfinite(cov_rho) else np.nan
                ),
                "country_rank_spearman_vs_default_TGR": (
                    round(float(tgr_rho), 4) if np.isfinite(tgr_rho) else np.nan
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["facility_set", "threshold_km", "population_mapping"]
    )


def ols_coefficients(
    y: np.ndarray, x: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    mask = np.isfinite(y) & np.all(np.isfinite(x), axis=1)
    y = y[mask]
    x = x[mask]
    n, k = x.shape
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    resid = y - x @ beta
    dof = max(n - k, 1)
    sigma2 = float((resid @ resid) / dof)
    xtx_inv = np.linalg.pinv(x.T @ x)
    se = np.sqrt(np.diag(xtx_inv) * sigma2)
    t_stat = beta / np.maximum(se, 1e-12)
    p = 2.0 * (1.0 - stats.t.cdf(np.abs(t_stat), df=dof))
    ss_tot = float(((y - y.mean()) @ (y - y.mean())))
    r2 = 1.0 - float(resid @ resid) / ss_tot if ss_tot > 0 else np.nan
    return beta, se, p, r2


def regression_table(
    grid_path: Path, selected_facilities: pd.DataFrame
) -> pd.DataFrame | None:
    if not grid_path.exists() or selected_facilities.empty:
        return None
    grid = pd.read_csv(grid_path)
    required = {"cell_lon", "cell_lat", "pw_delta_t", "total_pop"}
    if not required.issubset(grid.columns):
        return None
    grid = grid.copy()
    grid["cell_lon"] = finite_numeric(grid["cell_lon"])
    grid["cell_lat"] = finite_numeric(grid["cell_lat"])
    grid["total_pop"] = finite_numeric(grid["total_pop"])
    grid["pw_delta_t"] = finite_numeric(grid["pw_delta_t"])

    fac = selected_facilities.copy()
    fac["cell_lon"] = grid_center(fac["lon"])
    fac["cell_lat"] = grid_center(fac["lat"])
    count = (
        fac.groupby(
            [
                "facility_set",
                "threshold_km",
                "population_mapping",
                "cell_lon",
                "cell_lat",
            ]
        )
        .size()
        .rename("n_facilities_variant")
        .reset_index()
    )

    rows = []
    for keys, sub_count in count.groupby(
        ["facility_set", "threshold_km", "population_mapping"]
    ):
        df = grid.merge(sub_count, on=["cell_lon", "cell_lat"], how="left")
        df["n_facilities_variant"] = df["n_facilities_variant"].fillna(0.0)
        df["facility_per_million_variant"] = np.where(
            df["total_pop"] > 0,
            df["n_facilities_variant"] / df["total_pop"] * 1_000_000.0,
            0.0,
        )
        y = df["pw_delta_t"].to_numpy(dtype=float)
        x = np.column_stack(
            [
                np.ones(len(df)),
                np.log1p(df["facility_per_million_variant"].to_numpy(dtype=float)),
                np.log1p(df["total_pop"].to_numpy(dtype=float)),
            ]
        )
        beta, se, p, r2 = ols_coefficients(y, x)
        for term, idx in [
            ("const", 0),
            ("log_facility_per_million", 1),
            ("log_population", 2),
        ]:
            rows.append(
                {
                    "facility_set": keys[0],
                    "threshold_km": keys[1],
                    "population_mapping": keys[2],
                    "term": term,
                    "coefficient": round(float(beta[idx]), 6),
                    "SE": round(float(se[idx]), 6),
                    "p_value": round(float(p[idx]), 6),
                    "R2": round(float(r2), 6),
                    "sign_stable_vs_default": np.nan,
                    "n_grid_cells": int(len(df)),
                }
            )
    out = pd.DataFrame(rows)
    baseline = out[
        (out["facility_set"] == DEFAULT_FACILITY_SET)
        & (out["threshold_km"] == DEFAULT_THRESHOLD_KM)
        & (out["population_mapping"] == "nearest_node")
        & (out["term"] == "log_facility_per_million")
    ]
    if not baseline.empty:
        baseline_sign = np.sign(float(baseline["coefficient"].iloc[0]))
        mask = out["term"] == "log_facility_per_million"
        out.loc[mask, "sign_stable_vs_default"] = (
            np.sign(out.loc[mask, "coefficient"].astype(float)) == baseline_sign
        )
    return out


def build_interpretation(
    summary: pd.DataFrame, exclusion50: pd.DataFrame, reg: pd.DataFrame | None
) -> pd.DataFrame:
    rows = []
    rows.append(
        {
            "check": "18 health-facility variant grid",
            "evidence": (
                f"1h coverage-loss proxy ranges from {summary['one_hour_coverage_loss_pct'].min():.2f}% "
                f"to {summary['one_hour_coverage_loss_pct'].max():.2f}%; mean TGR ranges from "
                f"{summary['mean_tail_gap_ratio'].min():.2f} to {summary['mean_tail_gap_ratio'].max():.2f}."
            ),
            "interpretation": "proxy check; confirms whether headline direction survives facility/threshold/mapping changes",
        }
    )
    fac50 = exclusion50[
        (exclusion50["threshold_km"] == 50.0)
        & (exclusion50["facility_set"] == "hospital_clinic_healthcentre")
        & (exclusion50["population_mapping"] == "nearest_node")
    ]
    if not fac50.empty:
        rows.append(
            {
                "check": "50 km exclusion by country",
                "evidence": (
                    f"Facility exclusion median {fac50['excluded_facility_pct'].median():.1f}% "
                    f"(range {fac50['excluded_facility_pct'].min():.1f}-{fac50['excluded_facility_pct'].max():.1f}%). "
                    f"Population exclusion median {fac50['excluded_population_pct'].median():.1f}%."
                ),
                "interpretation": "must be reported; 50 km rule is spatially uneven",
            }
        )
    if reg is not None and not reg.empty:
        fac_terms = reg[reg["term"] == "log_facility_per_million"]
        stable = fac_terms["sign_stable_vs_default"].map(
            lambda value: True if pd.isna(value) else bool(value)
        )
        rows.append(
            {
                "check": "Fig. 3c regression proxy",
                "evidence": (
                    f"{stable.sum()}/{len(stable)} variants keep the same facility-density coefficient sign; "
                    f"coefficient range {fac_terms['coefficient'].min():.4f} to {fac_terms['coefficient'].max():.4f}."
                ),
                "interpretation": "same proxy specification across variants",
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_path_args(parser)
    parser.add_argument("--countries", nargs="*", default=None)
    parser.add_argument("--max-pop-pixels", type=int, default=100_000)
    parser.add_argument("--max-segment-points", type=int, default=120_000)
    parser.add_argument(
        "--segment-proxy-source",
        choices=["cached_midpoint", "shp_endpoint_midpoint"],
        default="cached_midpoint",
        help="Default uses cached road-node neighbour midpoints; shp mode is slower.",
    )
    args = parser.parse_args()

    paths = resolve_paths(args.base_dir, args.output_dir)
    out_dir = ensure_dir(paths.output_root / "08_health_variant_grid")
    countries = args.countries or COUNTRIES
    default_country = pd.read_csv(
        paths.health_accessibility / "country_accessibility_summary.csv"
    )

    country_rows = []
    exclusion_rows = []
    selected_facility_frames = []
    context_rows = []
    missing_rows = []

    for country in countries:
        print(f"  {country} ...", flush=True)
        ctx = build_country_context(
            paths,
            country,
            args.max_pop_pixels,
            args.max_segment_points,
            args.segment_proxy_source,
        )
        if ctx is None:
            missing_rows.append(
                {
                    "country": country,
                    "reason": "missing node accessibility or health CSV",
                }
            )
            continue
        context_rows.append(
            {
                "country": country,
                "n_nodes": len(ctx.nodes),
                "n_health_rows": len(ctx.health),
                "segment_points": len(ctx.segment_xy),
                "segment_source": ctx.segment_source,
                "population_sampled_pixels": (
                    ctx.population.sampled_pixels if ctx.population else 0
                ),
                "population_total_est": ctx.total_population,
            }
        )
        default_anchor_cache: dict[str, np.ndarray] = {}
        for facility_set in FACILITY_SETS:
            for threshold in HEALTH_SNAP_KM:
                for mapping in POPULATION_MAPPINGS:
                    metrics, exclusion, selected = country_variant_metrics(
                        ctx, facility_set, threshold, mapping, default_anchor_cache
                    )
                    country_rows.append(metrics)
                    exclusion_rows.append(exclusion)
                    if not selected.empty:
                        selected_facility_frames.append(selected)

    country_df = pd.DataFrame(country_rows)
    exclusion_df = pd.DataFrame(exclusion_rows)
    context_df = pd.DataFrame(context_rows)
    summary_df = aggregate_variant_summary(country_df, default_country)

    selected_facilities = (
        pd.concat(selected_facility_frames, ignore_index=True)
        if selected_facility_frames
        else pd.DataFrame()
    )
    grid_path = (
        paths.data_base
        / "result"
        / "result2"
        / "finding4_OLS_regression_facility_popdensity_vs_climate_impact"
        / "grid_cells_pw_delta_t_facility_popdensity.csv"
    )
    reg_df = regression_table(grid_path, selected_facilities)

    exclusion50 = exclusion_df[exclusion_df["threshold_km"] == 50.0].copy()
    interp = build_interpretation(summary_df, exclusion50, reg_df)

    write_table(country_df, out_dir / "health_variant_grid_country_metrics.csv")
    write_table(summary_df, out_dir / "health_variant_grid_summary.csv")
    write_table(
        exclusion_df, out_dir / "health_variant_exclusion_by_country_all_thresholds.csv"
    )
    write_table(exclusion50, out_dir / "health_50km_exclusion_by_country.csv")
    write_table(context_df, out_dir / "health_variant_input_context.csv")
    write_table(interp, out_dir / "interpretation_summary.csv")
    if reg_df is not None:
        write_table(reg_df, out_dir / "fig3c_regression_coefficients.csv")
    if missing_rows:
        write_table(pd.DataFrame(missing_rows), out_dir / "missing_inputs.csv")

    print("Health variant grid written to:", out_dir)
    print("\nVariant summary:")
    print(summary_df.to_string(index=False))
    print("\nInterpretation:")
    print(interp.to_string(index=False))


if __name__ == "__main__":
    main()
