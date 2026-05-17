"""
network_buffering_decomposition.py
===================================
Sub-argument 2 — Network Redundancy Mechanism

Decomposes each node's climate-induced travel-time increase into:

  direct_degradation
      Travel-time increase along the G0-optimal path at G1 road speeds,
      assuming no rerouting is possible (counterfactual: "what if you were
      locked onto your normal route when conditions deteriorate?").

  network_buffering_ratio
      Fraction of direct_degradation that the network absorbs by allowing
      rerouting onto alternative paths under extreme conditions:

          buffering = 1 − (actual Δt) / direct_degradation

          buffering ≈ 1 → network absorbed almost all local degradation
          buffering ≈ 0 → no alternatives; node exposed to full degradation

The test:
    If P90 populations have significantly lower buffering than P50 populations,
    the inequality documented in Result 2 is produced by the unequal
    distribution of network redundancy, not just by local road conditions.

Method (predecessor-tree approach):
    For each country:
      1. Rebuild G0 and G1 (same logic as compute_health_accessibility.py).
      2. Add a super-source connected to all health nodes with weight=0.
      3. Run nx.dijkstra_predecessor_and_distance on the augmented G0 graph
         to obtain the G0 shortest-path tree (predecessor map + distances).
      4. Walk the predecessor tree in topological order to compute each
         node's G0-path cost under G1 edge weights (O(N) tree traversal).
      5. direct_degradation = G0-path cost in G1 − t_normal
      6. buffering_ratio = 1 − actual_delta / direct_degradation

Inputs (same as compute_health_accessibility.py):
    <BASE_DIR>/RAW/Road_data/{country}/{country}.shp
    <BASE_DIR>/road_speed_cordex/{country}_road_speed.csv
    <BASE_DIR>/RAW/Health_data/{country}_health.csv
    <BASE_DIR>/web/health_accessibility/node_accessibility_{country}.csv
        (used for pre-computed population weights; avoids re-running raster snap)

Outputs → <BASE_DIR>/web/network_results/buffering_decomposition/
    country_buffering_stats.csv     per-country buffering summary
    node_buffering_{country}.csv    per-node decomposition detail

Usage:
    python result2/network_buffering_decomposition.py --base <BASE_DIR>
    python result2/network_buffering_decomposition.py --base <BASE_DIR> --country Kenya
    python result2/network_buffering_decomposition.py --base <BASE_DIR> --no-node-output
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

warnings.filterwarnings("ignore")

# =============================================================================
# CONFIGURATION  (mirrors compute_health_accessibility.py)
# =============================================================================
BASE_DIR_DEFAULT = Path("path/to/base")

SNAP_THRESHOLD_DEG = 0.0045
MIN_ROAD_LENGTH_KM = 0.1
UNREACHABLE_H = 1e6
MAX_HEALTH_SNAP_KM = 50.0

SUPER_SRC = "__super__"

# Percentile windows for grouping nodes
P50_LO, P50_HI = 0.40, 0.60  # 40th–60th percentile of baseline travel time
P90_LO = 0.80  # 80th–100th percentile

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
    "WestSahara": "",
    "Zambia": "zmb",
    "Zimbabwe": "zwe",
}


# =============================================================================
# GRAPH BUILDING  (copied from compute_health_accessibility.py)
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


def load_health_facilities(health_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(health_csv)
    df = df.dropna(subset=["lon", "lat"])
    df["lon"] = df["lon"].astype(float)
    df["lat"] = df["lat"].astype(float)
    return df


def snap_health_to_network(health_df: pd.DataFrame, node_coords: dict) -> list:
    if health_df.empty:
        return []
    net_nodes = list(node_coords.keys())
    net_xy = np.array([node_coords[n] for n in net_nodes])
    tree = cKDTree(net_xy)
    health_xy = health_df[["lon", "lat"]].values
    dists, idxs = tree.query(health_xy)
    snapped = []
    for dist_deg, idx in zip(dists, idxs):
        if dist_deg * 111.0 <= MAX_HEALTH_SNAP_KM:
            snapped.append(net_nodes[idx])
    return list(set(snapped))


# =============================================================================
# CORE: PREDECESSOR-TREE BUFFERING DECOMPOSITION
# =============================================================================
def compute_direct_degradation(
    G0: nx.Graph,
    G1: nx.Graph,
    health_nodes: list,
) -> dict:
    """
    Compute the G1-cost of each node's G0-optimal path (no rerouting allowed).

    Steps:
      1. Add a zero-weight super-source connected to all health nodes.
      2. Run nx.dijkstra_predecessor_and_distance on augmented G0 to get the
         shortest-path tree (predecessor map + distances in G0 time units).
      3. Walk the predecessor tree in ascending-distance order so that every
         parent is processed before its children.  For each node accumulate the
         G1 edge weights along its G0-optimal path.
      4. direct_degradation = G1-path-cost − G0-path-cost  (≥ 0 by construction,
         since G1 edge weights ≥ G0 edge weights).

    Returns:
        dict mapping node_id → {t_normal_path, t_g1_forced_path, direct_degradation}
    """
    # Augmented G0 with super-source
    H0 = G0.copy()
    H0.add_node(SUPER_SRC)
    for h in health_nodes:
        if h in H0:
            H0.add_edge(SUPER_SRC, h, weight=0.0)

    # Dijkstra with predecessor tracking from super-source
    pred, dist = nx.dijkstra_predecessor_and_distance(H0, SUPER_SRC, weight="weight")

    # Walk tree in topological order (ascending distance = guaranteed parent-before-child)
    nodes_sorted = sorted(dist.items(), key=lambda x: x[1])

    # dp[node] = cost of G0-optimal path traversed with G1 edge weights
    dp = {}
    for node, _ in nodes_sorted:
        if node is SUPER_SRC or node == SUPER_SRC:
            dp[node] = 0.0
            continue
        par_list = pred.get(node, [])
        if not par_list:
            dp[node] = float("inf")
            continue
        par = par_list[0]  # pick one predecessor (tie-break: first found)
        if par == SUPER_SRC:
            # Node is a health facility — zero road cost to itself
            dp[node] = 0.0
        elif G1.has_edge(par, node):
            dp[node] = dp.get(par, float("inf")) + G1[par][node]["weight"]
        else:
            # Edge exists in G0 but not G1 (shouldn't happen; fallback to inf)
            dp[node] = float("inf")

    result = {}
    for node in G0.nodes():
        t_n = dist.get(node, float("inf"))
        t_g1_forced = dp.get(node, float("inf"))
        dd = max(0.0, t_g1_forced - t_n)
        result[node] = {
            "t_normal_path": t_n,
            "t_g1_forced_path": t_g1_forced,
            "direct_degradation": dd,
        }
    return result


# =============================================================================
# BUFFERING RATIO AND PERCENTILE GROUPING
# =============================================================================
def build_node_dataframe(
    decomp: dict,
    node_list: list,
    t_extreme_map: dict,
    pop_arr: np.ndarray,
) -> pd.DataFrame:
    """
    Combine decomposition results with actual extreme-condition travel times
    and population weights.  Computes buffering_ratio per node.

    buffering_ratio ∈ [0, 1]:
        1 → rerouting absorbed all direct degradation (no impact on traveller)
        0 → no alternative routes; traveller exposed to full local degradation
    """
    rows = []
    for i, node in enumerate(node_list):
        info = decomp.get(node, {})
        t_n = info.get("t_normal_path", float("inf"))
        dd = info.get("direct_degradation", 0.0)
        t_e = t_extreme_map.get(node, float("inf"))
        delta_t = (
            max(0.0, t_e - t_n)
            if np.isfinite(t_e) and np.isfinite(t_n)
            else float("inf")
        )
        pop = float(pop_arr[i])

        if dd > 0 and np.isfinite(delta_t):
            buf = 1.0 - delta_t / dd
            buf = float(np.clip(buf, 0.0, 1.0))
        elif dd == 0.0:
            # No degradation on G0 path → buffering is trivially 1
            buf = 1.0 if delta_t == 0 else 0.0
        else:
            buf = float("nan")

        rows.append(
            {
                "node_id": node,
                "t_normal": t_n,
                "t_extreme": t_e,
                "direct_degradation": dd,
                "actual_delta": delta_t,
                "buffering_ratio": buf,
                "population": pop,
            }
        )

    return pd.DataFrame(rows)


def assign_percentile_groups(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign population-weighted percentile groups based on baseline travel time.

    Only nodes that are:
      - finite and reachable (t_normal < UNREACHABLE_H)
      - have population > 0
      - have a valid buffering_ratio
    are included.

    Groups:
      "p50": nodes whose t_normal falls in the P40–P60 window of the
             population-weighted cumulative distribution.
      "p90": nodes above the P80 threshold.
    """
    valid = df[
        np.isfinite(df["t_normal"])
        & (df["t_normal"] < UNREACHABLE_H)
        & (df["population"] > 0)
        & np.isfinite(df["buffering_ratio"])
    ].copy()

    if len(valid) < 20:
        valid["pct_group"] = np.nan
        return valid

    valid_sorted = valid.sort_values("t_normal").reset_index(drop=True)
    total_pop = valid_sorted["population"].sum()
    cum_frac = np.cumsum(valid_sorted["population"].values) / total_pop

    groups = []
    for frac in cum_frac:
        if P50_LO <= frac <= P50_HI:
            groups.append("p50")
        elif frac > P90_LO:
            groups.append("p90")
        else:
            groups.append("other")

    valid_sorted["pct_group"] = groups
    return valid_sorted


def buffering_stats_from_groups(df_grouped: pd.DataFrame) -> dict:
    """
    Compute buffering statistics for p50 and p90 baseline-travel-time groups.

    Primary metric: population-weighted mean buffering ratio.
    Secondary metrics:
      - frac_positive_buffering: fraction of (weighted) population with buffering > 1%
        (addresses the zero-inflation problem in tree-like networks)
      - mean_dd_intensity: mean direct_degradation / t_normal per group
        (tests whether local road conditions differ between groups)
      - mean_actual_intensity: mean actual_delta / t_normal per group
        (total exposure per unit of travel time)
    """
    stats = {}
    for grp in ("p50", "p90"):
        sub = df_grouped[df_grouped["pct_group"] == grp].copy()
        if len(sub) == 0:
            for key in (
                "pwmean_buffering",
                "mean_buffering",
                "frac_positive_buffering",
                "mean_dd_intensity",
                "mean_actual_intensity",
                "mean_direct_degradation_h",
                "mean_actual_delta_h",
                "mean_degree",
                "n_nodes",
            ):
                stats[f"{key}_{grp}"] = np.nan
            continue

        total_pop = sub["population"].sum()
        w = (
            sub["population"].values / total_pop
            if total_pop > 0
            else np.ones(len(sub)) / len(sub)
        )

        buf = sub["buffering_ratio"].values
        stats[f"pwmean_buffering_{grp}"] = float(np.sum(w * buf))
        stats[f"mean_buffering_{grp}"] = float(buf.mean())

        # Fraction of nodes facing non-zero direct degradation that absorb some of it
        dd_vals = sub["direct_degradation"].values
        sub_facing_dd = buf[dd_vals > 0]
        stats[f"frac_positive_buffering_{grp}"] = (
            float((sub_facing_dd > 0.01).mean()) if len(sub_facing_dd) > 0 else np.nan
        )

        # Local road-condition vulnerability (direct degradation per travel hour)
        dd = sub["direct_degradation"].values
        tn = sub["t_normal"].values
        valid_dn = tn > 0
        if valid_dn.sum() > 0:
            stats[f"mean_dd_intensity_{grp}"] = float(
                np.sum(w[valid_dn] * (dd[valid_dn] / tn[valid_dn])) / w[valid_dn].sum()
            )
        else:
            stats[f"mean_dd_intensity_{grp}"] = np.nan

        # Actual climate impact per travel hour
        ad = sub["actual_delta"].values
        if valid_dn.sum() > 0:
            stats[f"mean_actual_intensity_{grp}"] = float(
                np.sum(w[valid_dn] * (ad[valid_dn] / tn[valid_dn])) / w[valid_dn].sum()
            )
        else:
            stats[f"mean_actual_intensity_{grp}"] = np.nan

        stats[f"mean_direct_degradation_h_{grp}"] = float(np.sum(w * dd))
        stats[f"mean_actual_delta_h_{grp}"] = float(np.sum(w * ad))

        if "degree" in sub.columns:
            stats[f"mean_degree_{grp}"] = float(np.sum(w * sub["degree"].values))
        else:
            stats[f"mean_degree_{grp}"] = np.nan

        stats[f"n_nodes_{grp}"] = len(sub)

    # Cross-group comparisons
    mb50 = stats["pwmean_buffering_p50"]
    mb90 = stats["pwmean_buffering_p90"]
    if np.isfinite(mb50) and np.isfinite(mb90) and mb90 > 0:
        stats["buffering_ratio_p50_over_p90"] = mb50 / mb90
    elif np.isfinite(mb50) and np.isfinite(mb90) and mb90 == 0.0 and mb50 > 0:
        stats["buffering_ratio_p50_over_p90"] = float("inf")
    else:
        stats["buffering_ratio_p50_over_p90"] = np.nan

    return stats


# =============================================================================
# PER-COUNTRY PIPELINE
# =============================================================================
def process_country(
    country: str,
    base_dir: Path,
    output_dir: Path,
    write_node_output: bool = True,
) -> dict | None:
    shp_path = base_dir / "RAW/Road_data" / country / f"{country}.shp"
    iri_path = base_dir / "road_speed_cordex" / f"{country}_road_speed.csv"
    hlth_path = base_dir / "RAW/Health_data" / f"{country}_health.csv"
    node_acc_path = (
        base_dir / "web/health_accessibility" / f"node_accessibility_{country}.csv"
    )

    missing = [p for p in [shp_path, iri_path, hlth_path] if not p.exists()]
    if missing:
        print(f"  [SKIP] {country}: missing files: {[str(m) for m in missing]}")
        return None
    if not node_acc_path.exists():
        print(
            f"  [SKIP] {country}: node_accessibility CSV not found — run compute_health_accessibility.py first"
        )
        return None

    health_df = load_health_facilities(hlth_path)
    if health_df.empty:
        print(f"  [SKIP] {country}: no health facility data")
        return None

    print(f"\n{'='*60}\n  {country}  ({len(health_df)} health facilities)\n{'='*60}")
    t_start = time.time()

    # --- Build graphs ---
    print("  [1/4] Building road network graphs ...")
    G0, G1, node_coords = build_graphs(shp_path, iri_path)

    lcc_nodes = max(nx.connected_components(G0), key=len)
    G0 = G0.subgraph(lcc_nodes).copy()
    G1 = G1.subgraph(lcc_nodes).copy()
    node_coords = {k: v for k, v in node_coords.items() if k in lcc_nodes}
    node_list = list(node_coords.keys())

    health_nodes = snap_health_to_network(health_df, node_coords)
    if not health_nodes:
        print(
            f"  [SKIP] {country}: no health facilities within {MAX_HEALTH_SNAP_KM} km"
        )
        return None
    print(f"  {len(health_nodes)} unique health-facility anchor nodes")

    # --- Predecessor-tree decomposition ---
    print("  [2/4] Computing G0 predecessor tree and G1 forced-path costs ...")
    decomp = compute_direct_degradation(G0, G1, health_nodes)

    # --- Load t_extreme from node_accessibility CSV (already computed) ---
    print("  [3/4] Loading pre-computed extreme travel times and population ...")
    node_acc = pd.read_csv(node_acc_path)
    t_extreme_map = dict(zip(node_acc["node_id"], node_acc["t_extreme"]))
    pop_series = node_acc.set_index("node_id")["population"]
    pop_arr = np.array([pop_series.get(n, 0.0) for n in node_list])

    # --- Build per-node DataFrame and assign percentile groups ---
    print("  [4/4] Computing buffering ratios and percentile groups ...")
    node_df = build_node_dataframe(decomp, node_list, t_extreme_map, pop_arr)
    node_df["country"] = country

    # Add node degree (proxy for topological redundancy)
    degree_map = dict(G0.degree())
    node_df["degree"] = node_df["node_id"].map(degree_map).fillna(0).astype(int)

    node_df_grouped = assign_percentile_groups(node_df)

    buf_stats = buffering_stats_from_groups(node_df_grouped)

    n_valid = int(
        (np.isfinite(node_df["buffering_ratio"]) & (node_df["population"] > 0)).sum()
    )
    valid_nodes = node_df[
        (node_df["population"] > 0)
        & np.isfinite(node_df["buffering_ratio"])
        & np.isfinite(node_df["t_normal"])
        & (node_df["t_normal"] < UNREACHABLE_H)
    ]
    pop_wt = valid_nodes["population"] / valid_nodes["population"].sum()
    mean_buf_all = float(np.sum(pop_wt * valid_nodes["buffering_ratio"]))

    summary = {
        "country": country,
        "n_nodes_lcc": len(node_list),
        "n_health_anchors": len(health_nodes),
        "n_valid_nodes": n_valid,
        "pwmean_buffering_all": mean_buf_all,
        **buf_stats,
        "runtime_s": round(time.time() - t_start, 1),
    }

    mb50 = buf_stats.get("pwmean_buffering_p50", float("nan"))
    mb90 = buf_stats.get("pwmean_buffering_p90", float("nan"))
    ratio = buf_stats.get("buffering_ratio_p50_over_p90", float("nan"))
    print(
        f"  Pop-wt mean buffering: P50 = {mb50*100:.1f}%  P90 = {mb90*100:.1f}%  "
        f"P50/P90 ratio = {ratio:.2f}"
    )
    print(
        f"  DD intensity: P50 = {buf_stats.get('mean_dd_intensity_p50', float('nan')):.4f}  "
        f"P90 = {buf_stats.get('mean_dd_intensity_p90', float('nan')):.4f}"
    )
    print(
        f"  Mean degree: P50 = {buf_stats.get('mean_degree_p50', float('nan')):.2f}  "
        f"P90 = {buf_stats.get('mean_degree_p90', float('nan')):.2f}"
    )

    if write_node_output:
        node_out = output_dir / f"node_buffering_{country}.csv"
        node_df[
            [
                "country",
                "node_id",
                "t_normal",
                "t_extreme",
                "direct_degradation",
                "actual_delta",
                "buffering_ratio",
                "degree",
                "population",
            ]
        ].to_csv(node_out, index=False)
        print(f"  Node output → {node_out.name}")

    gc.collect()
    return summary


# =============================================================================
# CONTINENT-LEVEL AGGREGATION
# =============================================================================
def aggregate_continent(df: pd.DataFrame) -> dict:
    """Country-level aggregate of buffering statistics across all countries."""
    valid = df.dropna(subset=["pwmean_buffering_p50", "pwmean_buffering_p90"]).copy()
    n = len(valid)

    p50_exceeds = valid["pwmean_buffering_p50"] > valid["pwmean_buffering_p90"]
    p50_exceeds_2x = valid["buffering_ratio_p50_over_p90"].fillna(0) >= 2.0

    # Test whether dd_intensity differs: if similar, network is the mechanism
    dd_ratio = valid["mean_dd_intensity_p90"] / valid["mean_dd_intensity_p50"]

    return {
        "n_countries": n,
        # Primary: population-weighted mean buffering by group
        "continent_median_pwmean_buffering_p50": float(
            valid["pwmean_buffering_p50"].median()
        ),
        "continent_median_pwmean_buffering_p90": float(
            valid["pwmean_buffering_p90"].median()
        ),
        "continent_mean_pwmean_buffering_p50": float(
            valid["pwmean_buffering_p50"].mean()
        ),
        "continent_mean_pwmean_buffering_p90": float(
            valid["pwmean_buffering_p90"].mean()
        ),
        # Cross-country counts
        "n_countries_p50_exceeds_p90": int(p50_exceeds.sum()),
        "pct_countries_p50_exceeds_p90": float(p50_exceeds.mean() * 100),
        "n_countries_p50_gt2x_p90": int(p50_exceeds_2x.sum()),
        "pct_countries_p50_gt2x_p90": float(p50_exceeds_2x.mean() * 100),
        "median_p50_over_p90_ratio": float(
            valid["buffering_ratio_p50_over_p90"].median()
        ),
        # DD intensity comparison (do local road conditions differ?)
        "continent_median_dd_intensity_p50": float(
            valid["mean_dd_intensity_p50"].median()
        ),
        "continent_median_dd_intensity_p90": float(
            valid["mean_dd_intensity_p90"].median()
        ),
        "median_dd_ratio_p90_over_p50": float(dd_ratio.median()),
        # Degree comparison (structural network evidence)
        "continent_mean_degree_p50": float(valid["mean_degree_p50"].mean()),
        "continent_mean_degree_p90": float(valid["mean_degree_p90"].mean()),
        # Fraction with positive buffering (addresses zero-inflation)
        "continent_mean_frac_positive_p50": float(
            valid["frac_positive_buffering_p50"].mean()
        ),
        "continent_mean_frac_positive_p90": float(
            valid["frac_positive_buffering_p90"].mean()
        ),
    }


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Decompose climate travel-time increase into direct degradation and network buffering"
    )
    parser.add_argument(
        "--base", required=True, help="Path to africa_pavement directory"
    )
    parser.add_argument("--country", default=None, help="Process only this country")
    parser.add_argument(
        "--no-node-output",
        action="store_true",
        help="Skip writing per-node CSV files (faster, less disk)",
    )
    args = parser.parse_args()

    base = Path(args.base)
    out_dir = base / "web/network_results/buffering_decomposition"
    out_dir.mkdir(parents=True, exist_ok=True)

    countries = [args.country] if args.country else sorted(WORLDPOP_PREFIX.keys())

    print(f"\n{'='*60}")
    print("  Network Buffering Decomposition")
    print(f"  Base: {base}")
    print(f"  Countries: {len(countries)}")
    print(f"{'='*60}")

    all_summaries = []
    for country in countries:
        summary = process_country(
            country,
            base,
            out_dir,
            write_node_output=not args.no_node_output,
        )
        if summary:
            all_summaries.append(summary)

    if not all_summaries:
        print("\nNo results. Check inputs.")
        return

    df = pd.DataFrame(all_summaries)
    country_path = out_dir / "country_buffering_stats.csv"
    df.to_csv(country_path, index=False)
    print(f"\nCountry summary → {country_path}")

    agg = aggregate_continent(df)
    pd.DataFrame([agg]).to_csv(out_dir / "continent_buffering_summary.csv", index=False)

    print(f"\n{'='*60}")
    print("  Continent-level results:")
    print(f"{'='*60}")
    print(f"  Countries processed                       : {agg['n_countries']}")
    print(
        f"  Median pop-wt buffering — P50 group       : {agg['continent_median_pwmean_buffering_p50']*100:.1f}%"
    )
    print(
        f"  Median pop-wt buffering — P90 group       : {agg['continent_median_pwmean_buffering_p90']*100:.1f}%"
    )
    print(
        f"  Countries where P50 buffering > P90       : {agg['n_countries_p50_exceeds_p90']} / {agg['n_countries']}"
    )
    print(
        f"  Countries where P50 ≥ 2× P90             : {agg['n_countries_p50_gt2x_p90']} / {agg['n_countries']}"
    )
    print(
        f"  Median P50/P90 buffering ratio            : {agg['median_p50_over_p90_ratio']:.2f}×"
    )
    print(
        f"  Median DD intensity P50 / P90             : {agg['continent_median_dd_intensity_p50']:.4f} / {agg['continent_median_dd_intensity_p90']:.4f}"
    )
    print(
        f"  Median DD intensity ratio (P90/P50)       : {agg['median_dd_ratio_p90_over_p50']:.2f}×"
    )
    print(
        f"  Mean degree P50 / P90                     : {agg['continent_mean_degree_p50']:.2f} / {agg['continent_mean_degree_p90']:.2f}"
    )
    print(
        f"  Frac with positive buffering P50 / P90    : {agg['continent_mean_frac_positive_p50']*100:.1f}% / {agg['continent_mean_frac_positive_p90']*100:.1f}%"
    )
    print(f"\n  Outputs in: {out_dir}")


if __name__ == "__main__":
    main()
