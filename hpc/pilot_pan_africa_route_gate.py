"""Two-country Pan-Africa C04 engineering pilot; never a final reviewer result.

Rebuilds country graphs from source shapefiles and a versioned speed table. It
does not read any legacy graph pickle, and reproduces the published synthetic
border connector rule only for the two selected neighbouring countries.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from hpc.pan_africa_route_gate import (
    classify_paper_pairs,
    crosswalk_graph_edges,
    validate_paper_od_nodes,
    verified_speed_source_table,
)
from hpc.route_decomposition import decompose_od_routes
from result1 import run_africa_layer as africa


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_legacy_border_connectors(G0: nx.Graph, G1: nx.Graph, borders: list[tuple]) -> int:
    """Mirror ``run_africa_layer.py`` border rule on the pilot subset."""
    tree = cKDTree(np.array([(lon, lat) for _, lon, lat, _ in borders]))
    count = 0
    for i, j in tree.query_pairs(africa.CROSS_BORDER_DIST_DEG):
        ni, x0, y0, ci = borders[i]
        nj, x1, y1, cj = borders[j]
        if ci == cj or G0.has_edge(ni, nj):
            continue
        dist_km = math.hypot(x0 - x1, y0 - y1) * 111.0
        weight = dist_km / africa.CROSS_BORDER_SPEED
        rid = f"synthetic_border_{min(ni, nj)}_{max(ni, nj)}"
        for graph in (G0, G1):
            graph.add_edge(ni, nj, weight=weight, road_id=rid, synthetic=True)
        count += 1
    return count


def run(args: argparse.Namespace) -> dict:
    if args.country_a == args.country_b:
        raise ValueError("Pilot needs two distinct countries")
    if args.output_dir.exists():
        raise FileExistsError("Use a new output directory; never overwrite a pilot")
    with zipfile.ZipFile(args.nodes_zip) as archive:
        nodes = pd.read_csv(io.BytesIO(archive.read("africa_layer/africa_nodes.csv")))
    registry = pd.read_csv(args.registry_csv)
    paper_nodes = validate_paper_od_nodes(nodes, set(registry["speed_country"]))
    countries = [args.country_a, args.country_b]
    pilot_nodes = paper_nodes[paper_nodes["country_folder"].isin(countries)].copy()
    if len(pilot_nodes) < 2 or set(pilot_nodes["country_folder"]) != set(countries):
        raise ValueError("Both pilot countries need a paper OD node")

    africa.ROADS_DIR = args.roads_dir
    africa.SPEED_DIR = args.speed_dir
    graphs = []
    all_coords = {}
    all_border = []
    offset = 0
    input_hashes = {"nodes_zip": sha256(args.nodes_zip), "registry_csv": sha256(args.registry_csv)}
    speed_sources = []
    for country in countries:
        shp = args.roads_dir / country / f"{country}.shp"
        speed = args.speed_dir / f"{country}_road_speed.csv"
        if not shp.is_file() or not speed.is_file():
            raise FileNotFoundError(f"Missing pilot road/speed input for {country}")
        input_hashes[f"{country}_shp"] = sha256(shp)
        input_hashes[f"{country}_speed"] = sha256(speed)
        result = africa.build_country_graph(country, offset)
        if result is None:
            raise ValueError(f"Could not build country graph for {country}")
        g0, g1, coords, border = result
        graphs.append((g0, g1))
        all_coords.update(coords)
        all_border.extend(border)
        offset += len(coords)
        speed_sources.append(verified_speed_source_table(speed))
    G0, G1 = nx.Graph(), nx.Graph()
    for normal, extreme in graphs:
        G0.add_nodes_from(normal.nodes(data=True))
        G0.add_edges_from(normal.edges(data=True))
        G1.add_nodes_from(extreme.nodes(data=True))
        G1.add_edges_from(extreme.edges(data=True))
    n_synthetic = add_legacy_border_connectors(G0, G1, all_border)
    sources = pd.concat(speed_sources, ignore_index=True)
    edge_table = crosswalk_graph_edges(G0, G1, sources)

    snapped = africa.snap_cities(pilot_nodes, all_coords)
    if len(snapped) != len(pilot_nodes):
        raise ValueError("A paper OD city did not snap within 0.5 degrees")
    name_to_id = pilot_nodes.set_index("name")["node_id"].to_dict()
    origins = [{"id": name_to_id[row["city_name"]], "node": row["snap_node"]} for row in snapped]
    pairs = classify_paper_pairs(decompose_od_routes(G0, G1, edge_table, origins), pilot_nodes)
    expected = len(origins) * (len(origins) - 1) // 2
    if len(pairs) != expected:
        raise ValueError(f"Pilot OD pair count {len(pairs)} != {expected}")
    physical_ids = set(edge_table.loc[~edge_table["synthetic"], "road_id"])
    if any(rid.startswith("synthetic_border_") for rid in physical_ids):
        raise ValueError("Synthetic road leaked into physical source")

    args.output_dir.mkdir(parents=True)
    pair_path = args.output_dir / "two_country_route_decomposition.parquet"
    edge_path = args.output_dir / "two_country_graph_edge_crosswalk.parquet"
    report_path = args.output_dir / "two_country_route_gate.json"
    pairs.to_parquet(pair_path, compression="zstd", index=False)
    edge_table.to_parquet(edge_path, compression="zstd", index=False)
    report = {
        "status": "PASS", "scope": "two_country_engineering_pilot_old_speed_not_reviewer_result",
        "countries": countries, "code_commit": args.code_commit,
        "speed_provenance_gate": args.speed_provenance_gate,
        "input_sha256": input_hashes,
        "n_paper_nodes_in_two_countries": len(pilot_nodes),
        "n_od_pairs": len(pairs),
        "n_international_pairs": int(pairs["international"].sum()),
        "n_connected_international_pairs": int((pairs["international"] & (pairs["status"] == "connected")).sum()),
        "od_status_counts": pairs["status"].value_counts().to_dict(),
        "n_normal_graph_edges": G0.number_of_edges(),
        "n_extreme_graph_edges": G1.number_of_edges(),
        "n_crosswalk_physical_ids": len(physical_ids),
        "n_crosswalk_synthetic_ids": int(edge_table["synthetic"].sum()),
        "n_synthetic_border_connectors": n_synthetic,
        "output_sha256": {pair_path.name: sha256(pair_path), edge_path.name: sha256(edge_path)},
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PAN_AFRICA_C04_GATE_PASS countries={countries} pairs={len(pairs)} synthetic={n_synthetic}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roads-dir", type=Path, required=True)
    parser.add_argument("--speed-dir", type=Path, required=True)
    parser.add_argument("--nodes-zip", type=Path, required=True)
    parser.add_argument("--registry-csv", type=Path, required=True)
    parser.add_argument("--country-a", required=True)
    parser.add_argument("--country-b", required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--speed-provenance-gate", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
