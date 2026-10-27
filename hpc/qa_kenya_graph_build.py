"""Engineering-only graph build QA; does not compute manuscript metrics."""

import argparse
import contextlib
import hashlib
import io
import json
import math
import re
import resource
import sys
import time
from pathlib import Path

import pandas as pd

from result1.network_pipeline import build_graphs_from_shp


class _Tee(io.StringIO):
    def write(self, value):
        sys.__stdout__.write(value)
        return super().write(value)


def parse_build_counts(log, route_edges):
    """Derive parallel collapses from the builder's own per-feature counters."""
    filtered = re.search(r"Filtered segments:\s*([\d,]+)", log)
    completion = re.search(r"Fill=([\d,]+)\s+Skip=([\d,]+)", log)
    if not filtered or not completion:
        raise ValueError("Could not parse graph builder feature counters")
    filtered_count = int(filtered.group(1).replace(",", ""))
    fill_count = int(completion.group(1).replace(",", ""))
    skip_count = int(completion.group(2).replace(",", ""))
    candidates = filtered_count - skip_count
    parallel_collapses = candidates - route_edges
    if parallel_collapses < 0:
        raise ValueError("Graph has more edges than non-skipped road candidates")
    return {
        "filtered_unpaved_segments": filtered_count,
        "skipped_geometry_or_selfloop_segments": skip_count,
        "speed_fill_segments": fill_count,
        "candidate_road_segments": candidates,
        "parallel_segments_collapsed": parallel_collapses,
    }


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_graph(G0, G1, G_conn, edges, speed_ids):
    """Compare the collapsed route graph with the materialized edge table."""
    result = {
        "nodes": G0.number_of_nodes(),
        "route_edges": G0.number_of_edges(),
        "connectivity_edges": G_conn.number_of_edges(),
        "edge_table_rows": len(edges),
        "edge_table_duplicate_road_ids": int(edges.road_id.duplicated().sum()),
        "selected_road_id_missing_from_speed": 0,
        "normal_graph_table_road_id_mismatch": 0,
        "normal_graph_table_weight_mismatch": 0,
        "extreme_graph_table_weight_mismatch": 0,
        "nonfinite_nonpositive_normal_weight": 0,
        "nonfinite_nonpositive_extreme_weight": 0,
    }
    for row in edges.itertuples(index=False):
        normal = G0[row.u][row.v]
        extreme = G1[row.u][row.v]
        result["selected_road_id_missing_from_speed"] += row.road_id not in speed_ids
        result["normal_graph_table_road_id_mismatch"] += normal.get("road_id") != row.road_id
        result["normal_graph_table_weight_mismatch"] += not math.isclose(
            normal["weight"], row.w0, rel_tol=1e-10, abs_tol=1e-12
        )
        result["extreme_graph_table_weight_mismatch"] += not math.isclose(
            extreme["weight"], row.w1, rel_tol=1e-10, abs_tol=1e-12
        )
        result["nonfinite_nonpositive_normal_weight"] += not (
            math.isfinite(normal["weight"]) and normal["weight"] > 0
        )
        result["nonfinite_nonpositive_extreme_weight"] += not (
            math.isfinite(extreme["weight"]) and extreme["weight"] > 0
        )
    result["edge_table_matches_route_graph"] = (
        result["route_edges"] == result["edge_table_rows"]
        and result["normal_graph_table_road_id_mismatch"] == 0
        and result["normal_graph_table_weight_mismatch"] == 0
        and result["extreme_graph_table_weight_mismatch"] == 0
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shp", required=True, type=Path)
    parser.add_argument("--speed", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-rar", type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    speed = pd.read_csv(args.speed, usecols=["road_id"])
    speed_ids = set(speed.road_id)
    stream = _Tee()
    with contextlib.redirect_stdout(stream):
        G0, G1, G_conn, edges, _ = build_graphs_from_shp(args.shp, args.speed)
    result = audit_graph(G0, G1, G_conn, edges, speed_ids)
    result.update(parse_build_counts(stream.getvalue(), G0.number_of_edges()))
    result.update({
        "kind": "engineering_graph_build_qa_only",
        "country": "Kenya",
        "source_rar_sha256": sha256_file(args.source_rar) if args.source_rar else None,
        "speed_csv_sha256": sha256_file(args.speed),
        "speed_rows": int(len(speed)),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
