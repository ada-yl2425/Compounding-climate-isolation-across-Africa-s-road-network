"""One-country C04 engineering/scientific pilot using a frozen road-speed table.

The output is explicitly provisional until the climate/IRI gate and OD node
selection are frozen. It never overwrites submitted or legacy results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from hpc.route_decomposition import decompose_od_routes
from result1.network_pipeline import (
    build_graphs_from_shp,
    extract_lcc,
    snap_cities_to_network,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(args: argparse.Namespace) -> dict:
    for path in (args.shp, args.speed, args.cities):
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(path)
    city_df = pd.read_csv(args.cities)
    if not {"country_folder", "city_name", "lon", "lat"} <= set(city_df.columns):
        raise ValueError("City input lacks country/name/coordinate fields")
    if set(city_df["country_folder"].dropna()) != {args.country}:
        raise ValueError("City file contains another country or no city rows")
    if city_df["city_name"].duplicated().any():
        raise ValueError("City names must be unique for OD identity")

    G0, G1, Gc, physical_edges, coords = build_graphs_from_shp(args.shp, args.speed)
    G0, G1, Gc, physical_edges, coords = extract_lcc(G0, G1, Gc, physical_edges, coords)
    snapped = snap_cities_to_network(city_df, G0, coords, country_filter=args.country)
    if len(snapped) != len(city_df):
        raise ValueError("A city was silently omitted during network snapping")
    origins = [{"id": item["city_name"], "node": item["snap_node"]} for item in snapped]
    pairs = decompose_od_routes(G0, G1, physical_edges, origins)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pairs_path = args.output_dir / f"{args.country}_route_decomposition.parquet"
    report_path = args.output_dir / f"{args.country}_route_decomposition_qc.json"
    if pairs_path.exists() or report_path.exists():
        raise FileExistsError("Pilot outputs already exist; use a new run directory")
    pairs.to_parquet(pairs_path, index=False, compression="zstd")
    status_counts = pairs["status"].value_counts().to_dict()
    connected = pairs[pairs["status"] == "connected"]
    report = {
        "status": "PASS" if len(pairs) == len(snapped) * (len(snapped) - 1) // 2 else "FAIL",
        "scope": "provisional_one_country_C04_pilot_not_final_review_result",
        "country": args.country,
        "code_commit": args.code_commit,
        "input_sha256": {str(p): sha256(p) for p in (args.shp, args.speed, args.cities)},
        "n_city_input": len(city_df),
        "n_city_snapped": len(snapped),
        "n_od_pairs": len(pairs),
        "od_status_counts": status_counts,
        "max_legacy_city_snap_dist_km": max((float(s["snap_dist_km"]) for s in snapped), default=None),
        "n_graph_nodes": G0.number_of_nodes(),
        "n_route_edges_normal": G0.number_of_edges(),
        "n_route_edges_extreme": G1.number_of_edges(),
        "n_physical_edges": len(physical_edges),
        "connected_mean_t_baseline_h": float(connected["t_baseline_h"].mean()) if len(connected) else None,
        "connected_mean_t_fixed_extreme_h": float(connected["t_fixed_extreme_h"].mean()) if len(connected) else None,
        "connected_mean_t_rerouted_extreme_h": float(connected["t_rerouted_extreme_h"].mean()) if len(connected) else None,
        "output_parquet": str(pairs_path),
        "output_parquet_sha256": sha256(pairs_path),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"C04_PILOT_{report['status']} country={args.country} pairs={len(pairs)}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shp", type=Path, required=True)
    parser.add_argument("--speed", type=Path, required=True)
    parser.add_argument("--cities", type=Path, required=True)
    parser.add_argument("--country", required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    result = run(parser.parse_args())
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
