"""
paving_isolation_analysis.py — Result 3 De-isolation Supplement

Computes climate isolation quantity and spatial recovery from targeted paving
at f=5%, loading existing pkl files (no network rebuild required).

Inputs (under BASE/web/network_results/bottleneck_paving/):
    experiment_state.pkl    — graphs, city indices, bottleneck/unpaved arrays
    01_graph_checkpoint.pkl — node coordinates (all_nc)

Outputs (under .../bottleneck_paving/deisolation/):
    R3_isolation_quantity.csv — Result 1: pair / population counts before & after
    R3_od_deisolation.csv     — Result 2: per-OD spatial data for mapping
    R3_country_summary.csv    — Result 2: country-level aggregation
    R3_region_summary.csv     — Result 2: hotspot-belt aggregation
    R3_deisolation_map.png    — Result 2: spatial figure

Isolation thresholds (OD-pair level, same CV definition as edge level):
    Severe  : CV_OD > 0.5  (extreme travel time ≥ 1.5× normal)
    Extreme : CV_OD > 1.0  (extreme travel time ≥ 2.0× normal)

Near-neighbor reachability:
    1-hour travel-time circle — counts how many other city nodes each node can
    reach in ≤ 1 h; populations losing ≥ 1 neighbour under extreme weather are
    "isolated", those that regain ≥ 1 neighbour after paving are "de-isolated".

Usage:
    python ABtest/paving_isolation_analysis.py --base /path/to/africa_pavement
"""

import argparse
import pickle
import warnings
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Parameters ────────────────────────────────────────────────────────────────
PAVING_FRACTION = 0.05
UNREACHABLE = 1e8

SEVERE_CV = 0.5  # CV_OD > 0.5  →  ≥ 1.5× normal travel time
EXTREME_CV = 1.0  # CV_OD > 1.0  →  ≥ 2.0× normal travel time
REACH_H = 1.0  # 1-hour reachability circle

# Hotspot belts (lon_min, lon_max, lat_min, lat_max)
# Priority: first match wins, so more specific regions listed first
REGIONS = [
    ("West Africa", -18, 15, 2, 20),  # Guinea coast extended to lat 2
    ("North Africa", -18, 51, 20, 38),
    ("Sahel-Horn", 15, 51, 8, 22),
    ("East Africa", 28, 51, -12, 12),
    ("Central Africa", 8, 30, -5, 8),
    ("Southern Africa", 10, 51, -35, -5),  # extended to lat -5 to cover N. Angola
]

REGION_COLORS = {
    "West Africa": "#e07b39",
    "Sahel-Horn": "#c94040",
    "East Africa": "#2a7d4f",
    "Southern Africa": "#3a6ea8",
    "North Africa": "#9b59b6",
    "Central Africa": "#d4ac0d",
    "Other": "#aaaaaa",
}


# =============================================================================
# HELPERS
# =============================================================================
def assign_region(lon: float, lat: float) -> str:
    for name, lo0, lo1, la0, la1 in REGIONS:
        if lo0 <= lon <= lo1 and la0 <= lat <= la1:
            return name
    return "Other"


def get_distances(g_ig, city_ig_idx: list) -> np.ndarray:
    """Run igraph multi-source shortest paths; return float64 matrix (hours)."""
    d = np.array(
        g_ig.distances(source=city_ig_idx, target=city_ig_idx, weights="weight"),
        dtype=np.float64,
    )
    d[d >= UNREACHABLE * 0.5] = np.inf
    return d


ISO3_TO_NAME = {
    "AGO": "Angola",
    "BDI": "Burundi",
    "BEN": "Benin",
    "BFA": "Burkina Faso",
    "BWA": "Botswana",
    "CAF": "Central African Republic",
    "CIV": "Ivory Coast",
    "CMR": "Cameroon",
    "COD": "DR Congo",
    "COG": "Congo",
    "DJI": "Djibouti",
    "DZA": "Algeria",
    "EGY": "Egypt",
    "ERI": "Eritrea",
    "ESH": "Western Sahara",
    "ETH": "Ethiopia",
    "GAB": "Gabon",
    "GHA": "Ghana",
    "GIN": "Guinea",
    "GMB": "Gambia",
    "GNB": "Guinea-Bissau",
    "GNQ": "Equatorial Guinea",
    "KEN": "Kenya",
    "LBR": "Liberia",
    "LBY": "Libya",
    "LSO": "Lesotho",
    "MAR": "Morocco",
    "MDG": "Madagascar",
    "MLI": "Mali",
    "MOZ": "Mozambique",
    "MRT": "Mauritania",
    "MWI": "Malawi",
    "NAM": "Namibia",
    "NER": "Niger",
    "NGA": "Nigeria",
    "RWA": "Rwanda",
    "SDN": "Sudan",
    "SEN": "Senegal",
    "SLE": "Sierra Leone",
    "SOM": "Somalia",
    "SSD": "South Sudan",
    "SWZ": "Eswatini",
    "TCD": "Chad",
    "TGO": "Togo",
    "TUN": "Tunisia",
    "TZA": "Tanzania",
    "UGA": "Uganda",
    "ZAF": "South Africa",
    "ZMB": "Zambia",
    "ZWE": "Zimbabwe",
}


def load_world_africa(gadm_dir: Path):
    """Load Africa country boundaries from local GADM _0 shapefiles."""
    import geopandas as gpd

    gdfs = []
    for folder in sorted(gadm_dir.iterdir()):
        iso3 = folder.name.replace("gadm41_", "")
        shp = folder / f"{folder.name}_0.shp"
        if not shp.exists():
            continue
        try:
            gdf = gpd.read_file(shp)[["geometry"]].copy()
            gdf["iso3"] = iso3
            gdf["name"] = ISO3_TO_NAME.get(iso3, iso3)
            gdfs.append(gdf)
        except Exception:
            continue

    if not gdfs:
        return None
    world = pd.concat(gdfs, ignore_index=True)
    return gpd.GeoDataFrame(world, geometry="geometry", crs="EPSG:4326")


def assign_countries(lons: np.ndarray, lats: np.ndarray, world_gdf):
    """Spatial join: point → country name. Falls back to 'Unknown'."""
    if world_gdf is None:
        return ["Unknown"] * len(lons)
    try:
        import geopandas as gpd
        from shapely.geometry import Point

        pts = gpd.GeoDataFrame(
            geometry=[Point(lo, la) for lo, la in zip(lons, lats)],
            crs="EPSG:4326",
        )
        joined = gpd.sjoin(
            pts, world_gdf[["name", "geometry"]], how="left", predicate="within"
        )
        # sjoin can duplicate rows if a point falls in multiple polygons; keep first
        joined = joined[~joined.index.duplicated(keep="first")]
        return joined["name"].fillna("Unknown").tolist()
    except Exception as e:
        print(f"  [WARN] Country assignment failed: {e}")
        return ["Unknown"] * len(lons)


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Result 3 De-isolation Analysis")
    parser.add_argument(
        "--base", required=True, help="Base directory (africa_pavement)"
    )
    parser.add_argument(
        "--paving-fraction",
        type=float,
        default=PAVING_FRACTION,
        help=f"Paving fraction (default {PAVING_FRACTION})",
    )
    args = parser.parse_args()

    base = Path(args.base)
    paving_dir = base / "web" / "network_results" / "bottleneck_paving"
    out_dir = paving_dir / "deisolation"
    out_dir.mkdir(parents=True, exist_ok=True)

    f = args.paving_fraction

    # ── [1] Load experiment state ──────────────────────────────────────────────
    print(f"\n{'='*60}\n  Result 3 De-isolation Analysis\n{'='*60}")
    print(f"\n[1] Loading experiment_state.pkl ...")
    with open(paving_dir / "experiment_state.pkl", "rb") as fh:
        state = pickle.load(fh)

    g0_ig = state["g0_ig"]
    g1_ig = state["g1_ig"]
    city_ig_idx = state["city_ig_idx"]
    pops = np.array(state["pops"], dtype=np.float64)
    bottleneck = state["bottleneck"]
    unpaved_mask = state["unpaved_mask"]

    # ── [2] Load checkpoint for city coordinates ───────────────────────────────
    print("[2] Loading 01_graph_checkpoint.pkl for city coordinates ...")
    with open(paving_dir / "01_graph_checkpoint.pkl", "rb") as fh:
        ckpt = pickle.load(fh)
    node_list = list(ckpt["G0"].nodes())
    all_nc = ckpt["all_nc"]
    del ckpt

    city_lons = np.array([all_nc[node_list[idx]][0] for idx in city_ig_idx])
    city_lats = np.array([all_nc[node_list[idx]][1] for idx in city_ig_idx])
    del all_nc, node_list

    city_regions = [assign_region(lo, la) for lo, la in zip(city_lons, city_lats)]

    n_cities = len(city_ig_idx)
    print(f"   City nodes: {n_cities:,}")
    print(f"   Unpaved edges in pool: {unpaved_mask.sum():,}")

    # ── [3] OD distance matrices (cached as .npy for fast reruns) ────────────
    cache_normal = out_dir / f"cache_d_normal.npy"
    cache_extreme = out_dir / f"cache_d_extreme.npy"
    cache_paved = out_dir / f"cache_d_paved_f{int(f*1000):04d}.npy"

    if cache_normal.exists() and cache_extreme.exists() and cache_paved.exists():
        print("\n[3-6] Loading cached OD distance matrices ...")
        d_normal = np.load(cache_normal)
        d_extreme = np.load(cache_extreme)
        d_paved = np.load(cache_paved)
        print(f"   Loaded from cache (delete .npy files to recompute)")
    else:
        print("\n[3] Computing OD distances — normal weather ...")
        d_normal = get_distances(g0_ig, city_ig_idx)
        np.save(cache_normal, d_normal)

        print("[4] Computing OD distances — extreme weather ...")
        d_extreme = get_distances(g1_ig, city_ig_idx)
        np.save(cache_extreme, d_extreme)

        # ── Apply guided paving at fraction f ─────────────────────────────────
        unpaved_idx = np.where(unpaved_mask)[0]
        order_guided = unpaved_idx[np.argsort(-bottleneck[unpaved_idx])]
        n_pave = int(round(f * len(unpaved_idx)))
        pave_edges = order_guided[:n_pave]

        print(f"\n[5] Applying guided paving (f={f:.0%}, {n_pave:,} edges) ...")
        orig_weights = [g1_ig.es[e]["weight"] for e in pave_edges]
        for e in pave_edges:
            g1_ig.es[e]["weight"] = g0_ig.es[e]["weight"]

        print("[6] Computing OD distances — after paving ...")
        d_paved = get_distances(g1_ig, city_ig_idx)
        np.save(cache_paved, d_paved)

        for e, w in zip(pave_edges, orig_weights):  # restore graph
            g1_ig.es[e]["weight"] = w

    unpaved_idx = np.where(unpaved_mask)[0]
    n_pave = int(round(f * len(unpaved_idx)))

    # ── [5] CV_OD matrices ────────────────────────────────────────────────────
    # CV_OD = t_extreme / t_normal − 1  (same definition as edge-level CV)
    valid_od = np.isfinite(d_normal) & (d_normal > 0)
    cv_extreme = np.full((n_cities, n_cities), np.nan)
    cv_paved = np.full((n_cities, n_cities), np.nan)
    cv_extreme[valid_od] = d_extreme[valid_od] / d_normal[valid_od] - 1.0
    cv_paved[valid_od] = d_paved[valid_od] / d_normal[valid_od] - 1.0
    cv_extreme = np.clip(cv_extreme, 0, None)
    cv_paved = np.clip(cv_paved, 0, None)

    # Upper-triangle indices only (avoid double-counting symmetric OD pairs)
    i_idx, j_idx = np.triu_indices(n_cities, k=1)
    cv_ex = cv_extreme[i_idx, j_idx]
    cv_pv = cv_paved[i_idx, j_idx]
    valid = np.isfinite(cv_ex)

    # ── [6] Result 1 — isolation quantity ─────────────────────────────────────
    print("\n[7] Computing isolation counts (Result 1) ...")

    severe_before = int(np.sum(valid & (cv_ex >= SEVERE_CV)))
    severe_after = int(np.sum(valid & (cv_pv >= SEVERE_CV)))
    extreme_before = int(np.sum(valid & (cv_ex >= EXTREME_CV)))
    extreme_after = int(np.sum(valid & (cv_pv >= EXTREME_CV)))

    # 1-hour reachability per node  (exclude self: k=1 not needed since
    # d[i,i]=0 < 1h, but we subtract the self count below)
    reach_normal = np.sum((d_normal > 0) & (d_normal < REACH_H), axis=1)
    reach_extreme = np.sum((d_extreme > 0) & (d_extreme < REACH_H), axis=1)
    reach_paved = np.sum((d_paved > 0) & (d_paved < REACH_H), axis=1)

    lost_mask = reach_extreme < reach_normal  # nodes losing ≥1 neighbour
    recovered_mask = (reach_paved > reach_extreme) & lost_mask  # regain ≥1 after paving

    pop_isolated_before = float(pops[lost_mask].sum())
    pop_recovered = float(pops[recovered_mask].sum())
    pop_isolated_after = pop_isolated_before - pop_recovered

    total_valid = int(valid.sum())

    r1_rows = [
        {
            "metric": "Severe isolated city pairs  (CV_OD > 0.5, extreme ≥ 1.5× normal)",
            "total_valid_pairs": total_valid,
            "before_paving": severe_before,
            "after_paving_5pct": severe_after,
            "reduction": severe_before - severe_after,
            "reduction_pct": round(
                (severe_before - severe_after) / max(severe_before, 1) * 100, 1
            ),
        },
        {
            "metric": "Extreme isolated city pairs (CV_OD > 1.0, extreme ≥ 2.0× normal)",
            "total_valid_pairs": total_valid,
            "before_paving": extreme_before,
            "after_paving_5pct": extreme_after,
            "reduction": extreme_before - extreme_after,
            "reduction_pct": round(
                (extreme_before - extreme_after) / max(extreme_before, 1) * 100, 1
            ),
        },
        {
            "metric": "Pop. losing ≥1 city within 1-h reach (millions)",
            "total_valid_pairs": "",
            "before_paving": round(pop_isolated_before / 1e6, 3),
            "after_paving_5pct": round(pop_isolated_after / 1e6, 3),
            "reduction": round(pop_recovered / 1e6, 3),
            "reduction_pct": round(
                pop_recovered / max(pop_isolated_before, 1) * 100, 1
            ),
        },
    ]
    df_r1 = pd.DataFrame(r1_rows)
    df_r1.to_csv(out_dir / "R3_isolation_quantity.csv", index=False)

    print(f"\n  ── Result 1: Isolation Quantity Recovery ──")
    for row in r1_rows:
        print(f"  {row['metric']}")
        print(
            f"    Before: {row['before_paving']}   After 5% paving: {row['after_paving_5pct']}"
            f"   Reduction: {row['reduction']} ({row['reduction_pct']}%)"
        )

    # ── [6b] City node–level CSV (needed by GIS export) ──────────────────────
    # Save per-node 1-h reachability metrics for the point layer in QGIS
    city_node_records = []
    for k in range(n_cities):
        city_node_records.append(
            {
                "node_id": k,
                "lon": round(float(city_lons[k]), 5),
                "lat": round(float(city_lats[k]), 5),
                "pop": float(pops[k]),
                "region": city_regions[k],
                "neighbors_1h_normal": int(reach_normal[k]),
                "neighbors_1h_extreme": int(reach_extreme[k]),
                "neighbors_1h_paved": int(reach_paved[k]),
                "neighbors_lost_1h": int(max(0, reach_normal[k] - reach_extreme[k])),
                "neighbors_recovered_1h": int(
                    max(0, reach_paved[k] - reach_extreme[k])
                ),
                "is_1h_isolated": bool(lost_mask[k]),
                "is_1h_recovered": bool(recovered_mask[k]),
            }
        )
    df_city_nodes = pd.DataFrame(city_node_records)
    df_city_nodes.to_csv(out_dir / "R3_city_nodes.csv", index=False)

    # ── [7] Result 2 — OD spatial data ────────────────────────────────────────
    print("\n[8] Building OD de-isolation spatial data (Result 2) ...")

    # Country assignment via local GADM shapefiles
    gadm_dir = base / "RAW" / "GADM_admin"
    print(f"   Loading GADM boundaries from {gadm_dir} ...")
    world_gdf = load_world_africa(gadm_dir)
    if world_gdf is None:
        print("   [WARN] GADM boundaries not found — country assignment skipped")
    else:
        print(f"   GADM loaded: {len(world_gdf)} country polygons")
    city_countries = assign_countries(city_lons, city_lats, world_gdf)

    # De-isolated at severe level: was severe before, not severe after
    deiso_severe = valid & (cv_ex >= SEVERE_CV) & (cv_pv < SEVERE_CV)
    deiso_extreme = valid & (cv_ex >= EXTREME_CV) & (cv_pv < EXTREME_CV)

    od_records = []
    for k in np.where(deiso_severe)[0]:
        i, j = int(i_idx[k]), int(j_idx[k])
        od_records.append(
            {
                "lon_i": float(city_lons[i]),
                "lat_i": float(city_lats[i]),
                "lon_j": float(city_lons[j]),
                "lat_j": float(city_lats[j]),
                "pop_i": float(pops[i]),
                "pop_j": float(pops[j]),
                "country_i": city_countries[i],
                "country_j": city_countries[j],
                "region_i": city_regions[i],
                "region_j": city_regions[j],
                "is_cross_border": city_countries[i] != city_countries[j],
                "cv_od_before": round(float(cv_ex[k]), 3),
                "cv_od_after": round(float(cv_pv[k]), 3),
                "severity_before": "extreme" if cv_ex[k] >= EXTREME_CV else "severe",
            }
        )

    df_od = pd.DataFrame(od_records)
    df_od.to_csv(out_dir / "R3_od_deisolation.csv", index=False)
    n_deiso_severe = int(deiso_severe.sum())
    n_deiso_extreme = int(deiso_extreme.sum())
    n_cross = int(df_od["is_cross_border"].sum()) if not df_od.empty else 0
    print(f"   Severe→not-severe de-isolated pairs:   {n_deiso_severe:,}")
    print(f"   Extreme→not-extreme de-isolated pairs: {n_deiso_extreme:,}")
    print(f"   Cross-border de-isolated pairs:        {n_cross:,}")

    # ── [8] Country summary ────────────────────────────────────────────────────
    country_rows = []
    for country in sorted(set(city_countries)):
        in_c = np.array([c == country for c in city_countries], dtype=bool)
        c_i = in_c[i_idx]
        c_j = in_c[j_idx]
        either = c_i | c_j

        country_rows.append(
            {
                "country": country,
                "n_city_nodes": int(in_c.sum()),
                "severe_pairs_before": int(
                    np.sum(valid & either & (cv_ex >= SEVERE_CV))
                ),
                "severe_pairs_after_5pct": int(
                    np.sum(valid & either & (cv_pv >= SEVERE_CV))
                ),
                "severe_pairs_reduced": int(np.sum(deiso_severe & either)),
                "extreme_pairs_before": int(
                    np.sum(valid & either & (cv_ex >= EXTREME_CV))
                ),
                "extreme_pairs_after_5pct": int(
                    np.sum(valid & either & (cv_pv >= EXTREME_CV))
                ),
                "pop_1h_isolated_before_M": round(
                    float(pops[lost_mask & in_c].sum()) / 1e6, 3
                ),
                "pop_1h_recovered_M": round(
                    float(pops[recovered_mask & in_c].sum()) / 1e6, 3
                ),
            }
        )

    df_country = (
        pd.DataFrame(country_rows)
        .sort_values("severe_pairs_reduced", ascending=False)
        .reset_index(drop=True)
    )
    df_country.to_csv(out_dir / "R3_country_summary.csv", index=False)
    print(f"\n  Top 10 countries by severe-pair reduction:")
    print(
        df_country.head(10)[
            [
                "country",
                "severe_pairs_before",
                "severe_pairs_reduced",
                "pop_1h_recovered_M",
            ]
        ].to_string(index=False)
    )

    # ── [9] Region summary ─────────────────────────────────────────────────────
    region_rows = []
    all_region_names = [r[0] for r in REGIONS] + ["Other"]
    for reg in all_region_names:
        in_r = np.array([r == reg for r in city_regions], dtype=bool)
        r_i = in_r[i_idx]
        r_j = in_r[j_idx]
        either = r_i | r_j

        region_rows.append(
            {
                "region": reg,
                "n_city_nodes": int(in_r.sum()),
                "severe_pairs_before": int(
                    np.sum(valid & either & (cv_ex >= SEVERE_CV))
                ),
                "severe_pairs_after_5pct": int(
                    np.sum(valid & either & (cv_pv >= SEVERE_CV))
                ),
                "severe_pairs_reduced": int(np.sum(deiso_severe & either)),
                "extreme_pairs_reduced": int(np.sum(deiso_extreme & either)),
                "pop_1h_isolated_before_M": round(
                    float(pops[lost_mask & in_r].sum()) / 1e6, 3
                ),
                "pop_1h_recovered_M": round(
                    float(pops[recovered_mask & in_r].sum()) / 1e6, 3
                ),
            }
        )

    df_region = (
        pd.DataFrame(region_rows)
        .sort_values("severe_pairs_reduced", ascending=False)
        .reset_index(drop=True)
    )
    df_region.to_csv(out_dir / "R3_region_summary.csv", index=False)
    print(f"\n  Region summary:")
    print(
        df_region[
            [
                "region",
                "severe_pairs_before",
                "severe_pairs_reduced",
                "pop_1h_recovered_M",
            ]
        ].to_string(index=False)
    )

    # ── [10] Spatial map ───────────────────────────────────────────────────────
    print("\n[10] Drawing de-isolation map ...")
    _draw_map(
        city_lons,
        city_lats,
        city_regions,
        pops,
        i_idx,
        j_idx,
        deiso_severe,
        cv_ex,
        lost_mask,
        recovered_mask,
        df_region,
        world_gdf,
        out_dir,
        f,
    )

    print(f"\n{'='*60}")
    print(f"  Outputs saved → {out_dir}")
    print(f"{'='*60}")


# =============================================================================
# MAP
# =============================================================================
def _draw_map(
    city_lons,
    city_lats,
    city_regions,
    pops,
    i_idx,
    j_idx,
    deiso_mask,
    cv_ex,
    lost_mask,
    recovered_mask,
    df_region,
    world_gdf,
    out_dir,
    f,
):
    fig, axes = plt.subplots(1, 2, figsize=(18, 9))

    # ── Left panel: de-isolation arcs ─────────────────────────────────────────
    ax = axes[0]
    ax.set_facecolor("#1a1a2e")
    ax.set_xlim(-20, 55)
    ax.set_ylim(-38, 40)

    # Draw country outlines if available
    if world_gdf is not None:
        try:
            world_gdf.boundary.plot(ax=ax, linewidth=0.4, color="#444466", zorder=1)
        except Exception:
            pass

    # Arc lines for de-isolated pairs (alpha-blended, coloured by severity)
    deiso_idx = np.where(deiso_mask)[0]
    # Down-sample if too many to render clearly
    rng = np.random.default_rng(42)
    if len(deiso_idx) > 20_000:
        deiso_idx = rng.choice(deiso_idx, size=20_000, replace=False)

    for k in deiso_idx:
        i, j = int(i_idx[k]), int(j_idx[k])
        lo0, la0 = city_lons[i], city_lats[i]
        lo1, la1 = city_lons[j], city_lats[j]
        sev = cv_ex[k]
        color = "#ff4444" if sev >= 1.0 else "#ff9944"
        ax.plot([lo0, lo1], [la0, la1], "-", color=color, alpha=0.04, lw=0.4, zorder=2)

    # Cities coloured by region
    for reg in set(city_regions):
        mask_reg = np.array([r == reg for r in city_regions])
        c = REGION_COLORS.get(reg, "#aaaaaa")
        ax.scatter(
            city_lons[mask_reg],
            city_lats[mask_reg],
            s=1.5,
            c=c,
            alpha=0.5,
            zorder=3,
            linewidths=0,
        )

    # Recovered-population bubble overlay
    if recovered_mask.any():
        rec_lons = city_lons[recovered_mask]
        rec_lats = city_lats[recovered_mask]
        rec_pops = pops[recovered_mask]
        sizes = np.clip(rec_pops / rec_pops.max() * 60, 2, 60)
        ax.scatter(
            rec_lons,
            rec_lats,
            s=sizes,
            c="#00ffcc",
            alpha=0.6,
            zorder=4,
            linewidths=0,
            label="Pop. regaining 1-h neighbour",
        )

    # Legend for arc colours
    ax.plot(
        [], [], "-", color="#ff4444", lw=1.5, label="Extreme isolated → de-isolated"
    )
    ax.plot([], [], "-", color="#ff9944", lw=1.5, label="Severe isolated → de-isolated")
    ax.legend(loc="lower left", fontsize=7.5, framealpha=0.6)
    ax.set_title(
        f"City-pair de-isolation after targeted paving (f = {f:.0%})\n"
        f"Arc = corridor restored; dot = population regaining 1-h access",
        fontsize=10,
        color="white",
        pad=8,
    )
    ax.set_xlabel("Longitude", fontsize=9, color="white")
    ax.set_ylabel("Latitude", fontsize=9, color="white")
    ax.tick_params(colors="white", labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor("#444466")

    # ── Right panel: region bar chart ─────────────────────────────────────────
    ax2 = axes[1]
    df_plot = df_region[df_region["n_city_nodes"] > 0].copy()
    regs = df_plot["region"].tolist()
    colors = [REGION_COLORS.get(r, "#aaaaaa") for r in regs]

    x = np.arange(len(regs))
    w = 0.38

    bars1 = ax2.bar(
        x - w / 2,
        df_plot["severe_pairs_before"],
        width=w,
        color=colors,
        alpha=0.45,
        label="Severe isolated pairs — before paving",
    )
    bars2 = ax2.bar(
        x + w / 2,
        df_plot["severe_pairs_reduced"],
        width=w,
        color=colors,
        alpha=0.95,
        label="De-isolated by 5% targeted paving",
    )

    # Population recovered as secondary axis
    ax2b = ax2.twinx()
    ax2b.plot(
        x,
        df_plot["pop_1h_recovered_M"],
        "D--",
        color="#00ddaa",
        ms=7,
        lw=1.5,
        label="Pop. regaining 1-h neighbour (M)",
    )
    ax2b.set_ylabel("Population recovered (millions)", fontsize=9, color="#00ddaa")
    ax2b.tick_params(axis="y", colors="#00ddaa", labelsize=8)

    ax2.set_xticks(x)
    ax2.set_xticklabels(regs, rotation=30, ha="right", fontsize=9)
    ax2.set_ylabel("Number of city-pair corridors", fontsize=9)
    ax2.set_title(
        "Climate-isolated corridor reduction by region\n"
        "Severe isolation (CV_OD > 0.5, extreme ≥ 1.5× normal travel time)",
        fontsize=10,
        pad=8,
    )

    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2b.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper right")
    ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    out_path = out_dir / "R3_deisolation_map.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="#1a1a2e")
    plt.close(fig)
    print(f"   Saved → {out_path.name}")


if __name__ == "__main__":
    main()
