"""
network_pipeline.py
=======================
Africa Road Network Climate Impact - End-to-End Network Analysis Pipeline v7

Logic Framework:
  - city layer: Evaluates structural vulnerability (bridges, low redundancy).
  - country/africa layer: Evaluates functional consequences. Focuses solely on
    OD matrix analysis to derive functional accessibility metrics (disconnection,
    travel time increase, isolation risk).
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
import scipy.sparse as sp
from scipy.sparse.csgraph import shortest_path as sp_shortest
from scipy.spatial import cKDTree

warnings.filterwarnings("ignore")

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_DIR = Path("path/to/your/base/directory")
ROADS_DIR = BASE_DIR / "RAW/Road_data"
SPEED_DIR = BASE_DIR / "road_speed_cordex"
OUTPUT_ROOT = BASE_DIR / "web/network_results"

SNAP_THRESHOLD_DEG = 0.0045
MIN_ROAD_LENGTH_KM = 0.1
BLOCK_PROB_THRESH = 0.5
EFFICIENCY_SAMPLE = 300
DIAMETER_SAMPLE = 150
BETWEENNESS_K = 300
PERCOLATION_STEPS = 50
PERC_E_STEPS = 51
PERC_E_SAMPLE = 200

SEVERE_INCREASE_THRESH = 0.5
UNREACHABLE_THRESH = 1e8


# =============================================================================
# UTILITIES
# =============================================================================
class _Timer:
    def __init__(self, label):
        self.label = label

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, *_):
        print(f"    ⏱  {self.label}: {time.time() - self.t0:.2f}s")


def T(label):
    return _Timer(label)


def fmt(x):
    return f"{x:.4f}" if x is not None and not np.isnan(x) else "N/A"


# =============================================================================
# UNION-FIND FOR ENDPOINT MERGING
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
        a_root, b_root = find(a), find(b)
        if a_root != b_root:
            parent[b_root] = a_root

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
# STEP 0: GRAPH BUILDING (Shared across city/country/africa layers)
# =============================================================================
def build_graphs_from_shp(shp_path, iri_path, surface_filter="unpaved"):
    print(f"\n{'=' * 60}\n  STEP 0 - Graph Building\n{'=' * 60}")
    import geopandas as gpd

    with T("Read shapefile"):
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
    if surf_col and surface_filter:
        gdf = gdf[
            gdf[surf_col].str.lower().str.contains(surface_filter, na=False)
        ].copy()
    gdf = gdf[gdf["length_km"] >= MIN_ROAD_LENGTH_KM].reset_index(drop=True)

    stem = Path(shp_path).stem
    if "road_id" not in gdf.columns:
        gdf["road_id"] = [f"{stem}_road_{i}" for i in range(len(gdf))]
    print(f"  Filtered segments: {len(gdf):,}")

    df_iri = pd.read_csv(iri_path)
    if "year" in df_iri.columns:
        df_iri = df_iri.drop(columns=["year"], errors="ignore")
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

    needed = ["road_id", "V_normal", "V_extreme", "p_block"]
    if "delta_V_pct" in df_iri.columns:
        needed.append("delta_V_pct")
    iri_lu = df_iri[needed].set_index("road_id").to_dict("index")

    v_n_med = df_iri["V_normal"].median()
    v_e_med = v_n_med  # paved roads (not in speed CSV): no climate impact
    print(
        f"  Speed CSV: {len(df_iri):,} rows | Fill: V_n={v_n_med:.1f} V_e={v_e_med:.1f} (paved, climate-neutral)"
    )

    with T("Endpoint extraction (vectorized)"):
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

    pts_arr = np.array(coords_list, dtype=np.float64)

    with T("Endpoint merging (Union-Find)"):
        node_id_of, node_coords = _merge_endpoints(
            pts_arr, same_pairs, SNAP_THRESHOLD_DEG
        )

    compression_ratio = len(coords_list) / len(node_coords)
    print(f"  Nodes: {len(node_coords):,} (Compression ratio {compression_ratio:.1f}x)")

    G0 = nx.Graph()
    G1 = nx.Graph()
    G_conn = nx.Graph()
    for nid, (lon, lat) in node_coords.items():
        G0.add_node(nid, lon=lon, lat=lat)
        G1.add_node(nid)
        G_conn.add_node(nid)

    ea = []
    n_match = 0
    n_fill = 0
    n_skip = 0

    with T("Graph Construction"):
        for ridx in range(len(gdf)):
            ep = road_ep_idx[ridx]
            if ep is None:
                n_skip += 1
                continue
            si, ei = ep
            u, v = node_id_of[si], node_id_of[ei]
            if u == v:
                n_skip += 1
                continue

            row = gdf.iloc[ridx]
            road_id = row["road_id"]
            lkm = float(row.get("length_km", 1.0))
            if not lkm > 0:
                lkm = 1.0

            if road_id in iri_lu:
                d = iri_lu[road_id]
                V_n = d["V_normal"]
                V_e = d["V_extreme"]
                pb = d["p_block"]
                dv = abs(d.get("delta_V_pct", 0) or 0)
                n_match += 1
            else:
                V_n = v_n_med
                V_e = v_e_med
                pb = 0.0
                dv = 0.0
                n_fill += 1

            w0 = lkm / V_n
            w1 = lkm / V_e / (1.0 - min(pb, 0.99))

            if G0.has_edge(u, v):
                if w0 < G0[u][v].get("weight", 1e9):
                    G0[u][v].update(weight=w0, road_id=road_id)
                    G1[u][v]["weight"] = w1
            else:
                G0.add_edge(u, v, weight=w0, road_id=road_id, length_km=lkm)
                G1.add_edge(u, v, weight=w1)
                G_conn.add_edge(u, v)
                ea.append(
                    {
                        "u": u,
                        "v": v,
                        "road_id": road_id,
                        "w0": w0,
                        "w1": w1,
                        "p_block": pb,
                        "passable": int(pb < BLOCK_PROB_THRESH),
                        "delta_V_pct": dv,
                        "length_km": lkm,
                    }
                )

    df_edges = pd.DataFrame(ea)
    comps = list(nx.connected_components(G_conn))
    lcc_r = max(len(c) for c in comps) / G0.number_of_nodes()
    total = n_match + n_fill

    print(f"\n  Nodes={G0.number_of_nodes():,}  Edges={G0.number_of_edges():,}")
    print(f"  IRI Match={n_match / total * 100:.1f}%  Fill={n_fill:,}  Skip={n_skip:,}")
    print(f"  Components={len(comps)}  LCC Ratio={lcc_r:.1%}")
    return G0, G1, G_conn, df_edges, node_coords


def extract_lcc(G0, G1, G_conn, df_edges, node_coords):
    comps = list(nx.connected_components(G_conn))
    lcc = max(comps, key=len)
    ratio = len(lcc) / G0.number_of_nodes()

    print(
        f"\n  LCC: {len(lcc):,} nodes ({ratio:.1%})  "
        f"Edges: {G_conn.subgraph(lcc).number_of_edges():,}"
    )

    G0l = G0.subgraph(lcc).copy()
    G1l = G1.subgraph(lcc).copy()
    Gcl = G_conn.subgraph(lcc).copy()
    df_l = df_edges[df_edges["u"].isin(lcc) & df_edges["v"].isin(lcc)].copy()
    nc_l = {k: v for k, v in node_coords.items() if k in lcc}
    return G0l, G1l, Gcl, df_l, nc_l


def _scipy_sampled_efficiency(G, n_sample, weighted=True):
    nodes = list(G.nodes())
    n = len(nodes)
    if n < 2:
        return 0.0
    n_sample = min(n_sample, n)
    if weighted:
        adj = nx.to_scipy_sparse_array(G, nodelist=nodes, weight="weight", format="csr")
    else:
        adj = nx.to_scipy_sparse_array(G, nodelist=nodes, weight=None, format="csr")
        adj.data[:] = 1.0
    adj.indices = adj.indices.astype(np.int32)
    adj.indptr = adj.indptr.astype(np.int32)
    D = sp_shortest(
        adj, directed=False, indices=list(range(n_sample)), unweighted=not weighted
    )
    mask = (D > 0) & np.isfinite(D)
    return float(np.sum(1.0 / D[mask]) / (n_sample * (n - 1)))


# =============================================================================
# CITY LAYER FUNCTIONS
# =============================================================================
def compute_network_metrics(G0, G1, G_conn):
    print(f"\n{'=' * 60}\n  STEP 2 - Global Network Metrics\n{'=' * 60}")
    results = {}
    for label, G in [("normal", G0), ("extreme", G1), ("connectivity", G_conn)]:
        is_conn = label == "connectivity"
        print(f"\n  [{label}]")
        with T("Connected Components"):
            comps = list(nx.connected_components(G))
            n_comp = len(comps)
            lcc_nd = max(comps, key=len)
            lcc_r = len(lcc_nd) / G.number_of_nodes()
        print(f"    Components={n_comp}  LCC={lcc_r:.3f} ({len(lcc_nd)} nodes)")

        G_lcc = G.subgraph(lcc_nd).copy()
        n_lcc = len(G_lcc)

        with T("Global Efficiency (scipy)"):
            sn = min(EFFICIENCY_SAMPLE, n_lcc)
            E = _scipy_sampled_efficiency(G_lcc, sn, weighted=not is_conn)
        print(f"    E={E:.6f}")

        with T("Diameter (sampled)"):
            if n_lcc <= 300:
                try:
                    D = nx.diameter(G_lcc, weight="weight" if not is_conn else None)
                except Exception:
                    D = float("nan")
            else:
                samp = list(G_lcc.nodes())[:DIAMETER_SAMPLE]
                md = 0.0
                w_arg = "weight" if not is_conn else None
                for s in samp:
                    dd = nx.single_source_dijkstra_path_length(G_lcc, s, weight=w_arg)
                    if dd:
                        md = max(md, max(dd.values()))
                D = md
        print(f"    D={fmt(D)}")

        results[label] = {
            "n_components": n_comp,
            "lcc_ratio": lcc_r,
            "global_efficiency": E,
            "diameter": D,
        }

    r0, r1 = results["normal"], results["extreme"]
    dE = (
        (r0["global_efficiency"] - r1["global_efficiency"])
        / r0["global_efficiency"]
        * 100
        if r0["global_efficiency"] > 0
        else float("nan")
    )
    dD = (
        r1["diameter"] - r0["diameter"]
        if not (np.isnan(r0["diameter"]) or np.isnan(r1["diameter"]))
        else float("nan")
    )
    delta_comp = r1["n_components"] - r0["n_components"]
    print(f"\n  ΔE/E0={dE:+.3f}%  ΔD={fmt(dD)}  New components={delta_comp:+d}")
    return results


def identify_critical_roads(G0, G_conn, df_edges):
    print(f"\n{'=' * 60}\n  STEP 3 - Critical Roads Identification\n{'=' * 60}")
    with T("Tarjan Bridges"):
        bridges = set(nx.bridges(G_conn))
    n_e = G_conn.number_of_edges()
    print(f"\n  Bridges: {len(bridges):,} ({len(bridges) / n_e * 100:.1f}%)")

    k = BETWEENNESS_K if G0.number_of_nodes() > BETWEENNESS_K else None
    with T("Edge Betweenness"):
        bc = nx.edge_betweenness_centrality(G0, k=k, weight="weight", normalized=True)

    ba = np.array(list(bc.values()))
    t90 = np.percentile(ba, 90)
    t95 = np.percentile(ba, 95)
    t80 = np.percentile(ba, 80)

    def ne(u, v):
        return tuple(sorted([u, v]))

    bn = {ne(u, v) for u, v in bridges}
    b10 = {ne(u, v) for (u, v), val in bc.items() if val >= t90}
    b5 = {ne(u, v) for (u, v), val in bc.items() if val >= t95}
    b20 = {ne(u, v) for (u, v), val in bc.items() if val >= t80}

    L1 = bn & b10
    L2 = (bn | b5) - L1
    L3 = b20 - L1 - L2

    print(f"  L1 (Bridge ∩ Top 10% BC): {len(L1):,} <- Most Critical")
    print(f"  L2 (Bridge ∪ Top 5% BC):  {len(L2):,}")
    print(f"  L3 (Top 20% BC non-bridge): {len(L3):,}")

    return {
        "bridges": bridges,
        "bc": bc,
        "level1": list(L1),
        "level2": list(L2),
        "level3": list(L3),
    }


def percolation_analysis(G_conn, df_edges):
    print(f"\n{'=' * 60}\n  STEP 4 - Percolation Analysis\n{'=' * 60}")
    n_nodes = G_conn.number_of_nodes()
    all_edges = list(G_conn.edges())
    n_edges = len(all_edges)
    if n_edges == 0:
        print("  [Skip]")
        return {}

    epb = {}
    edv = {}
    for _, row in df_edges.iterrows():
        u, v = row["u"], row["v"]
        epb[(u, v)] = epb[(v, u)] = row.get("p_block", 0.0)
        edv[(u, v)] = edv[(v, u)] = abs(row.get("delta_V_pct", 0.0) or 0.0)

    dv_arr = np.array([edv.get(e, 0.0) for e in all_edges])
    pb_arr = np.array([epb.get(e, 0.0) for e in all_edges])
    dv_max = dv_arr.max() if dv_arr.max() > 0 else 1.0
    ALPHA = 0.6
    scores = ALPHA * pb_arr + (1 - ALPHA) * dv_arr / dv_max
    order = np.argsort(-scores)
    sorted_edges = [all_edges[i] for i in order]
    sz = max(1, n_edges // PERCOLATION_STEPS)
    e_steps = set(np.linspace(0, PERCOLATION_STEPS, PERC_E_STEPS, dtype=int))
    S_vals = []
    q_vals = []
    E_sparse = {}

    with T("Percolation (CC + scipy)"):
        Gt = G_conn.copy()
        for step in range(PERCOLATION_STEPS + 1):
            qv = step / PERCOLATION_STEPS
            if Gt.number_of_edges() > 0:
                cs = list(nx.connected_components(Gt))
                Sv = max(len(c) for c in cs) / n_nodes
            else:
                cs = []
                Sv = 0.0
            S_vals.append(Sv)
            q_vals.append(qv)

            if step in e_steps and Gt.number_of_edges() > 0 and cs:
                lcc_nodes = list(max(cs, key=len))
                if len(lcc_nodes) < 20:
                    E_sparse[step] = 0.0
                else:
                    samp = lcc_nodes[:PERC_E_SAMPLE]
                    try:
                        sub_adj = nx.to_scipy_sparse_array(
                            Gt.subgraph(samp),
                            nodelist=samp,
                            weight=None,
                            format="csr",
                        )
                        sub_adj.data[:] = 1.0
                        sub_adj.indices = sub_adj.indices.astype(np.int32)
                        sub_adj.indptr = sub_adj.indptr.astype(np.int32)
                        ns = len(samp)
                        D = sp_shortest(
                            sub_adj,
                            directed=False,
                            indices=list(range(ns)),
                            unweighted=True,
                        )
                        mask = (D > 0) & np.isfinite(D)
                        E_sparse[step] = float(
                            np.sum(1.0 / D[mask]) / (ns * (n_nodes - 1))
                        )
                    except Exception:
                        E_sparse[step] = E_sparse.get(step - 1, 0.0)

            batch = sorted_edges[step * sz : (step + 1) * sz]
            Gt.remove_edges_from([(u, v) for u, v in batch if Gt.has_edge(u, v)])

    prev_E = float("inf")
    for step in sorted(E_sparse.keys()):
        E_sparse[step] = min(E_sparse[step], prev_E)
        prev_E = E_sparse[step]

    e_steps_sorted = sorted(E_sparse.keys())
    E_vals = []
    for step in range(PERCOLATION_STEPS + 1):
        if step in E_sparse:
            E_vals.append(E_sparse[step])
        else:
            prev = max((s for s in e_steps_sorted if s <= step), default=None)
            nxt = min((s for s in e_steps_sorted if s >= step), default=None)
            if prev is None:
                E_vals.append(E_sparse[nxt])
            elif nxt is None:
                E_vals.append(E_sparse[prev])
            else:
                t = (step - prev) / (nxt - prev)
                E_vals.append(E_sparse[prev] * (1 - t) + E_sparse[nxt] * t)

    S_arr = np.array(S_vals)
    q_arr = np.array(q_vals)
    dS = np.diff(S_arr)
    qi = int(np.argmin(dS))
    qc = q_arr[qi]
    E0 = E_vals[0]
    dEr = (E0 - E_vals[qi]) / E0 if E0 > 0 else float("nan")
    amp = dEr / qc if qc > 0 else float("nan")

    print(
        f"\n  q_c={qc:.3f}  S(qc)={S_arr[qi]:.4f}  ΔE/E0={dEr * 100:.2f}%  Amp={fmt(amp)}"
    )
    print(
        f"  {'Non-linear amplification ✓' if amp and not np.isnan(amp) and amp > 1 else 'Near linear'}"
    )

    return {
        "q_values": q_vals,
        "S_values": list(S_arr),
        "E_values": E_vals,
        "q_c": qc,
        "S_at_qc": float(S_arr[qi]),
        "E_drop_at_qc": dEr,
        "amplification": amp,
        "E_sampled_steps": e_steps_sorted,
    }


def spatial_clustering(df_edges, critical_info):
    print(f"\n{'=' * 60}\n  STEP 5 - Spatial Clustering\n{'=' * 60}")
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    bc = critical_info.get("bc", {})
    bn = {tuple(sorted(e)) for e in critical_info.get("bridges", set())}
    F = []
    for _, row in df_edges.iterrows():
        u, v = row["u"], row["v"]
        F.append(
            [
                bc.get((u, v), bc.get((v, u), 0.0)),
                row["p_block"],
                int(tuple(sorted([u, v])) in bn),
                abs(row.get("delta_V_pct", 0) or 0),
            ]
        )

    X = np.nan_to_num(np.array(F), 0)
    Xs = StandardScaler().fit_transform(X)
    k = min(5, max(2, len(X) // 20))
    print(f"  Samples={len(X):,}  k={k}")

    with T(f"K-means (k={k})"):
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(Xs)

    df_c = pd.DataFrame(F, columns=["bc", "p_block", "is_bridge", "delta_v"])
    df_c["cluster"] = labels
    bm_global = df_c["bc"].mean()
    su = []

    print(
        f"\n  {'Cluster':>7}  {'Count':>7}  {'BC Mean':>10}  {'p_block':>9}  "
        f"{'Bridge%':>7}  {'ΔV':>7}  Tag"
    )
    for c in range(k):
        sb = df_c[df_c["cluster"] == c]
        bm = sb["bc"].mean()
        pm = sb["p_block"].mean()
        brm = sb["is_bridge"].mean() * 100
        dvm = sb["delta_v"].mean()

        if brm > 50 and pm > 0.2:
            tag = "Critical (Bridge + Block)"
        elif brm > 50 and bm > bm_global:
            tag = "High Risk (Bridge + Traffic)"
        elif brm > 50:
            tag = "Structurally Vulnerable"
        elif pm > 0.35:
            tag = "High Block Risk"
        elif bm > bm_global * 3:
            tag = "High Traffic Critical"
        else:
            tag = "Low Risk"

        print(
            f"  {c:>7}  {len(sb):>7}  {bm:>10.6f}  {pm:>9.4f}  "
            f"{brm:>7.1f}  {dvm:>7.2f}  {tag}"
        )
        su.append(
            {
                "cluster": c,
                "n": len(sb),
                "bc_mean": bm,
                "p_block_mean": pm,
                "bridge_pct": brm,
                "delta_v_mean": dvm,
                "tag": tag,
            }
        )
    return {"labels": labels, "summary": su}


def save_percolation_curve(perc, out_path):
    if not perc or "q_values" not in perc:
        return
    df = pd.DataFrame(
        {
            "q": perc["q_values"],
            "S": perc["S_values"],
            "E": perc["E_values"],
            "E_exact": [
                i in perc["E_sampled_steps"] for i in range(len(perc["q_values"]))
            ],
        }
    )
    df.to_csv(out_path, index=False)


def save_critical_roads(critical, node_coords, G0, out_path):
    bc = critical.get("bc", {})
    bn = {tuple(sorted(e)) for e in critical.get("bridges", set())}
    rows = []
    levels = [
        ("L1", critical["level1"]),
        ("L2", critical["level2"]),
        ("L3", critical["level3"]),
    ]
    for level_name, edge_list in levels:
        for u, v in edge_list:
            ne = tuple(sorted([u, v]))
            lon_u, lat_u = node_coords.get(u, (float("nan"), float("nan")))
            lon_v, lat_v = node_coords.get(v, (float("nan"), float("nan")))
            road_id = G0[u][v].get("road_id", "") if G0.has_edge(u, v) else ""
            rows.append(
                {
                    "level": level_name,
                    "road_id": road_id,
                    "u": u,
                    "v": v,
                    "lon_u": lon_u,
                    "lat_u": lat_u,
                    "lon_v": lon_v,
                    "lat_v": lat_v,
                    "bc": bc.get(ne, bc.get((v, u), float("nan"))),
                    "is_bridge": int(ne in bn),
                }
            )
    pd.DataFrame(rows).to_csv(out_path, index=False)


def save_cluster_edges(df_edges, clust_labels, node_coords, out_path):
    rows = []
    for i, (_, row) in enumerate(df_edges.iterrows()):
        u, v = row["u"], row["v"]
        lu, la = node_coords.get(u, (float("nan"), float("nan")))
        lv, lb = node_coords.get(v, (float("nan"), float("nan")))
        mid_lon = (lu + lv) / 2 if not (np.isnan(lu) or np.isnan(lv)) else float("nan")
        mid_lat = (la + lb) / 2 if not (np.isnan(la) or np.isnan(lb)) else float("nan")
        rows.append(
            {
                "road_id": row.get("road_id", ""),
                "u": u,
                "v": v,
                "mid_lon": mid_lon,
                "mid_lat": mid_lat,
                "cluster": int(clust_labels[i]) if i < len(clust_labels) else -1,
                "p_block": row.get("p_block", float("nan")),
                "is_bridge": row.get("passable", float("nan")),
                "delta_v": abs(row.get("delta_V_pct", 0) or 0),
                "length_km": row.get("length_km", float("nan")),
            }
        )
    pd.DataFrame(rows).to_csv(out_path, index=False)


def _build_summary_row(
    district_id,
    country,
    layer,
    G0,
    G1,
    G_conn,
    df_edges,
    metrics,
    critical,
    perc,
    runtime,
):
    E0 = metrics["normal"]["global_efficiency"]
    E1 = metrics["extreme"]["global_efficiency"]
    dE_pct = (E0 - E1) / E0 * 100 if E0 > 0 else float("nan")
    dv_vals = df_edges["delta_V_pct"].dropna()
    mean_road_deg = float(dv_vals.mean()) if len(dv_vals) > 0 else float("nan")
    if not np.isnan(mean_road_deg) and mean_road_deg > 0 and not np.isnan(dE_pct):
        amplification_ratio = dE_pct / mean_road_deg
    else:
        amplification_ratio = float("nan")

    n_comp_normal = metrics["normal"]["n_components"]
    n_comp_extreme = metrics["extreme"]["n_components"]

    bridge_ratio = (
        len(critical["bridges"]) / G_conn.number_of_edges()
        if G_conn.number_of_edges() > 0
        else float("nan")
    )

    return {
        "district_id": district_id,
        "country": country,
        "layer": layer,
        "n_nodes": G0.number_of_nodes(),
        "n_edges": G0.number_of_edges(),
        "lcc_ratio": metrics["normal"]["lcc_ratio"],
        "bridge_ratio": bridge_ratio,
        "L1_count": len(critical["level1"]),
        "mean_road_degradation_pct": mean_road_deg,
        "mean_p_block": float(df_edges["p_block"].mean()),
        "E_normal": E0,
        "E_extreme": E1,
        "dE_pct": dE_pct,
        "D_normal": metrics["normal"]["diameter"],
        "D_extreme": metrics["extreme"]["diameter"],
        "n_comp_normal": n_comp_normal,
        "n_comp_extreme": n_comp_extreme,
        "delta_components": n_comp_extreme - n_comp_normal,
        "amplification_ratio": amplification_ratio,
        "q_c": perc.get("q_c", float("nan")),
        "S_at_qc": perc.get("S_at_qc", float("nan")),
        "perc_E_drop_at_qc": perc.get("E_drop_at_qc", float("nan")),
        "perc_amplification": perc.get("amplification", float("nan")),
        "runtime_s": runtime,
    }


# =============================================================================
# COUNTRY / AFRICA LAYER FUNCTIONS
# =============================================================================
def snap_cities_to_network(city_nodes_df, G0, node_coords, country_filter=None):
    df = city_nodes_df.copy()
    if country_filter:
        df = df[df["country_folder"] == country_filter].copy()
    if df.empty:
        return []

    net_nodes = list(node_coords.keys())
    net_xy = np.array([node_coords[n] for n in net_nodes])
    tree = cKDTree(net_xy)

    snapped = []
    for _, row in df.iterrows():
        dist, idx = tree.query([row["lon"], row["lat"]])
        snap_node = net_nodes[idx]
        if snap_node in G0:
            snapped.append(
                {
                    "city_name": row["city_name"],
                    "level": row.get("level", ""),
                    "lon": row["lon"],
                    "lat": row["lat"],
                    "snap_node": snap_node,
                    "snap_dist_km": dist * 111,
                }
            )
    return snapped


def compute_od_analysis(G0, G1, snapped, country, layer):
    print(f"\n{'=' * 60}\n  OD Analysis - Functional Accessibility\n{'=' * 60}")

    if len(snapped) < 2:
        print(f"  [Skip] Valid city nodes = {len(snapped)} < 2")
        return None, None, None, None, {}

    city_names = [s["city_name"] for s in snapped]
    snap_nodes = [s["snap_node"] for s in snapped]
    levels = [s["level"] for s in snapped]
    n_cities = len(city_names)
    print(f"  City nodes: {n_cities}  ({', '.join(set(levels))})")

    def compute_dist_matrix(G, label):
        mat = {}
        with T(f"Shortest path ({label})"):
            for cname, snode in zip(city_names, snap_nodes):
                if snode not in G:
                    mat[cname] = {}
                    continue
                lengths = nx.single_source_dijkstra_path_length(
                    G, snode, weight="weight"
                )
                mat[cname] = lengths
        return mat

    dist0 = compute_dist_matrix(G0, "normal")
    dist1 = compute_dist_matrix(G1, "extreme")

    INF = float("nan")
    mat_n = pd.DataFrame(index=city_names, columns=city_names, dtype=float)
    mat_e = pd.DataFrame(index=city_names, columns=city_names, dtype=float)

    for i, (cA, nA) in enumerate(zip(city_names, snap_nodes)):
        for j, (cB, nB) in enumerate(zip(city_names, snap_nodes)):
            if i == j:
                mat_n.loc[cA, cB] = 0.0
                mat_e.loc[cA, cB] = 0.0
            else:
                mat_n.loc[cA, cB] = dist0.get(cA, {}).get(nB, INF)
                mat_e.loc[cA, cB] = dist1.get(cA, {}).get(nB, INF)

    pair_rows = []
    for i in range(n_cities):
        for j in range(i + 1, n_cities):
            cA, cB = city_names[i], city_names[j]
            t0_val = mat_n.loc[cA, cB]
            t1_val = mat_e.loc[cA, cB]

            t0_ok = pd.notna(t0_val) and t0_val < UNREACHABLE_THRESH
            t1_ok = pd.notna(t1_val) and t1_val < UNREACHABLE_THRESH

            if not t0_ok and not t1_ok:
                conn_type = "both_unreachable"
            elif not t0_ok and t1_ok:
                conn_type = "normal_unreachable"
            elif t0_ok and not t1_ok:
                conn_type = "climate_disconnected"
            else:
                conn_type = "connected"

            increase_pct = float("nan")
            if t0_ok and t1_ok and t0_val > 0:
                increase_pct = (t1_val - t0_val) / t0_val * 100

            pair_rows.append(
                {
                    "country": country,
                    "city_A": cA,
                    "city_B": cB,
                    "level_A": levels[i],
                    "level_B": levels[j],
                    "t_normal_h": t0_val if t0_ok else float("nan"),
                    "t_extreme_h": t1_val if t1_ok else float("nan"),
                    "increase_pct": increase_pct,
                    "conn_type": conn_type,
                    "severe_increase": int(
                        not np.isnan(increase_pct)
                        and increase_pct >= SEVERE_INCREASE_THRESH * 100
                    ),
                }
            )

    od_pairs_df = pd.DataFrame(pair_rows)

    iso_rows = []
    for i, (cname, snode, level) in enumerate(zip(city_names, snap_nodes, levels)):
        other_pairs = od_pairs_df[
            (od_pairs_df["city_A"] == cname) | (od_pairs_df["city_B"] == cname)
        ].copy()

        n_total = len(other_pairs)
        n_climate_disconnected = (
            other_pairs["conn_type"] == "climate_disconnected"
        ).sum()
        n_both_unreachable = (other_pairs["conn_type"] == "both_unreachable").sum()
        n_connected = (other_pairs["conn_type"] == "connected").sum()
        n_severe = other_pairs["severe_increase"].sum()

        connected_pairs = other_pairs[other_pairs["conn_type"] == "connected"]
        mean_increase = (
            connected_pairs["increase_pct"].mean()
            if len(connected_pairs) > 0
            else float("nan")
        )
        max_increase = (
            connected_pairs["increase_pct"].max()
            if len(connected_pairs) > 0
            else float("nan")
        )

        disconn_ratio = n_climate_disconnected / n_total if n_total > 0 else 0.0

        iso_rows.append(
            {
                "country": country,
                "city_name": cname,
                "level": level,
                "n_city_pairs": n_total,
                "n_climate_disconnected": int(n_climate_disconnected),
                "n_both_unreachable": int(n_both_unreachable),
                "n_connected": int(n_connected),
                "n_severe_increase": int(n_severe),
                "disconnection_ratio": disconn_ratio,
                "mean_travel_increase_pct": mean_increase,
                "max_travel_increase_pct": max_increase,
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
    n_total_pairs = len(od_pairs_df)

    climate_disconn_ratio = (
        len(climate_disc) / n_total_pairs if n_total_pairs > 0 else float("nan")
    )
    summary = {
        "country": country,
        "layer": layer,
        "n_cities": n_cities,
        "n_city_pairs": n_total_pairs,
        "n_connected": (od_pairs_df["conn_type"] == "connected").sum(),
        "n_climate_disconnected": len(climate_disc),
        "n_both_unreachable": (od_pairs_df["conn_type"] == "both_unreachable").sum(),
        "climate_disconn_ratio": climate_disconn_ratio,
        "mean_travel_increase_pct": connected["increase_pct"].mean(),
        "median_travel_increase_pct": connected["increase_pct"].median(),
        "p75_travel_increase_pct": connected["increase_pct"].quantile(0.75),
        "pct_severe_increase": od_pairs_df["severe_increase"].mean() * 100,
        "n_severe_increase": od_pairs_df["severe_increase"].sum(),
    }

    print(f"\n  Total city pairs: {n_total_pairs}")
    print(
        f"  Climate disconnected: {summary['n_climate_disconnected']} "
        f"({summary['climate_disconn_ratio'] * 100:.1f}%)"
    )
    print(
        f"  Travel time increase for connected pairs: "
        f"Mean={fmt(summary['mean_travel_increase_pct'])}%  "
        f"Median={fmt(summary['median_travel_increase_pct'])}%"
    )
    print(
        f"  Severely degraded (>50%): {summary['n_severe_increase']} "
        f"({summary['pct_severe_increase']:.1f}%)"
    )
    print(f"\n  Top 5 highest isolation risk cities:")
    for _, r in city_iso_df.head(5).iterrows():
        print(
            f"    {r['city_name']:<25} Disconn={r['n_climate_disconnected']:>3} pairs  "
            f"Avg Increase={fmt(r['mean_travel_increase_pct'])}%  level={r['level']}"
        )

    return od_pairs_df, city_iso_df, mat_n, mat_e, summary


def run_od_layer(
    shp_path, iri_path, nodes_path, country, layer, surface="unpaved", out_dir=None
):
    t0 = time.time()
    G0, G1, G_conn, df_edges, node_coords = build_graphs_from_shp(
        shp_path, iri_path, surface
    )
    G0, G1, G_conn, df_edges, node_coords = extract_lcc(
        G0, G1, G_conn, df_edges, node_coords
    )

    if G0.number_of_nodes() < 5:
        print("  [Skip] Nodes < 5")
        return None

    city_nodes = pd.read_csv(nodes_path)
    cf = country if layer == "country" else None
    snapped = snap_cities_to_network(city_nodes, G0, node_coords, country_filter=cf)

    if len(snapped) < 2:
        print("  [Skip] Valid cities after snap < 2")
        return None

    od_pairs_df, city_iso_df, mat_n, mat_e, summary = compute_od_analysis(
        G0, G1, snapped, country, layer
    )

    runtime = time.time() - t0
    summary["runtime_s"] = runtime

    if out_dir:
        od = Path(out_dir)
        od.mkdir(parents=True, exist_ok=True)
        od_pairs_df.to_csv(od / f"{country}_od_pairs.csv", index=False)
        city_iso_df.to_csv(od / f"{country}_city_isolation.csv", index=False)
        mat_n.to_csv(od / f"{country}_od_matrix_normal.csv")
        mat_e.to_csv(od / f"{country}_od_matrix_extreme.csv")

    print(f"\n{'=' * 60}")
    print(f"  Complete - {runtime:.1f}s")
    return summary


# =============================================================================
# CITY LAYER RUNNERS
# =============================================================================
def run_single_city(
    shp_path,
    iri_path,
    surface="unpaved",
    no_lcc=False,
    district_id=None,
    country="Unknown",
    out_dir=None,
):
    t0 = time.time()
    G0, G1, G_conn, df_edges, node_coords = build_graphs_from_shp(
        shp_path, iri_path, surface
    )
    if not no_lcc:
        G0, G1, G_conn, df_edges, node_coords = extract_lcc(
            G0, G1, G_conn, df_edges, node_coords
        )

    if G0.number_of_nodes() < 5:
        print("  [Skip] Nodes < 5")
        return None

    metrics = compute_network_metrics(G0, G1, G_conn)
    critical = identify_critical_roads(G0, G_conn, df_edges)
    perc = percolation_analysis(G_conn, df_edges)
    clust = spatial_clustering(df_edges, critical)
    runtime = time.time() - t0
    did = district_id or Path(shp_path).stem

    if out_dir:
        od = Path(out_dir)
        perc_dir = od / "perc_curves"
        perc_dir.mkdir(parents=True, exist_ok=True)
        crit_dir = od / "critical_roads"
        crit_dir.mkdir(parents=True, exist_ok=True)
        clust_dir = od / "cluster_edges"
        clust_dir.mkdir(parents=True, exist_ok=True)

        save_percolation_curve(perc, perc_dir / f"{did}.csv")
        save_critical_roads(critical, node_coords, G0, crit_dir / f"{did}.csv")
        save_cluster_edges(
            df_edges, clust["labels"], node_coords, clust_dir / f"{did}.csv"
        )

    row = _build_summary_row(
        did, country, "city", G0, G1, G_conn, df_edges, metrics, critical, perc, runtime
    )

    print(f"\n{'=' * 60}")
    print(f"  Complete - {runtime:.1f}s")
    print(
        f"  Road Degradation={fmt(row['mean_road_degradation_pct'])}%  "
        f"ΔE/E0={row['dE_pct']:+.3f}%  "
        f"Amplification={fmt(row['amplification_ratio'])}  q_c={fmt(row['q_c'])}"
    )
    return row


def run_batch_city(batch_dir, country, surface="unpaved", out_dir=None):
    batch_dir = Path(batch_dir)
    out_dir = Path(out_dir) if out_dir else (OUTPUT_ROOT / "city_layer" / country)
    out_dir.mkdir(parents=True, exist_ok=True)
    shp_files = sorted(batch_dir.rglob("*.shp"))

    print(f"\nBatch processing (city): {len(shp_files)} districts [{country}]")
    print("=" * 60)

    rows = []
    for i, shp in enumerate(shp_files):
        did = shp.stem
        iri_file = shp.parent / f"{did}_speed.csv"
        if not iri_file.exists():
            print(f"  [{i + 1}/{len(shp_files)}] {did}: speed CSV not found, skipping")
            continue

        print(f"\n[{i + 1}/{len(shp_files)}] {did}")
        try:
            row = run_single_city(
                str(shp),
                str(iri_file),
                surface=surface,
                district_id=did,
                country=country,
                out_dir=str(out_dir),
            )
            if row:
                rows.append(row)
        except Exception as e:
            print(f"  [ERROR] {e}")
        gc.collect()

    if rows:
        df_out = pd.DataFrame(rows)
        csv_path = out_dir / f"{country}_district_summary.csv"
        df_out.to_csv(csv_path, index=False)

        print(f"\n{'=' * 60}")
        print(f"Summary: {len(rows)}/{len(shp_files)} districts -> {csv_path}")
        print(
            f"  Avg road degradation: {df_out['mean_road_degradation_pct'].mean():.2f}%"
        )
        print(f"  Avg ΔE/E0:            {df_out['dE_pct'].mean():.2f}%")
        print(f"  Avg amplification:    {df_out['amplification_ratio'].mean():.3f}")
        print(
            f"  Amp > 1:              {(df_out['amplification_ratio'] > 1).sum()}/{len(rows)}"
        )
        print(f"  Avg q_c:              {df_out['q_c'].mean():.3f}")
    return rows


# =============================================================================
# MAIN EXECUTABLE
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Africa Road Network Climate Impact Pipeline v7"
    )
    parser.add_argument(
        "--layer", choices=["city", "country", "africa"], default="city"
    )
    parser.add_argument("--shp", type=str)
    parser.add_argument("--iri", type=str)
    parser.add_argument("--nodes", type=str, help="City node CSV")
    parser.add_argument("--surface", type=str, default="unpaved")
    parser.add_argument("--no_lcc", action="store_true")
    parser.add_argument("--batch_dir", type=str, help="city_layer/{Country} dir")
    parser.add_argument("--country", type=str, default="Unknown")
    parser.add_argument("--out_dir", type=str)
    args = parser.parse_args()

    # City Layer Execution
    if args.layer == "city":
        if args.batch_dir:
            run_batch_city(args.batch_dir, args.country, args.surface, args.out_dir)
        elif args.shp and args.iri:
            out_dir = (
                Path(args.out_dir)
                if args.out_dir
                else (OUTPUT_ROOT / "city_layer" / args.country)
            )
            out_dir.mkdir(parents=True, exist_ok=True)
            row = run_single_city(
                args.shp,
                args.iri,
                args.surface,
                args.no_lcc,
                country=args.country,
                out_dir=str(out_dir),
            )
            if row:
                pd.DataFrame([row]).to_csv(
                    out_dir / f"{Path(args.shp).stem}_summary.csv", index=False
                )
        else:
            print("City layer requires --batch_dir OR --shp + --iri")
        return

    # Country / Africa Layer Execution
    if args.layer in ("country", "africa"):
        if not (args.shp and args.iri and args.nodes):
            print(f"{args.layer} layer requires --shp, --iri, and --nodes")
            return

        out_dir = (
            Path(args.out_dir)
            if args.out_dir
            else (OUTPUT_ROOT / f"{args.layer}_layer" / args.country)
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        summary = run_od_layer(
            args.shp,
            args.iri,
            args.nodes,
            country=args.country,
            layer=args.layer,
            surface=args.surface,
            out_dir=str(out_dir),
        )
        if summary:
            pd.DataFrame([summary]).to_csv(
                out_dir / f"{args.country}_od_summary.csv", index=False
            )
            print(f"Summary saved to: {out_dir / f'{args.country}_od_summary.csv'}")
        return


if __name__ == "__main__":
    main()
