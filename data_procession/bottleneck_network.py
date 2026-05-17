"""
bottleneck_network.py

Builds the pan-African road network, computes NI/CV/bottleneck scores,
and serialises the experiment state for the paving simulation.

Usage:
    python data_procession/bottleneck_network.py --base <BASE_DIR>
    python data_procession/bottleneck_network.py --base <BASE_DIR> --rebuild

Outputs (all under <BASE_DIR>/web/network_results/bottleneck_paving/):
    01_graph_checkpoint.pkl   — cached pan-African NetworkX graph
    02_edge_scores.csv        — per-edge NI, CV, bottleneck scores
    03_2x2_matrix.csv         — four-quadrant summary
    experiment_state.pkl      — serialised state for paving_experiment.py
    network_stats.json        — n_total / n_unpaved / n_ni_positive for plotting
"""

import argparse
import gc
import json
import pickle
import shutil
import tempfile
import time
import warnings
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import igraph as ig
import networkx as nx
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from scipy.spatial import cKDTree

warnings.filterwarnings("ignore")

# ── Paths ─────────────────────────────────────────────────────────────────────
_DEFAULT_BASE = Path("<BASE_DIR>")

# ── Road network ──────────────────────────────────────────────────────────────
MIN_ROAD_LENGTH_KM = 0.1
SNAP_THRESHOLD_DEG = 0.0045
BORDER_DEG = 0.5
CROSS_BORDER_DIST_DEG = 0.20
CROSS_BORDER_SPEED = 40.0

# ── WorldPop demand nodes ─────────────────────────────────────────────────────
WORLDPOP_GRID_DEG = 0.5
WORLDPOP_POP_THRESH = 50_000
WORLDPOP_POP_THRESH_RURAL = 1_000
N_RURAL_NODES = 3_000
WORLDPOP_RURAL_SEED = 42
WORLDPOP_SNAP_MAX_DEG = 0.5

# ── Network analysis ──────────────────────────────────────────────────────────
GRAVITY_ALPHA = 2.0
UNREACHABLE = 1e8
CV_MIN_THRESHOLD = 0.02

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
# STEP 1 — BUILD PAN-AFRICAN GRAPH
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
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

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


def _build_country_graph(country, node_offset, roads_dir, speed_dir):
    shp_path = roads_dir / country / f"{country}.shp"
    speed_path = speed_dir / f"{country}_road_speed.csv"
    if not shp_path.exists() or not speed_path.exists():
        return None

    try:
        gdf = gpd.read_file(shp_path)
    except Exception as e:
        print(f"  [{country} ERROR] {e}")
        return None

    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    if "length_km" not in gdf.columns:
        gdf["length_km"] = gdf.to_crs("ESRI:102022").geometry.length / 1000
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
        v_n_med = float(df_sp["V_normal"].median())
        speed_lu = df_sp.set_index("road_id")[
            ["V_normal", "V_extreme", "p_block"]
        ].to_dict("index")
    except Exception:
        v_n_med, speed_lu = 60.0, {}

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
        coords_list.extend([(sc[0], sc[1]), (ec[0], ec[1])])
        road_ep_idx.append((si, ei))
        same_pairs.add((min(si, ei), max(si, ei)))

    if not coords_list:
        return None

    pts_arr = np.array(coords_list, dtype=np.float64)
    node_id_of, node_coords_local = _merge_endpoints(
        pts_arr, same_pairs, SNAP_THRESHOLD_DEG
    )
    node_coords_global = {nid + node_offset: c for nid, c in node_coords_local.items()}

    G0, G1 = nx.Graph(), nx.Graph()
    for nid, (lon, lat) in node_coords_global.items():
        G0.add_node(nid, lon=lon, lat=lat)
        G1.add_node(nid)

    for ridx in range(len(gdf)):
        ep = road_ep_idx[ridx]
        if ep is None:
            continue
        u = node_id_of[ep[0]] + node_offset
        v = node_id_of[ep[1]] + node_offset
        if u == v:
            continue
        row = gdf.iloc[ridx]
        lkm = max(float(row["length_km"]), 1e-6)
        d = speed_lu.get(row["road_id"], {})
        V_n = d.get("V_normal", v_n_med)
        V_e = d.get("V_extreme", v_n_med)
        pb = d.get("p_block", 0.0)
        w0 = lkm / V_n
        w1 = lkm / V_e / (1.0 - min(pb, 0.99))
        if G0.has_edge(u, v):
            if w0 < G0[u][v]["weight"]:
                G0[u][v]["weight"] = w0
                G1[u][v]["weight"] = w1
        else:
            G0.add_edge(u, v, weight=w0)
            G1.add_edge(u, v, weight=w1)

    lons = np.array([c[0] for c in node_coords_global.values()])
    lats = np.array([c[1] for c in node_coords_global.values()])
    border_nodes = [
        (nid, lon, lat, country)
        for nid, (lon, lat) in node_coords_global.items()
        if (
            lon - lons.min() < BORDER_DEG
            or lons.max() - lon < BORDER_DEG
            or lat - lats.min() < BORDER_DEG
            or lats.max() - lat < BORDER_DEG
        )
    ]
    del gdf, pts_arr, coords_list, same_pairs
    gc.collect()
    return G0, G1, node_coords_global, border_nodes


def build_africa_graph(roads_dir: Path, speed_dir: Path, checkpoint_path: Path):
    if checkpoint_path.exists():
        print(f"\n  [CHECKPOINT] Loading graph from {checkpoint_path.name} …")
        with open(checkpoint_path, "rb") as f:
            data = pickle.load(f)
        G0, G1, all_nc = data["G0"], data["G1"], data["all_nc"]
        print(f"  G0: {G0.number_of_nodes():,} nodes  {G0.number_of_edges():,} edges")
        return G0, G1, all_nc

    print(f"\n{'='*60}\n  STEP 1 — Build Pan-African Graph\n{'='*60}")
    G0_pan, G1_pan = nx.Graph(), nx.Graph()
    all_nc, all_border = {}, []
    node_offset = 0

    for country in FOLDER_TO_ISO:
        result = _build_country_graph(country, node_offset, roads_dir, speed_dir)
        if result is None:
            continue
        G0c, G1c, nc, border = result
        G0_pan.add_nodes_from(G0c.nodes(data=True))
        G0_pan.add_edges_from(G0c.edges(data=True))
        G1_pan.add_nodes_from(G1c.nodes(data=True))
        G1_pan.add_edges_from(G1c.edges(data=True))
        all_nc.update(nc)
        all_border.extend(border)
        node_offset += len(nc)
        del G0c, G1c, nc, border
        gc.collect()

    border_arr = np.array([(lon, lat) for _, lon, lat, _ in all_border])
    border_nids = [nid for nid, _, _, _ in all_border]
    border_countries = [c for _, _, _, c in all_border]
    tree = cKDTree(border_arr)
    for i, j in tree.query_pairs(CROSS_BORDER_DIST_DEG):
        if border_countries[i] == border_countries[j]:
            continue
        u, v = border_nids[i], border_nids[j]
        if G0_pan.has_edge(u, v):
            continue
        dist_km = (
            np.hypot(
                border_arr[i, 0] - border_arr[j, 0], border_arr[i, 1] - border_arr[j, 1]
            )
            * 111.0
        )
        w = dist_km / CROSS_BORDER_SPEED
        G0_pan.add_edge(u, v, weight=w)
        G1_pan.add_edge(u, v, weight=w)

    lcc = max(nx.connected_components(G0_pan), key=len)
    G0 = G0_pan.subgraph(lcc).copy()
    G1 = G1_pan.subgraph(lcc).copy()
    all_nc = {k: v for k, v in all_nc.items() if k in lcc}
    del G0_pan, G1_pan
    gc.collect()

    with open(checkpoint_path, "wb") as f:
        pickle.dump(
            {"G0": G0, "G1": G1, "all_nc": all_nc}, f, protocol=pickle.HIGHEST_PROTOCOL
        )
    print(f"  Saved checkpoint → {checkpoint_path.name}")
    return G0, G1, all_nc


# =============================================================================
# STEP 2 — WORLDPOP DEMAND NODES
# =============================================================================
def sample_worldpop_nodes(pop_dir: Path, G0: nx.Graph, all_nc: dict):
    print(f"\n{'='*60}\n  STEP 2 — Sample WorldPop Demand Nodes (stratified)\n{'='*60}")
    nids = list(all_nc.keys())
    xy = np.array([all_nc[n] for n in nids])
    tree = cKDTree(xy)

    node_pop, node_lon, node_lat = {}, {}, {}
    rural_lons, rural_lats, rural_pops = [], [], []

    for country, iso3 in sorted(FOLDER_TO_ISO.items()):
        tif_path = pop_dir / f"{iso3.lower()}_ppp_2020_UNadj_constrained.tif"
        if not tif_path.exists():
            continue
        try:
            with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
                tmp_path = tmp.name
            shutil.copy2(tif_path, tmp_path)
            with open(tmp_path, "rb") as f:
                raw_bytes = f.read()
            Path(tmp_path).unlink(missing_ok=True)

            with rasterio.MemoryFile(raw_bytes) as memfile:
                with memfile.open() as src:
                    res_deg = src.res[0]
                    scale = max(1, round(WORLDPOP_GRID_DEG / res_deg))
                    new_h = max(1, src.height // scale)
                    new_w = max(1, src.width // scale)
                    try:
                        agg = src.read(
                            1, out_shape=(new_h, new_w), resampling=Resampling.sum
                        )
                    except Exception:
                        raw = src.read(1).astype(np.float32)
                        raw = np.where(
                            (raw == src.nodata) | (~np.isfinite(raw)), 0.0, raw
                        )
                        agg = raw[: new_h * scale, : new_w * scale]
                        agg = agg.reshape(new_h, scale, new_w, scale).sum(axis=(1, 3))

                    cell_lon = (
                        src.transform.c + (np.arange(new_w) + 0.5) * WORLDPOP_GRID_DEG
                    )
                    cell_lat = (
                        src.transform.f - (np.arange(new_h) + 0.5) * WORLDPOP_GRID_DEG
                    )
                    lon_grid, lat_grid = np.meshgrid(cell_lon, cell_lat)
                    if src.nodata is not None:
                        agg = np.where(agg == src.nodata * scale**2, 0.0, agg)
                    agg = np.where(np.isfinite(agg), agg, 0.0)

                    # Urban tier — snap immediately
                    mask_u = agg > WORLDPOP_POP_THRESH
                    if mask_u.any():
                        pts_u = np.column_stack(
                            [lon_grid[mask_u].ravel(), lat_grid[mask_u].ravel()]
                        )
                        dists_u, idxs_u = tree.query(pts_u)
                        for lc, la, p, ix, ok in zip(
                            lon_grid[mask_u].ravel(),
                            lat_grid[mask_u].ravel(),
                            agg[mask_u].ravel(),
                            idxs_u,
                            dists_u <= WORLDPOP_SNAP_MAX_DEG,
                        ):
                            if ok and nids[ix] in G0:
                                sn = nids[ix]
                                node_pop[sn] = node_pop.get(sn, 0.0) + float(p)
                                node_lon[sn], node_lat[sn] = lc, la

                    # Rural tier — collect candidates
                    mask_r = (agg > WORLDPOP_POP_THRESH_RURAL) & (
                        agg <= WORLDPOP_POP_THRESH
                    )
                    if mask_r.any():
                        rural_lons.extend(lon_grid[mask_r].ravel().tolist())
                        rural_lats.extend(lat_grid[mask_r].ravel().tolist())
                        rural_pops.extend(agg[mask_r].ravel().tolist())

            del raw_bytes
            gc.collect()
        except Exception:
            continue

    # Sample rural pool
    r_lons = np.array(rural_lons, dtype=np.float64)
    r_lats = np.array(rural_lats, dtype=np.float64)
    r_pops = np.array(rural_pops, dtype=np.float64)
    if len(r_lons) > N_RURAL_NODES:
        probs = r_pops / r_pops.sum()
        rng = np.random.default_rng(seed=WORLDPOP_RURAL_SEED)
        sidx = rng.choice(len(r_lons), size=N_RURAL_NODES, replace=False, p=probs)
        r_lons, r_lats, r_pops = r_lons[sidx], r_lats[sidx], r_pops[sidx]

    if len(r_lons) > 0:
        pts_r = np.column_stack([r_lons, r_lats])
        dists_r, idxs_r = tree.query(pts_r)
        for lc, la, p, ix, ok in zip(
            r_lons, r_lats, r_pops, idxs_r, dists_r <= WORLDPOP_SNAP_MAX_DEG
        ):
            if ok and nids[ix] in G0:
                sn = nids[ix]
                node_pop[sn] = node_pop.get(sn, 0.0) + float(p)
                if sn not in node_lon:
                    node_lon[sn], node_lat[sn] = lc, la

    demand_nodes = [
        {"snap_node": sn, "pop": node_pop[sn], "lon": node_lon[sn], "lat": node_lat[sn]}
        for sn in node_pop
    ]
    total_pop = sum(d["pop"] for d in demand_nodes)
    print(f"  Demand nodes: {len(demand_nodes):,}  pop = {total_pop/1e6:.1f} M")
    return demand_nodes


# =============================================================================
# STEPS 3–6 — IGRAPH / ACCESSIBILITY / NI / SCORES
# =============================================================================
def build_igraphs(G0: nx.Graph, G1: nx.Graph):
    node_list = list(G0.nodes())
    node_idx = {n: i for i, n in enumerate(node_list)}
    edge_list = list(G0.edges())
    edges_ig = [(node_idx[u], node_idx[v]) for u, v in edge_list]
    w0_arr = np.array([G0[u][v]["weight"] for u, v in edge_list], dtype=np.float64)
    w1_arr = np.array(
        [
            G1[u][v]["weight"] if G1.has_edge(u, v) else G0[u][v]["weight"]
            for u, v in edge_list
        ],
        dtype=np.float64,
    )
    N = len(node_list)
    g0_ig = ig.Graph(n=N, edges=edges_ig, directed=False)
    g0_ig.es["weight"] = w0_arr.tolist()
    g1_ig = ig.Graph(n=N, edges=edges_ig, directed=False)
    g1_ig.es["weight"] = w1_arr.tolist()
    return node_list, node_idx, edge_list, edges_ig, w0_arr, w1_arr, g0_ig, g1_ig


def compute_accessibility(g_ig, city_ig_idx, pops, alpha=1.0):
    d_mat = np.array(
        g_ig.distances(source=city_ig_idx, target=city_ig_idx, weights="weight"),
        dtype=np.float64,
    )
    pop_arr = np.array(pops, dtype=np.float64)
    i_idx, j_idx = np.triu_indices(len(city_ig_idx), k=1)
    d_vals = d_mat[i_idx, j_idx]
    valid = (d_vals > 0) & (d_vals < UNREACHABLE)
    A = float(
        np.sum(pop_arr[i_idx[valid]] * pop_arr[j_idx[valid]] / d_vals[valid] ** alpha)
    )
    return A, int(valid.sum())


def compute_gravity_bc(g0_ig, city_ig_idx, pops, d0_mat):
    print(f"\n{'='*60}\n  STEP 5 — Gravity-Weighted Edge Betweenness\n{'='*60}")
    t0 = time.time()
    pop_arr = np.array(pops, dtype=np.float64)
    gbc = np.zeros(g0_ig.ecount(), dtype=np.float64)
    n_cities = len(city_ig_idx)
    n_pairs = 0
    for i in range(n_cities):
        targets = city_ig_idx[i + 1 :]
        if not targets:
            continue
        paths = g0_ig.get_shortest_paths(
            city_ig_idx[i], to=targets, weights="weight", output="epath"
        )
        for k, path_edges in enumerate(paths):
            j = i + 1 + k
            d_ij = d0_mat[i, j]
            if 0 < d_ij < UNREACHABLE:
                g_ij = pop_arr[i] * pop_arr[j] / (d_ij**GRAVITY_ALPHA)
                for eidx in path_edges:
                    gbc[eidx] += g_ij
                n_pairs += 1
    print(f"  City pairs traced: {n_pairs:,}  ({time.time()-t0:.1f} s)")
    print(f"  Edges with NI > 0: {(gbc > 0).sum():,} / {g0_ig.ecount():,}")
    return gbc


def compute_scores(w0_arr, w1_arr, gbc):
    cv_arr = np.clip(np.where(w0_arr > 1e-9, w1_arr / w0_arr - 1.0, 0.0), 0.0, None)
    ni_max = gbc.max()
    cv_max = cv_arr.max()
    ni_norm = gbc / ni_max if ni_max > 0 else gbc
    cv_norm = cv_arr / cv_max if cv_max > 0 else cv_arr
    bottleneck = ni_norm * cv_norm
    unpaved_mask = cv_arr > CV_MIN_THRESHOLD
    print(
        f"\n  Climate-affected edges: {unpaved_mask.sum():,} / {len(w0_arr):,} "
        f"({100*unpaved_mask.mean():.1f}%)"
    )
    print(
        f"  CV range: [{cv_arr.min():.3f}, {cv_arr.max():.3f}]  "
        f"median={np.median(cv_arr[unpaved_mask]):.3f}"
    )
    return cv_arr, bottleneck, unpaved_mask


# =============================================================================
# STEP 7 — SAVE EDGE SCORES + 2×2 MATRIX
# =============================================================================
def save_edge_scores(
    edge_list,
    node_list,
    all_nc,
    w0_arr,
    w1_arr,
    gbc,
    cv_arr,
    bottleneck,
    unpaved_mask,
    out_dir,
):
    node_coords = {n: all_nc.get(n, (np.nan, np.nan)) for n in node_list}
    mid_lons = [(node_coords[u][0] + node_coords[v][0]) / 2 for u, v in edge_list]
    mid_lats = [(node_coords[u][1] + node_coords[v][1]) / 2 for u, v in edge_list]

    df = pd.DataFrame(
        {
            "u": [u for u, _ in edge_list],
            "v": [v for _, v in edge_list],
            "mid_lon": mid_lons,
            "mid_lat": mid_lats,
            "w0": w0_arr,
            "w1": w1_arr,
            "NI": gbc,
            "CV": cv_arr,
            "bottleneck": bottleneck,
            "unpaved": unpaved_mask.astype(int),
        }
    )
    sub = df[df["unpaved"] == 1].copy()
    sub["NI_rank"] = sub["NI"].rank(ascending=False, method="min")
    sub["CV_rank"] = sub["CV"].rank(ascending=False, method="min")
    sub["B_rank"] = sub["bottleneck"].rank(ascending=False, method="min")
    df = df.join(sub[["NI_rank", "CV_rank", "B_rank"]])
    df.to_csv(out_dir / "02_edge_scores.csv", index=False)
    print(f"\n  Saved → 02_edge_scores.csv  ({len(df):,} edges)")

    ni_med = np.median(gbc[unpaved_mask])
    cv_med = np.median(cv_arr[unpaved_mask])
    hi_ni, hi_cv = gbc > ni_med, cv_arr > cv_med
    labels = {
        (False, False): "Low NI  × Low CV  (low priority)",
        (False, True): "Low NI  × High CV (climate-vulnerable marginal)",
        (True, False): "High NI × Low CV  (efficiency-critical)",
        (True, True): "High NI × High CV (STRATEGIC BOTTLENECK ★)",
    }
    rows = []
    for (hni, hcv), label in labels.items():
        mask = unpaved_mask & (hi_ni == hni) & (hi_cv == hcv)
        rows.append(
            {
                "quadrant": label,
                "n_edges": int(mask.sum()),
                "pct_unpaved": f"{100*mask.sum()/max(unpaved_mask.sum(),1):.1f}%",
                "mean_NI": float(gbc[mask].mean()) if mask.any() else 0,
                "mean_CV": float(cv_arr[mask].mean()) if mask.any() else 0,
            }
        )
    pd.DataFrame(rows).to_csv(out_dir / "03_2x2_matrix.csv", index=False)
    print("  Saved → 03_2x2_matrix.csv")


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Bottleneck Network Analysis (Steps 1–7)"
    )
    parser.add_argument("--base", default=str(_DEFAULT_BASE))
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force rebuild graph even if checkpoint exists",
    )
    args = parser.parse_args()

    base = Path(args.base)
    roads_dir = base / "RAW" / "Road_data"
    speed_dir = base / "road_speed_cordex"
    pop_dir = base / "RAW" / "Pop_data"
    out_dir = base / "web" / "network_results" / "bottleneck_paving"
    out_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = out_dir / "01_graph_checkpoint.pkl"
    if args.rebuild and checkpoint.exists():
        checkpoint.unlink()
        print("  [--rebuild] Deleted existing checkpoint.")

    # Steps 1–2
    G0, G1, all_nc = build_africa_graph(roads_dir, speed_dir, checkpoint)
    demand_nodes = sample_worldpop_nodes(pop_dir, G0, all_nc)
    if len(demand_nodes) < 10:
        raise RuntimeError("Too few demand nodes — check WorldPop data.")

    # Step 3
    print(f"\n{'='*60}\n  STEP 3 — Build igraph Objects\n{'='*60}")
    node_list, node_idx, edge_list, edges_ig, w0_arr, w1_arr, g0_ig, g1_ig = (
        build_igraphs(G0, G1)
    )
    del G0, G1
    gc.collect()
    print(f"  igraph built: {g0_ig.vcount():,} nodes  {g0_ig.ecount():,} edges")

    # Snap demand nodes to igraph indices
    city_ig_idx, pops = [], []
    for dn in demand_nodes:
        if dn["snap_node"] in node_idx:
            city_ig_idx.append(node_idx[dn["snap_node"]])
            pops.append(dn["pop"])
    print(f"  Demand nodes in LCC: {len(city_ig_idx):,}")

    # Step 4
    print(f"\n{'='*60}\n  STEP 4 — Baseline Accessibility\n{'='*60}")
    A_normal, n_reach = compute_accessibility(g0_ig, city_ig_idx, pops)
    A_extreme, _ = compute_accessibility(g1_ig, city_ig_idx, pops)
    print(f"  A_normal  = {A_normal:.4e}  ({n_reach:,} reachable pairs)")
    print(f"  A_extreme = {A_extreme:.4e}")
    print(
        f"  Climate-driven accessibility loss: {100*(A_normal-A_extreme)/A_normal:.1f}%"
    )

    # Step 5
    d0_mat = np.array(
        g0_ig.distances(source=city_ig_idx, target=city_ig_idx, weights="weight"),
        dtype=np.float64,
    )
    gbc = compute_gravity_bc(g0_ig, city_ig_idx, pops, d0_mat)

    # Step 6
    print(f"\n{'='*60}\n  STEP 6 — Climate Vulnerability + Bottleneck Score\n{'='*60}")
    cv_arr, bottleneck, unpaved_mask = compute_scores(w0_arr, w1_arr, gbc)

    # Step 7
    print(f"\n{'='*60}\n  STEP 7 — Save Edge Scores\n{'='*60}")
    save_edge_scores(
        edge_list,
        node_list,
        all_nc,
        w0_arr,
        w1_arr,
        gbc,
        cv_arr,
        bottleneck,
        unpaved_mask,
        out_dir,
    )

    # Serialise experiment state for paving_experiment.py
    state = {
        "g0_ig": g0_ig,
        "g1_ig": g1_ig,
        "edges_ig": edges_ig,
        "city_ig_idx": city_ig_idx,
        "pops": pops,
        "A_normal": A_normal,
        "A_extreme": A_extreme,
        "gbc": gbc,
        "cv_arr": cv_arr,
        "bottleneck": bottleneck,
        "unpaved_mask": unpaved_mask,
    }
    state_path = out_dir / "experiment_state.pkl"
    with open(state_path, "wb") as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"\n  Saved → experiment_state.pkl")

    # Save lightweight stats for plot_paving.py
    stats = {
        "n_total": g0_ig.ecount(),
        "n_unpaved": int(unpaved_mask.sum()),
        "n_ni_positive": int((gbc > 0).sum()),
    }
    with open(out_dir / "network_stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    print("  Saved → network_stats.json")
    print("\n  Done. Run result3/paving_experiment.py next.")


if __name__ == "__main__":
    main()
