"""
compute_health_accessibility.py
================================
Conclusion 2 Analysis: Spatial Inequality and Climate-Isolation Compounding

Three-step pipeline:
  Step 1  Node-level accessibility — travel time from each network node to
          the nearest health facility under G0 (normal) and G1 (extreme).
  Step 2  Population-weighted aggregation — PWMTT, percentile distributions
          (P10/P50/P90), and their climate-induced changes.
  Step 3  Inequality verification — Spearman ρ between baseline accessibility
          and Δt, plus Gini coefficient before/after climate shock.

Outputs (written to OUTPUT_DIR):
  node_accessibility_{country}.csv    — per-node t_normal, t_extreme, Δt, pop
  country_accessibility_summary.csv   — PWMTT / Gini / Spearman per country
  africa_accessibility_summary.csv    — continent-level aggregation

Inputs:
    <BASE_DIR>/RAW/Road_data/{country}/{country}.shp
    <BASE_DIR>/road_speed_cordex/{country}_road_speed.csv
    <BASE_DIR>/RAW/Health_data/{country}_health.csv
    <BASE_DIR>/RAW/Pop_data/{iso3}_ppp_2020_UNadj_constrained.tif

Outputs:
    <OUTPUT_DIR>/node_accessibility_{country}.csv
    <OUTPUT_DIR>/country_accessibility_summary.csv
    <OUTPUT_DIR>/africa_accessibility_summary.csv

Default OUTPUT_DIR:
    <BASE_DIR>/web/health_accessibility/

Usage:
    python data_procession/compute_health_accessibility.py --base-dir <BASE_DIR>
    python data_procession/compute_health_accessibility.py --base-dir <BASE_DIR> --country Kenya
"""

import argparse
import gc
import time
import warnings
from collections import defaultdict
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")

# =============================================================================
# CONFIGURATION — mirror network_pipeline.py settings
# =============================================================================
BASE_DIR_DEFAULT = Path("path/to/base")

SNAP_THRESHOLD_DEG = 0.0045  # ~500 m — same as pipeline
MIN_ROAD_LENGTH_KM = 0.1
BLOCK_PROB_THRESH = 0.5
UNREACHABLE_H = 1e6  # travel-time sentinel for unreachable nodes (hours)
MAX_HEALTH_SNAP_KM = 50.0  # discard health facilities >50 km from any road node

# WorldPop ISO-3 prefix → country folder mapping
WORLDPOP_PREFIX = {
    "Algeria": "dza",
    "Angola": "ago",
    "Benin": "ben",
    "Botswana": "bwa",
    "BurkinaFaso": "bfa",
    "Burundi": "bdi",
    "Cameroon": "cmr",
    "CentralAfrican": "caf",
    "Chad": "tcd",
    "Congo": "cog",
    "CongoDR": "cod",
    "Djibouti": "dji",
    "Egypt": "egy",
    "Equatorial": "gnq",
    "Eritrea": "eri",
    "Ethiopia": "eth",
    "Gabon": "gab",
    "Gambia": "gmb",
    "Ghana": "gha",
    "Guinea": "gin",
    "GuineaBissau": "gnb",
    "IvoryCoast": "civ",
    "Kenya": "ken",
    "Lesotho": "lso",
    "Liberia": "lbr",
    "Libya": "lby",
    "Madagascar": "mdg",
    "Malawi": "mwi",
    "Mali": "mli",
    "Mauritania": "mrt",
    "Morocco": "mar",
    "Mozambique": "moz",
    "Namibia": "nam",
    "Niger": "ner",
    "Nigeria": "nga",
    "Rwanda": "rwa",
    "Senegal": "sen",
    "SierraLeone": "sle",
    "Somalia": "som",
    "SouthAfrica": "zaf",
    "SouthSudan": "ssd",
    "Sudan": "sdn",
    "Swaziland": "swz",
    "Tanzania": "tza",
    "Togo": "tgo",
    "Tunisia": "tun",
    "Uganda": "uga",
    "WestSahara": "",  # no WorldPop TIF — will use uniform weight
    "Zambia": "zmb",
    "Zimbabwe": "zwe",
}


# =============================================================================
# GRAPH BUILDING (simplified, unpaved-only, matching pipeline)
# =============================================================================
def _merge_endpoints(pts_arr, same_pairs, threshold):
    N = len(pts_arr)
    parent = list(range(N))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        r_a, r_b = find(a), find(b)
        if r_a != r_b:
            parent[r_b] = r_a

    tree = cKDTree(pts_arr)
    for i, j in tree.query_pairs(threshold):
        if (min(i, j), max(i, j)) not in same_pairs:
            union(i, j)

    groups = defaultdict(list)
    for i in range(N):
        groups[find(i)].append(i)

    node_id_of = [0] * N
    node_coords = {}
    nid = 0
    for root, members in groups.items():
        node_coords[nid] = (
            pts_arr[members, 0].mean(),
            pts_arr[members, 1].mean(),
        )
        for m in members:
            node_id_of[m] = nid
        nid += 1
    return node_id_of, node_coords


def build_graphs(shp_path: Path, iri_path: Path):
    """Build G0 (normal) and G1 (extreme) weighted graphs for unpaved roads."""
    import geopandas as gpd

    gdf = gpd.read_file(shp_path)
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    if "length_km" not in gdf.columns:
        gdf_m = gdf.to_crs("ESRI:102022")
        gdf["length_km"] = gdf_m.geometry.length / 1000

    surf_col = next(
        (c for c in ["Surface", "surface", "fclass", "highway"] if c in gdf.columns),
        None,
    )
    if surf_col:
        gdf = gdf[gdf[surf_col].str.lower().str.contains("unpaved", na=False)].copy()
    gdf = gdf[gdf["length_km"] >= MIN_ROAD_LENGTH_KM].reset_index(drop=True)

    stem = Path(shp_path).stem
    if "road_id" not in gdf.columns:
        gdf["road_id"] = [f"{stem}_road_{i}" for i in range(len(gdf))]

    df_iri = pd.read_csv(iri_path)
    df_iri["V_normal"] = df_iri["V_normal"].clip(lower=0.01)
    df_iri["V_extreme"] = df_iri["V_extreme"].clip(lower=0.01)
    if "passable_rate_extreme" in df_iri.columns:
        df_iri["p_block"] = (1.0 - df_iri["passable_rate_extreme"].clip(0, 1)).clip(
            0, 0.99
        )
    elif "p_block" not in df_iri.columns:
        df_iri["p_block"] = (
            (df_iri["V_normal"] - df_iri["V_extreme"]) / df_iri["V_normal"]
        ).clip(0, 0.99)

    iri_lu = (
        df_iri[["road_id", "V_normal", "V_extreme", "p_block"]]
        .set_index("road_id")
        .to_dict("index")
    )
    v_n_med = df_iri["V_normal"].median()
    v_e_med = v_n_med

    # Endpoint extraction
    coords_list, road_ep_idx, same_pairs = [], [], set()
    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            road_ep_idx.append(None)
            continue
        try:
            if geom.geom_type == "MultiLineString":
                sc, ec = geom.geoms[0].coords[0], geom.geoms[-1].coords[-1]
            elif geom.geom_type == "LineString":
                sc, ec = geom.coords[0], geom.coords[-1]
            else:
                road_ep_idx.append(None)
                continue
        except Exception:
            road_ep_idx.append(None)
            continue
        si, ei = len(coords_list), len(coords_list) + 1
        coords_list += [(sc[0], sc[1]), (ec[0], ec[1])]
        road_ep_idx.append((si, ei))
        same_pairs.add((min(si, ei), max(si, ei)))

    pts_arr = np.array(coords_list, dtype=np.float64)
    node_id_of, node_coords = _merge_endpoints(pts_arr, same_pairs, SNAP_THRESHOLD_DEG)

    G0, G1 = nx.Graph(), nx.Graph()
    for nid, (lon, lat) in node_coords.items():
        G0.add_node(nid, lon=lon, lat=lat)
        G1.add_node(nid, lon=lon, lat=lat)

    for ridx in range(len(gdf)):
        ep = road_ep_idx[ridx]
        if ep is None:
            continue
        si, ei = ep
        u, v = node_id_of[si], node_id_of[ei]
        if u == v:
            continue
        row_gdf = gdf.iloc[ridx]
        road_id = row_gdf["road_id"]
        lkm = float(row_gdf.get("length_km", 1.0)) or 1.0
        if road_id in iri_lu:
            d = iri_lu[road_id]
            V_n, V_e, pb = d["V_normal"], d["V_extreme"], d["p_block"]
        else:
            V_n, V_e, pb = v_n_med, v_e_med, 0.0
        w0 = lkm / V_n
        w1 = lkm / V_e / (1.0 - min(pb, 0.99))
        if G0.has_edge(u, v):
            if w0 < G0[u][v].get("weight", 1e9):
                G0[u][v]["weight"] = w0
                G1[u][v]["weight"] = w1
        else:
            G0.add_edge(u, v, weight=w0)
            G1.add_edge(u, v, weight=w1)

    print(f"  Graph: {G0.number_of_nodes():,} nodes, {G0.number_of_edges():,} edges")
    return G0, G1, node_coords


# =============================================================================
# STEP 1  NODE-LEVEL ACCESSIBILITY
# =============================================================================
def load_health_facilities(health_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(health_csv)
    df = df.dropna(subset=["lon", "lat"])
    df["lon"] = df["lon"].astype(float)
    df["lat"] = df["lat"].astype(float)
    return df


def snap_health_to_network(health_df: pd.DataFrame, node_coords: dict) -> list[int]:
    """Return list of node IDs for health facilities within MAX_HEALTH_SNAP_KM."""
    if health_df.empty:
        return []
    net_nodes = list(node_coords.keys())
    net_xy = np.array([node_coords[n] for n in net_nodes])
    tree = cKDTree(net_xy)

    health_xy = health_df[["lon", "lat"]].values
    dists, idxs = tree.query(health_xy)

    snapped = []
    for dist_deg, idx in zip(dists, idxs):
        dist_km = dist_deg * 111.0
        if dist_km <= MAX_HEALTH_SNAP_KM:
            snapped.append(net_nodes[idx])

    # De-duplicate: multiple facilities may snap to the same network node
    return list(set(snapped))


def compute_nearest_health_time(
    G: nx.Graph, health_node_ids: list[int]
) -> dict[int, float]:
    """
    Multi-source Dijkstra: distance from EACH node to the NEAREST health facility.
    Returns {node_id: travel_time_hours}.
    """
    if not health_node_ids:
        return {}
    sources = [n for n in health_node_ids if n in G]
    if not sources:
        return {}
    lengths = nx.multi_source_dijkstra_path_length(G, sources=sources, weight="weight")
    return dict(lengths)


# =============================================================================
# STEP 2  POPULATION WEIGHTING
# =============================================================================
# Maximum distance (km) to assign a population pixel to a road node.
# Pixels farther than this from any road node are excluded (e.g. deep desert).
MAX_POP_SNAP_KM = 50.0


def aggregate_population_to_nodes(
    pop_tif: Path,
    node_list: list,
    lons: np.ndarray,
    lats: np.ndarray,
) -> np.ndarray:
    """
    Correct population-weighting for road-network nodes.

    Logic
    -----
    For each populated WorldPop pixel (value > 0):
      1. Find the nearest road-network node via cKDTree.
      2. Accumulate that pixel's population count onto the node.

    This is the inverse of naively sampling the raster at node coordinates,
    which would give the population AT the road junction itself (usually 0,
    because intersections are rarely where people live).  Instead, every
    inhabited pixel "flows" to its nearest road node, so the node's population
    represents the catchment area it serves.

    Node selection
    --------------
    Nodes passed here are already filtered to the Largest Connected Component
    (LCC) of G0, so all included nodes:
      • lie on unpaved roads with a valid IRI speed record (or median fill),
      • are reachable from at least one other node under normal conditions,
      • have a coordinate that falls within the country boundary (road data is
        per-country).
    Nodes with zero aggregated population are kept in Dijkstra (they still
    affect routing) but are excluded from population-weighted statistics
    (PWMTT, Gini, Spearman) because they represent no one.
    """
    try:
        import rasterio

        with rasterio.open(pop_tif) as src:
            data = src.read(1).astype(np.float32)
            nodata = src.nodata
            transform = src.transform

        # --- mask nodata / negative sentinels (WorldPop uses -99999) ---
        if nodata is not None:
            data[data == nodata] = 0.0
        data[data < 0] = 0.0
        data = np.nan_to_num(data, nan=0.0)

        # --- pixel coordinates (centre of each populated cell) ---
        rows, cols = np.where(data > 0)
        if len(rows) == 0:
            print("    [WARN] Population raster has no positive values")
            return np.zeros(len(node_list), dtype=float)

        pix_lons = transform.c + (cols + 0.5) * transform.a  # lon
        pix_lats = transform.f + (rows + 0.5) * transform.e  # lat  (e < 0)
        pix_pop = data[rows, cols].astype(float)

        print(
            f"    WorldPop pixels with pop>0: {len(pix_pop):,}  "
            f"total pop: {pix_pop.sum():,.0f}"
        )

        # --- nearest-node assignment via cKDTree ---
        node_xy = np.column_stack([lons, lats])  # (N_nodes, 2)
        pix_xy = np.column_stack([pix_lons, pix_lats])  # (N_pixels, 2)
        tree = cKDTree(node_xy)

        dists, nearest_idx = tree.query(pix_xy, workers=-1)  # workers=-1 = all CPUs

        # discard pixels too far from any road node (isolated area)
        threshold_deg = MAX_POP_SNAP_KM / 111.0
        valid = dists <= threshold_deg
        nearest_idx = nearest_idx[valid]
        pix_pop_valid = pix_pop[valid]

        print(
            f"    Pixels within {MAX_POP_SNAP_KM} km of a road node: "
            f"{valid.sum():,} / {len(valid):,}  "
            f"({valid.mean()*100:.1f}%)"
        )

        # --- accumulate population per node ---
        pop_per_node = np.zeros(len(node_list), dtype=float)
        np.add.at(pop_per_node, nearest_idx, pix_pop_valid)

        n_nodes_with_pop = int((pop_per_node > 0).sum())
        print(f"    Nodes with pop>0: {n_nodes_with_pop:,} / {len(node_list):,}")

        return pop_per_node

    except Exception as exc:
        print(f"    [WARN] Population aggregation failed: {exc} — using uniform weight")
        return np.ones(len(node_list), dtype=float)


def population_weighted_stats(t: np.ndarray, pop: np.ndarray, label: str) -> dict:
    """Compute PWMTT and population-weighted percentiles."""
    mask = np.isfinite(t) & (t < UNREACHABLE_H) & (pop > 0)
    t_m, pop_m = t[mask], pop[mask]
    if len(t_m) == 0:
        return {
            f"pwmtt_{label}": np.nan,
            f"p10_{label}": np.nan,
            f"p50_{label}": np.nan,
            f"p90_{label}": np.nan,
            f"pct_unreachable_{label}": 1.0,
        }

    total_pop = pop_m.sum()
    pwmtt = float(np.sum(t_m * pop_m) / total_pop)

    # Population-weighted percentiles via cumulative sum approach
    sort_idx = np.argsort(t_m)
    t_sorted = t_m[sort_idx]
    pop_sorted = pop_m[sort_idx]
    cum_pop = np.cumsum(pop_sorted) / total_pop

    def quantile(q):
        idx = np.searchsorted(cum_pop, q)
        return float(t_sorted[min(idx, len(t_sorted) - 1)])

    pct_unreachable = float(1.0 - mask.sum() / len(t))

    return {
        f"pwmtt_{label}": pwmtt,
        f"p10_{label}": quantile(0.10),
        f"p50_{label}": quantile(0.50),
        f"p90_{label}": quantile(0.90),
        f"pct_unreachable_{label}": pct_unreachable,
    }


# =============================================================================
# STEP 2b  ISOCHRONE POPULATION COVERAGE
# =============================================================================
# Time thresholds (hours) for isochrone analysis.
# WHO recommends a health facility reachable within 1–2 hours as a benchmark.
ISOCHRONE_THRESHOLDS_H = [0.5, 1.0, 2.0, 4.0]


def isochrone_coverage(
    t_normal: np.ndarray,
    t_extreme: np.ndarray,
    pop: np.ndarray,
    thresholds: list[float] = ISOCHRONE_THRESHOLDS_H,
) -> dict:
    """
    For each time threshold T, compute:
      pop_coverage_normal  — population reachable within T hours under G0
      pop_coverage_extreme — population reachable within T hours under G1
      shrinkage_rate       — fractional loss of covered population

    This is the 'isochrone' metric: instead of geographic area (which requires
    polygon construction), we use population as the measure of coverage.
    Shrinkage rate > 0 means climate pushes people outside the time threshold.

    Example interpretation:
      T=2h, shrinkage=0.18 → 18% of the population that could reach a hospital
      in ≤2h under normal conditions can no longer do so under extreme climate.
    """
    total_pop = pop.sum()
    if total_pop == 0:
        return {}

    result = {}
    for T in thresholds:
        key = f"T{int(T*60)}min"  # e.g. T120min

        reachable_n = (t_normal < T) & np.isfinite(t_normal)
        reachable_e = (t_extreme < T) & np.isfinite(t_extreme)

        cov_n = float(pop[reachable_n].sum())
        cov_e = float(pop[reachable_e].sum())
        shrink = (cov_n - cov_e) / cov_n if cov_n > 0 else 0.0

        result[f"isochrone_pop_normal_{key}"] = cov_n
        result[f"isochrone_pop_extreme_{key}"] = cov_e
        result[f"isochrone_shrinkage_{key}"] = shrink
        result[f"isochrone_pct_normal_{key}"] = cov_n / total_pop
        result[f"isochrone_pct_extreme_{key}"] = cov_e / total_pop

    return result


# =============================================================================
# STEP 3  INEQUALITY VERIFICATION
# =============================================================================
def gini(x: np.ndarray) -> float:
    """Gini coefficient (ignores NaN / negative)."""
    x = x[np.isfinite(x) & (x >= 0)]
    if len(x) < 2:
        return np.nan
    x = np.sort(x)
    n = len(x)
    cumsum = np.cumsum(x)
    return float(((n + 1) * x.sum() - 2 * np.sum(cumsum)) / (n * x.sum() + 1e-12))


def inequality_metrics(
    t_normal: np.ndarray,
    t_extreme: np.ndarray,
    pop: np.ndarray,
) -> dict:
    """
    Compute:
      - Gini coefficient of travel time before/after climate shock
      - Spearman ρ between baseline travel time and Δt
      - Tail-gap: (P90 Δt) / (P50 Δt)
    All using population-weighted replication to respect population counts.
    """
    delta = t_extreme - t_normal
    mask = (
        np.isfinite(t_normal)
        & np.isfinite(t_extreme)
        & (t_normal < UNREACHABLE_H)
        & (t_extreme < UNREACHABLE_H)
        & (pop > 0)
    )
    t0_m, t1_m, dt_m, pop_m = t_normal[mask], t_extreme[mask], delta[mask], pop[mask]
    if len(t0_m) < 10:
        return {
            "gini_normal": np.nan,
            "gini_extreme": np.nan,
            "delta_gini": np.nan,
            "spearman_rho": np.nan,
            "spearman_pval": np.nan,
            "p90_delta_h": np.nan,
            "p50_delta_h": np.nan,
            "tail_gap_ratio": np.nan,
        }

    # Population-weighted Gini using integer weights (rounded to nearest person)
    weights = np.round(pop_m / pop_m.min()).clip(1, 500).astype(int)
    t0_rep = np.repeat(t0_m, weights)
    t1_rep = np.repeat(t1_m, weights)
    dt_rep = np.repeat(dt_m, weights)

    gini_n = gini(t0_rep)
    gini_e = gini(t1_rep)

    # Spearman: baseline accessibility vs delta
    rho, pval = spearmanr(t0_rep, dt_rep)

    # Population-weighted P90 and P50 of Δt
    sort_idx = np.argsort(dt_m)
    dt_sorted = dt_m[sort_idx]
    pop_sorted = pop_m[sort_idx]
    cum_pop = np.cumsum(pop_sorted) / pop_sorted.sum()
    p50_dt = float(dt_sorted[np.searchsorted(cum_pop, 0.50)])
    p90_dt = float(dt_sorted[np.searchsorted(cum_pop, 0.90)])
    tail_gap = p90_dt / p50_dt if p50_dt > 0 else np.nan

    return {
        "gini_normal": gini_n,
        "gini_extreme": gini_e,
        "delta_gini": gini_e - gini_n,
        "spearman_rho": float(rho),
        "spearman_pval": float(pval),
        "p90_delta_h": p90_dt,
        "p50_delta_h": p50_dt,
        "tail_gap_ratio": tail_gap,
    }


# =============================================================================
# PER-COUNTRY PIPELINE
# =============================================================================
def process_country(
    country: str,
    base_dir: Path,
    output_dir: Path,
) -> dict | None:
    shp_path = base_dir / "RAW/Road_data" / country / f"{country}.shp"
    iri_path = base_dir / "road_speed_cordex" / f"{country}_road_speed.csv"
    hlth_path = base_dir / "RAW/Health_data" / f"{country}_health.csv"
    prefix = WORLDPOP_PREFIX.get(country, "")
    pop_path = base_dir / "RAW/Pop_data" / f"{prefix}_ppp_2020_UNadj_constrained.tif"

    # Validate inputs
    missing = [p for p in [shp_path, iri_path, hlth_path] if not p.exists()]
    if missing:
        print(f"  [SKIP] {country}: missing files: {[str(m) for m in missing]}")
        return None

    # Check health CSV has data (not just header)
    health_df = load_health_facilities(hlth_path)
    if health_df.empty:
        print(
            f"  [SKIP] {country}: health CSV has no data rows — run fetch_health_facilities.py first"
        )
        return None

    print(f"\n{'='*60}\n  {country}  ({len(health_df)} health facilities)\n{'='*60}")
    t_start = time.time()

    # ----- Step 1: Build graphs and compute accessibility -----
    print("  [1/3] Building road network graphs ...")
    G0, G1, node_coords = build_graphs(shp_path, iri_path)

    # Extract largest connected component for G0 (use as reference graph)
    lcc_nodes = max(nx.connected_components(G0), key=len)
    G0 = G0.subgraph(lcc_nodes).copy()
    G1 = G1.subgraph(lcc_nodes).copy()
    node_coords = {k: v for k, v in node_coords.items() if k in lcc_nodes}

    # Snap health facilities to network
    health_nodes = snap_health_to_network(health_df, node_coords)
    if not health_nodes:
        print(
            f"  [SKIP] {country}: no health facilities within {MAX_HEALTH_SNAP_KM} km of road network"
        )
        return None
    print(f"  Snapped {len(health_nodes)} unique health-facility anchor nodes")

    # Multi-source Dijkstra
    print("  Computing nearest-health travel times (normal) ...")
    t_normal_map = compute_nearest_health_time(G0, health_nodes)

    print("  Computing nearest-health travel times (extreme) ...")
    t_extreme_map = compute_nearest_health_time(G1, health_nodes)

    # Assemble per-node DataFrame
    node_list = list(node_coords.keys())
    lons = np.array([node_coords[n][0] for n in node_list])
    lats = np.array([node_coords[n][1] for n in node_list])
    t_normal_arr = np.array([t_normal_map.get(n, UNREACHABLE_H) for n in node_list])
    t_extreme_arr = np.array([t_extreme_map.get(n, UNREACHABLE_H) for n in node_list])
    delta_arr = t_extreme_arr - t_normal_arr

    # ----- Step 2: Population weighting -----
    print("  [2/3] Aggregating WorldPop pixels → road nodes ...")
    if pop_path.exists():
        pop_arr = aggregate_population_to_nodes(pop_path, node_list, lons, lats)
    else:
        print(f"  [WARN] WorldPop TIF not found for {country} — setting pop=1 per node")
        pop_arr = np.ones(len(node_list), dtype=float)

    node_df = pd.DataFrame(
        {
            "country": country,
            "node_id": node_list,
            "lon": lons,
            "lat": lats,
            "t_normal": t_normal_arr,
            "t_extreme": t_extreme_arr,
            "delta_t": delta_arr,
            "population": pop_arr,
        }
    )

    out_node_path = output_dir / f"node_accessibility_{country}.csv"
    node_df.to_csv(out_node_path, index=False)
    print(f"  Node-level results → {out_node_path.name}")

    # Population-weighted stats for normal and extreme
    stats_n = population_weighted_stats(t_normal_arr, pop_arr, "normal")
    stats_e = population_weighted_stats(t_extreme_arr, pop_arr, "extreme")
    stats_dt = population_weighted_stats(delta_arr, pop_arr, "delta")

    # Isochrone population coverage at multiple time thresholds
    iso = isochrone_coverage(t_normal_arr, t_extreme_arr, pop_arr)

    # ----- Step 3: Inequality metrics -----
    print("  [3/3] Computing inequality metrics ...")
    ineq = inequality_metrics(t_normal_arr, t_extreme_arr, pop_arr)

    n_reachable_n = int(
        np.sum((t_normal_arr < UNREACHABLE_H) & np.isfinite(t_normal_arr))
    )
    n_reachable_e = int(
        np.sum((t_extreme_arr < UNREACHABLE_H) & np.isfinite(t_extreme_arr))
    )
    n_nodes = len(node_list)
    total_pop = float(pop_arr.sum())
    runtime = time.time() - t_start

    summary = {
        "country": country,
        "n_nodes": n_nodes,
        "n_health_anchors": len(health_nodes),
        "n_health_facilities": len(health_df),
        "n_reachable_normal": n_reachable_n,
        "n_reachable_extreme": n_reachable_e,
        "total_population": total_pop,
        **stats_n,
        **stats_e,
        **stats_dt,
        **iso,
        **ineq,
        "runtime_s": round(runtime, 1),
    }

    print(
        f"  PWMTT normal={stats_n['pwmtt_normal']:.3f}h  extreme={stats_e['pwmtt_extreme']:.3f}h"
    )
    for T in ISOCHRONE_THRESHOLDS_H:
        key = f"T{int(T*60)}min"
        shrink = iso.get(f"isochrone_shrinkage_{key}", float("nan"))
        pct_n = iso.get(f"isochrone_pct_normal_{key}", float("nan"))
        pct_e = iso.get(f"isochrone_pct_extreme_{key}", float("nan"))
        print(
            f"  Isochrone {T:.1f}h: {pct_n*100:.1f}% → {pct_e*100:.1f}%  shrinkage={shrink*100:.1f}%"
        )
    print(
        f"  Gini: {ineq['gini_normal']:.4f} → {ineq['gini_extreme']:.4f}  (Δ={ineq['delta_gini']:+.4f})"
    )
    print(f"  Spearman ρ={ineq['spearman_rho']:.4f}  p={ineq['spearman_pval']:.4e}")
    print(f"  Tail gap (P90_Δ / P50_Δ) = {ineq['tail_gap_ratio']:.2f}")
    print(f"  Done in {runtime:.1f}s")

    gc.collect()
    return summary


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Compute health accessibility under climate shock"
    )
    parser.add_argument(
        "--base-dir", required=True, help="Path to africa_pavement directory"
    )
    parser.add_argument(
        "--country",
        default=None,
        help="Process only this country folder name (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: <base-dir>/web/health_accessibility)",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else base_dir / "web/health_accessibility"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    countries = [args.country] if args.country else sorted(WORLDPOP_PREFIX.keys())

    all_summaries = []
    for country in countries:
        summary = process_country(country, base_dir, output_dir)
        if summary:
            all_summaries.append(summary)

    if not all_summaries:
        print("\nNo results produced. Check that health CSVs have data.")
        return

    # Country-level summary
    df_country = pd.DataFrame(all_summaries)
    country_path = output_dir / "country_accessibility_summary.csv"
    df_country.to_csv(country_path, index=False)
    print(f"\nCountry summary → {country_path}")

    # Africa-level aggregation (population-weighted)
    finite = df_country.dropna(
        subset=["pwmtt_normal", "pwmtt_extreme", "total_population"]
    )
    if len(finite) > 0:
        w = finite["total_population"].values
        agg = {
            "n_countries": len(finite),
            "total_population": float(w.sum()),
            "pwmtt_normal_africa": float(np.average(finite["pwmtt_normal"], weights=w)),
            "pwmtt_extreme_africa": float(
                np.average(finite["pwmtt_extreme"], weights=w)
            ),
            "pwmtt_delta_africa": float(np.average(finite["pwmtt_delta"], weights=w)),
            "mean_gini_normal": float(np.average(finite["gini_normal"], weights=w)),
            "mean_gini_extreme": float(np.average(finite["gini_extreme"], weights=w)),
            "mean_delta_gini": float(np.average(finite["delta_gini"], weights=w)),
            "median_spearman_rho": float(finite["spearman_rho"].median()),
            "pct_countries_sig_rho": float(
                (finite["spearman_pval"] < 0.05).mean() * 100
            ),
            "mean_tail_gap_ratio": float(finite["tail_gap_ratio"].mean()),
        }
        pd.DataFrame([agg]).to_csv(
            output_dir / "africa_accessibility_summary.csv", index=False
        )
        print(f"\nAfrica-level summary:")
        print(
            f"  PWMTT: {agg['pwmtt_normal_africa']:.3f}h → {agg['pwmtt_extreme_africa']:.3f}h"
        )
        print(f"  Gini: {agg['mean_gini_normal']:.4f} → {agg['mean_gini_extreme']:.4f}")
        print(f"  Median Spearman ρ = {agg['median_spearman_rho']:.4f}")
        print(f"  Tail gap ratio = {agg['mean_tail_gap_ratio']:.2f}")
        print(f"  Countries with sig. ρ (p<0.05): {agg['pct_countries_sig_rho']:.0f}%")


if __name__ == "__main__":
    main()
