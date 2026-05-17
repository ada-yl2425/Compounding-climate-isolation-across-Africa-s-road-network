"""
run_africa_layer.py
===================
Pan-African road network OD matrix analysis (africa layer).

Logic Framework:
  1. Build each country's graph independently to save memory.
  2. Extract border nodes from each country graph.
  3. Connect adjacent countries via synthetic cross-border edges.
  4. Merge all country graphs into one pan-African graph.
  5. Snap key cities and run OD matrix analysis.
"""

import gc
import pickle
import time
import warnings
from collections import defaultdict
from pathlib import Path

import igraph as ig
import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

warnings.filterwarnings("ignore")

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_DIR = Path("path/to/your/base/directory")
ROADS_DIR = BASE_DIR / "RAW/Road_data"
SPEED_DIR = BASE_DIR / "road_speed_cordex"
NODES_CSV = BASE_DIR / "web/africa_layer/africa_nodes.csv"
OUTPUT_DIR = BASE_DIR / "web/network_results/africa_layer"
CHECKPOINT_PATH = OUTPUT_DIR / "graph_checkpoint.pkl"

MIN_ROAD_LENGTH_KM = 0.1
SNAP_THRESHOLD_DEG = 0.0045
BORDER_DEG = 0.5
CROSS_BORDER_DEG = 0.5
CROSS_BORDER_SPEED = 40.0
CROSS_BORDER_DIST_DEG = 0.20  # ~22 km — wider search fixes fragmented LCC
CITY_SNAP_MAX_DEG = 0.5
SEVERE_INCREASE_THR = 0.5
UNREACHABLE_THRESH = 1e8

FOLDER_TO_ISO = {
    "Algeria": "DZA",
    "Angola": "AGO",
    "Benin": "BEN",
    "Botswana": "BWA",
    "BurkinaFaso": "BFA",
    "Burundi": "BDI",
    "Cameroon": "CMR",
    "CentralAfrican": "CAF",
    "Chad": "TCD",
    "Congo": "COG",
    "CongoDR": "COD",
    "Djibouti": "DJI",
    "Egypt": "EGY",
    "Equatorial": "GNQ",
    "Eritrea": "ERI",
    "Ethiopia": "ETH",
    "Gabon": "GAB",
    "Gambia": "GMB",
    "Ghana": "GHA",
    "Guinea": "GIN",
    "GuineaBissau": "GNB",
    "IvoryCoast": "CIV",
    "Kenya": "KEN",
    "Lesotho": "LSO",
    "Liberia": "LBR",
    "Libya": "LBY",
    "Madagascar": "MDG",
    "Malawi": "MWI",
    "Mali": "MLI",
    "Mauritania": "MRT",
    "Morocco": "MAR",
    "Mozambique": "MOZ",
    "Namibia": "NAM",
    "Niger": "NER",
    "Nigeria": "NGA",
    "Rwanda": "RWA",
    "Senegal": "SEN",
    "SierraLeone": "SLE",
    "Somalia": "SOM",
    "SouthAfrica": "ZAF",
    "SouthSudan": "SSD",
    "Sudan": "SDN",
    "Swaziland": "SWZ",
    "Tanzania": "TZA",
    "Togo": "TGO",
    "Tunisia": "TUN",
    "Uganda": "UGA",
    "WestSahara": "ESH",
    "Zambia": "ZMB",
    "Zimbabwe": "ZWE",
}


# =============================================================================
# UNION-FIND (Within-country endpoint merge)
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
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

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
        node_coords[nid] = (pts_arr[members, 0].mean(), pts_arr[members, 1].mean())
        for m in members:
            node_id_of[m] = nid
        nid += 1

    return node_id_of, node_coords


# =============================================================================
# BUILD ONE COUNTRY GRAPH
# =============================================================================
def build_country_graph(country, node_offset):
    """
    Build G0/G1 for a single country.
    Returns (G0, G1, node_coords_global, border_nodes) or None on failure.
    """
    import geopandas as gpd

    shp_path = ROADS_DIR / country / f"{country}.shp"
    speed_path = SPEED_DIR / f"{country}_road_speed.csv"

    if not shp_path.exists() or not speed_path.exists():
        return None

    try:
        gdf = gpd.read_file(shp_path)
    except Exception as e:
        print(f"  [ERROR] {country}: {e}")
        return None

    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    if "length_km" not in gdf.columns:
        gdf_m = gdf.to_crs("ESRI:102022")
        gdf["length_km"] = gdf_m.geometry.length / 1000
    gdf = gdf[gdf["length_km"] >= MIN_ROAD_LENGTH_KM].reset_index(drop=True)
    if gdf.empty:
        return None
    if "road_id" not in gdf.columns:
        gdf["road_id"] = [f"{country}_road_{i}" for i in range(len(gdf))]

    try:
        df_sp = pd.read_csv(speed_path)
        if "year" in df_sp.columns:
            df_sp = df_sp.drop(columns=["year"])
        df_sp["V_normal"] = df_sp["V_normal"].clip(lower=0.01)
        df_sp["V_extreme"] = df_sp["V_extreme"].clip(lower=0.01)
        if "passable_rate_extreme" in df_sp.columns:
            df_sp["p_block"] = (1.0 - df_sp["passable_rate_extreme"].clip(0, 1)).clip(
                0, 0.99
            )
        elif "p_block" not in df_sp.columns:
            df_sp["p_block"] = (
                (df_sp["V_normal"] - df_sp["V_extreme"]) / df_sp["V_normal"]
            ).clip(0, 0.99)
        v_n_med = df_sp["V_normal"].median()
        speed_lu = df_sp.set_index("road_id")[
            ["V_normal", "V_extreme", "p_block"]
        ].to_dict("index")
    except Exception:
        v_n_med = 60.0
        speed_lu = {}

    coords_list = []
    road_ep_idx = []
    same_pairs = set()
    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            road_ep_idx.append(None)
            continue
        try:
            if geom.geom_type == "MultiLineString":
                sc = geom.geoms[0].coords[0]
                ec = geom.geoms[-1].coords[-1]
            elif geom.geom_type == "LineString":
                sc, ec = geom.coords[0], geom.coords[-1]
            else:
                road_ep_idx.append(None)
                continue
        except Exception:
            road_ep_idx.append(None)
            continue
        si = len(coords_list)
        coords_list.append((sc[0], sc[1]))
        ei = len(coords_list)
        coords_list.append((ec[0], ec[1]))
        road_ep_idx.append((si, ei))
        same_pairs.add((min(si, ei), max(si, ei)))

    if not coords_list:
        return None

    pts_arr = np.array(coords_list, dtype=np.float64)
    node_id_of, node_coords_local = _merge_endpoints(
        pts_arr, same_pairs, SNAP_THRESHOLD_DEG
    )

    node_coords_global = {
        nid + node_offset: coords for nid, coords in node_coords_local.items()
    }

    G0 = nx.Graph()
    G1 = nx.Graph()
    for nid, (lon, lat) in node_coords_global.items():
        G0.add_node(nid, lon=lon, lat=lat)
        G1.add_node(nid)

    for ridx in range(len(gdf)):
        ep = road_ep_idx[ridx]
        if ep is None:
            continue
        si, ei = ep
        u = node_id_of[si] + node_offset
        v = node_id_of[ei] + node_offset
        if u == v:
            continue
        row = gdf.iloc[ridx]
        road_id = row["road_id"]
        lkm = float(row["length_km"])
        if not lkm > 0:
            lkm = 1.0
        if road_id in speed_lu:
            d = speed_lu[road_id]
            V_n, V_e, pb = d["V_normal"], d["V_extreme"], d["p_block"]
        else:
            V_n, V_e, pb = v_n_med, v_n_med, 0.0
        w0 = lkm / V_n
        w1 = lkm / V_e / (1.0 - min(pb, 0.99))
        if G0.has_edge(u, v):
            if w0 < G0[u][v].get("weight", 1e9):
                G0[u][v]["weight"] = w0
                G1[u][v]["weight"] = w1
        else:
            G0.add_edge(u, v, weight=w0)
            G1.add_edge(u, v, weight=w1)

    lons = np.array([c[0] for c in node_coords_global.values()])
    lats = np.array([c[1] for c in node_coords_global.values()])
    lon_min, lon_max = lons.min(), lons.max()
    lat_min, lat_max = lats.min(), lats.max()
    border_nodes = []
    for nid, (lon, lat) in node_coords_global.items():
        if (
            lon - lon_min < BORDER_DEG
            or lon_max - lon < BORDER_DEG
            or lat - lat_min < BORDER_DEG
            or lat_max - lat < BORDER_DEG
        ):
            border_nodes.append((nid, lon, lat, country))

    del gdf, pts_arr, coords_list, same_pairs
    gc.collect()

    return G0, G1, node_coords_global, border_nodes


# =============================================================================
# BUILD PAN-AFRICAN GRAPH
# =============================================================================
def build_africa_graph(checkpoint_path: Path = CHECKPOINT_PATH, rebuild: bool = False):
    if not rebuild and checkpoint_path.exists():
        print(f"\n  [CHECKPOINT] Loading graph from {checkpoint_path.name} …")
        with open(checkpoint_path, "rb") as f:
            data = pickle.load(f)
        G0, G1, all_node_coords = data["G0"], data["G1"], data["all_nc"]
        print(f"  G0: {G0.number_of_nodes():,} nodes  {G0.number_of_edges():,} edges")
        return G0, G1, all_node_coords, all_node_coords

    print(f"\n{'=' * 60}\n  STEP 1 - Build Country Graphs\n{'=' * 60}")

    all_G0 = []
    all_G1 = []
    all_node_coords = {}
    all_border = []

    node_offset = 0
    countries_ok = []

    for i, country in enumerate(FOLDER_TO_ISO.keys()):
        result = build_country_graph(country, node_offset)
        if result is None:
            print(f"  [{i + 1:>2}/50] {country:<20} SKIP")
            continue
        G0, G1, nc, border = result
        all_G0.append(G0)
        all_G1.append(G1)
        all_node_coords.update(nc)
        all_border.extend(border)
        node_offset += len(nc)
        countries_ok.append(country)
        print(
            f"  [{len(countries_ok):>2}/50] {country:<20} Nodes={G0.number_of_nodes():,}  "
            f"Border Nodes={len(border):,}"
        )
        gc.collect()

    print(
        f"\n  Loaded: {len(countries_ok)} countries, "
        f"Total Nodes={len(all_node_coords):,}, Border Nodes={len(all_border):,}"
    )

    print(f"\n{'=' * 60}\n  STEP 2 - Merge Country Graphs\n{'=' * 60}")
    G0_pan = nx.Graph()
    G1_pan = nx.Graph()
    for G0, G1 in zip(all_G0, all_G1):
        G0_pan.add_nodes_from(G0.nodes(data=True))
        G0_pan.add_edges_from(G0.edges(data=True))
        G1_pan.add_nodes_from(G1.nodes(data=True))
        G1_pan.add_edges_from(G1.edges(data=True))
    del all_G0, all_G1
    gc.collect()
    print(
        f"  Merged: Nodes={G0_pan.number_of_nodes():,}  Edges={G0_pan.number_of_edges():,}"
    )

    print(f"\n{'=' * 60}\n  STEP 3 - Cross-Border Connection\n{'=' * 60}")
    border_arr = np.array([(lon, lat) for _, lon, lat, _ in all_border])
    border_nids = [nid for nid, _, _, _ in all_border]
    border_countries = [c for _, _, _, c in all_border]
    tree = cKDTree(border_arr)

    pairs = tree.query_pairs(CROSS_BORDER_DIST_DEG)
    n_cross = 0
    for i, j in pairs:
        if border_countries[i] == border_countries[j]:
            continue
        u, v = border_nids[i], border_nids[j]
        if G0_pan.has_edge(u, v):
            continue
        dist_km = (
            np.hypot(
                all_border[i][1] - all_border[j][1],
                all_border[i][2] - all_border[j][2],
            )
            * 111.0
        )
        w = dist_km / CROSS_BORDER_SPEED
        G0_pan.add_edge(u, v, weight=w)
        G1_pan.add_edge(u, v, weight=w)
        n_cross += 1

    print(f"  New cross-border edges: {n_cross:,}")

    comps = list(nx.connected_components(G0_pan))
    lcc = max(comps, key=len)
    ratio = len(lcc) / G0_pan.number_of_nodes()
    print(f"  Components: {len(comps):,}  LCC: {len(lcc):,} nodes ({ratio:.1%})")
    print(
        f"  [INFO] Routing uses full graph ({G0_pan.number_of_nodes():,} nodes); "
        f"disconnected city pairs will appear as 'both_unreachable'."
    )

    # Save checkpoint
    checkpoint_path = CHECKPOINT_PATH
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path, "wb") as f:
        pickle.dump(
            {"G0": G0_pan, "G1": G1_pan, "all_nc": all_node_coords},
            f,
            protocol=pickle.HIGHEST_PROTOCOL,
        )
    print(f"  Saved checkpoint → {checkpoint_path.name}")

    gc.collect()
    return G0_pan, G1_pan, all_node_coords, all_node_coords


# =============================================================================
# SNAP + OD ANALYSIS
# =============================================================================
def snap_cities(nodes_csv, all_node_coords):
    """
    Snap all 84 cities to their nearest road-network node.

    No LCC-membership check: cities in isolated components are still snapped
    and will naturally appear as 'both_unreachable' in the OD matrix.
    A city is only skipped if it lies more than CITY_SNAP_MAX_DEG from any node.
    """
    df = pd.read_csv(nodes_csv)
    net_nodes = list(all_node_coords.keys())
    net_xy = np.array([all_node_coords[n] for n in net_nodes])
    tree = cKDTree(net_xy)
    snapped, skipped = [], []
    for _, row in df.iterrows():
        dist, idx = tree.query([row["lon"], row["lat"]])
        if dist > CITY_SNAP_MAX_DEG:
            skipped.append(row["name"])
            continue
        snap_node = net_nodes[idx]
        snapped.append(
            {
                "city_name": row["name"],
                "level": row.get("type", ""),
                "lon": row["lon"],
                "lat": row["lat"],
                "snap_node": snap_node,
                "snap_dist_km": dist * 111,
            }
        )
    print(f"  Snapped: {len(snapped)} / {len(df)}  Skipped (too far): {len(skipped)}")
    if skipped:
        print(f"  Skipped cities: {skipped}")
    return snapped


def compute_od_analysis(G0, G1, snapped):
    print(f"\n{'=' * 60}\n  OD Analysis\n{'=' * 60}")
    if len(snapped) < 2:
        print("  [Skip] Valid cities < 2")
        return None, None, None, None, {}

    city_names = [s["city_name"] for s in snapped]
    snap_nodes = [s["snap_node"] for s in snapped]
    levels = [s["level"] for s in snapped]
    n = len(city_names)
    print(f"  Cities: {n}, Pairs: {n * (n - 1) // 2}")

    def dist_matrix(G, label):
        """Calculate shortest paths using igraph for performance."""
        t0 = time.time()
        node_list = list(G.nodes())
        node_idx = {n_id: i for i, n_id in enumerate(node_list)}
        edges_ig = [(node_idx[u], node_idx[v]) for u, v in G.edges()]
        weights_ig = [d["weight"] for _, _, d in G.edges(data=True)]
        g_ig = ig.Graph(n=len(node_list), edges=edges_ig)
        g_ig.es["weight"] = weights_ig

        city_ig = [node_idx[sn] for sn in snap_nodes if sn in node_idx]
        city_names_valid = [
            cn for cn, sn in zip(city_names, snap_nodes) if sn in node_idx
        ]
        snap_nodes_valid = [sn for sn in snap_nodes if sn in node_idx]

        dists_raw = g_ig.distances(source=city_ig, target=city_ig, weights="weight")

        mat = {}
        for i, cname in enumerate(city_names_valid):
            mat[cname] = {}
            for j, snode in enumerate(snap_nodes_valid):
                v = dists_raw[i][j]
                mat[cname][snode] = v if v != float("inf") else float("nan")

        print(f"    Shortest path ({label}): {time.time() - t0:.1f}s")
        return mat

    dist0 = dist_matrix(G0, "normal")
    dist1 = dist_matrix(G1, "extreme")

    INF = float("nan")
    mat_n = pd.DataFrame(index=city_names, columns=city_names, dtype=float)
    mat_e = pd.DataFrame(index=city_names, columns=city_names, dtype=float)
    for i, (cA, nA) in enumerate(zip(city_names, snap_nodes)):
        for j, (cB, nB) in enumerate(zip(city_names, snap_nodes)):
            if i == j:
                mat_n.loc[cA, cB] = mat_e.loc[cA, cB] = 0.0
            else:
                mat_n.loc[cA, cB] = dist0.get(cA, {}).get(nB, INF)
                mat_e.loc[cA, cB] = dist1.get(cA, {}).get(nB, INF)

    pair_rows = []
    for i in range(n):
        for j in range(i + 1, n):
            cA, cB = city_names[i], city_names[j]
            t0v = mat_n.loc[cA, cB]
            t1v = mat_e.loc[cA, cB]
            t0_ok = pd.notna(t0v) and t0v < UNREACHABLE_THRESH
            t1_ok = pd.notna(t1v) and t1v < UNREACHABLE_THRESH
            if not t0_ok and not t1_ok:
                conn_type = "both_unreachable"
            elif not t0_ok and t1_ok:
                conn_type = "normal_unreachable"
            elif t0_ok and not t1_ok:
                conn_type = "climate_disconnected"
            else:
                conn_type = "connected"
            inc = float("nan")
            if t0_ok and t1_ok and t0v > 0:
                inc = (t1v - t0v) / t0v * 100
            pair_rows.append(
                {
                    "city_A": cA,
                    "city_B": cB,
                    "level_A": levels[i],
                    "level_B": levels[j],
                    "t_normal_h": t0v if t0_ok else float("nan"),
                    "t_extreme_h": t1v if t1_ok else float("nan"),
                    "increase_pct": inc,
                    "conn_type": conn_type,
                    "severe_increase": int(
                        not np.isnan(inc) and inc >= SEVERE_INCREASE_THR * 100
                    ),
                }
            )

    od_pairs_df = pd.DataFrame(pair_rows)

    iso_rows = []
    for cname, level in zip(city_names, levels):
        op = od_pairs_df[
            (od_pairs_df["city_A"] == cname) | (od_pairs_df["city_B"] == cname)
        ]
        n_total = len(op)
        n_cdisc = (op["conn_type"] == "climate_disconnected").sum()
        n_both = (op["conn_type"] == "both_unreachable").sum()
        n_conn = (op["conn_type"] == "connected").sum()
        n_severe = op["severe_increase"].sum()
        cp = op[op["conn_type"] == "connected"]
        mean_inc = cp["increase_pct"].mean() if len(cp) > 0 else float("nan")
        max_inc = cp["increase_pct"].max() if len(cp) > 0 else float("nan")
        iso_rows.append(
            {
                "city_name": cname,
                "level": level,
                "n_city_pairs": n_total,
                "n_climate_disconnected": int(n_cdisc),
                "n_both_unreachable": int(n_both),
                "n_connected": int(n_conn),
                "n_severe_increase": int(n_severe),
                "disconnection_ratio": n_cdisc / n_total if n_total > 0 else 0.0,
                "mean_travel_increase_pct": mean_inc,
                "max_travel_increase_pct": max_inc,
            }
        )

    city_iso_df = (
        pd.DataFrame(iso_rows)
        .sort_values(
            ["disconnection_ratio", "mean_travel_increase_pct"],
            ascending=[False, False],
        )
        .reset_index(drop=True)
    )

    connected = od_pairs_df[od_pairs_df["conn_type"] == "connected"]
    climate_disc = od_pairs_df[od_pairs_df["conn_type"] == "climate_disconnected"]
    both_unr = od_pairs_df[od_pairs_df["conn_type"] == "both_unreachable"]
    n_total_p = len(od_pairs_df)

    summary = {
        "layer": "africa",
        "n_cities": n,
        "n_city_pairs": n_total_p,
        "n_connected": (od_pairs_df["conn_type"] == "connected").sum(),
        "n_climate_disconnected": len(climate_disc),
        "n_both_unreachable": len(both_unr),
        "climate_disconn_ratio": (
            len(climate_disc) / n_total_p if n_total_p > 0 else float("nan")
        ),
        "both_unreachable_ratio": (
            len(both_unr) / n_total_p if n_total_p > 0 else float("nan")
        ),
        "mean_travel_increase_pct": connected["increase_pct"].mean(),
        "median_travel_increase_pct": connected["increase_pct"].median(),
        "p75_travel_increase_pct": connected["increase_pct"].quantile(0.75),
        "pct_severe_increase": od_pairs_df["severe_increase"].mean() * 100,
        "n_severe_increase": od_pairs_df["severe_increase"].sum(),
    }

    print(f"\n  Total pairs: {n_total_p}")
    print(f"  Connected pairs: {summary['n_connected']}")
    print(
        f"  Climate disconnected: {summary['n_climate_disconnected']} "
        f"({summary['climate_disconn_ratio'] * 100:.1f}%)"
    )
    print(
        f"  Structurally unreachable: {summary['n_both_unreachable']} "
        f"({summary['both_unreachable_ratio'] * 100:.1f}%)"
    )
    print(f"  Avg travel time increase: {summary['mean_travel_increase_pct']:.2f}%")
    print(
        f"  Severely degraded (>50%): {summary['n_severe_increase']} "
        f"({summary['pct_severe_increase']:.1f}%)"
    )

    print(f"\n  Top 10 highest isolation risk cities:")
    for _, r in city_iso_df.head(10).iterrows():
        print(
            f"    {r['city_name']:<25} Disconn={r['n_climate_disconnected']:>3}  "
            f"Unreachable={r['n_both_unreachable']:>3}  "
            f"Avg Increase={r['mean_travel_increase_pct']:.1f}%  type={r['level']}"
        )

    return od_pairs_df, city_iso_df, mat_n, mat_e, summary


# =============================================================================
# MAIN
# =============================================================================
def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default=None, help="Override BASE_DIR path")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Ignore cached checkpoint and rebuild graph from scratch",
    )
    args = parser.parse_args()

    global BASE_DIR, ROADS_DIR, SPEED_DIR, NODES_CSV, OUTPUT_DIR, CHECKPOINT_PATH
    if args.base_dir:
        BASE_DIR = Path(args.base_dir)
        ROADS_DIR = BASE_DIR / "RAW/Road_data"
        SPEED_DIR = BASE_DIR / "road_speed_cordex"
        NODES_CSV = BASE_DIR / "web/africa_layer/africa_nodes.csv"
        OUTPUT_DIR = BASE_DIR / "web/network_results/africa_layer"
        CHECKPOINT_PATH = OUTPUT_DIR / "graph_checkpoint.pkl"

    t_total = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"  Africa Layer - Graph Building, Splicing & OD Analysis")
    print(f"{'=' * 60}")

    G0, G1, node_coords, all_node_coords = build_africa_graph(rebuild=args.rebuild)

    print(f"\n{'=' * 60}\n  STEP 4 - City Snap\n{'=' * 60}")
    snapped = snap_cities(NODES_CSV, all_node_coords)
    del all_node_coords
    gc.collect()

    if len(snapped) < 2:
        print("Not enough valid cities. Exiting.")
        return

    od_pairs_df, city_iso_df, mat_n, mat_e, summary = compute_od_analysis(
        G0, G1, snapped
    )

    summary["runtime_s"] = time.time() - t_total

    if od_pairs_df is not None:
        od_pairs_df.to_csv(OUTPUT_DIR / "africa_od_pairs.csv", index=False)
        city_iso_df.to_csv(OUTPUT_DIR / "africa_city_isolation.csv", index=False)
        mat_n.to_csv(OUTPUT_DIR / "africa_od_matrix_normal.csv")
        mat_e.to_csv(OUTPUT_DIR / "africa_od_matrix_extreme.csv")
        pd.DataFrame([summary]).to_csv(
            OUTPUT_DIR / "africa_od_summary.csv", index=False
        )
        print(f"\n  Output directory: {OUTPUT_DIR}")
        print(f"  Total time: {summary['runtime_s'] / 60:.1f} minutes")


if __name__ == "__main__":
    main()
