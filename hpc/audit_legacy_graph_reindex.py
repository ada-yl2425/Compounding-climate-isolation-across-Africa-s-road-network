"""Quantify speed-table misjoins caused by post-filter graph renumbering.

The legacy graph code filters unpaved source roads to >=0.1 km, resets the
index, and constructs ``<country>_road_<new index>``.  Its speed table was
numbered before filtering at >=0.05 km.  Given a full-alignment-certified
speed CSV in original source order, this audit computes the implied join
outcomes without building the graph or rerunning the climate model.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_row_from_id(road_id: str, country: str) -> int:
    match = re.fullmatch(re.escape(country) + r"_road_([0-9]+)", road_id)
    if not match:
        raise ValueError(f"malformed road_id: {road_id!r}")
    return int(match.group(1))


def join_counts(
    source_rows_and_lengths: list[tuple[int, float]], min_graph_km: float = 0.1
) -> dict:
    if not math.isfinite(min_graph_km) or min_graph_km <= 0:
        raise ValueError("min_graph_km must be positive and finite")
    ordered = sorted(source_rows_and_lengths)
    if len({source_row for source_row, _ in ordered}) != len(ordered):
        raise ValueError("duplicate source road row")
    if any(not math.isfinite(length) or length <= 0 for _, length in ordered):
        raise ValueError("lengths must be positive and finite")
    speed_length_by_source_row = dict(ordered)
    graph_source = [(row, length) for row, length in ordered if length >= min_graph_km]
    correct = wrong = default = wrong_large_length_gap = 0
    examples: dict[str, list] = {"correct": [], "wrong": [], "default": []}
    for graph_index, (source_row, actual_length) in enumerate(graph_source):
        attached_length = speed_length_by_source_row.get(graph_index)
        if attached_length is None:
            default += 1
            if len(examples["default"]) < 10:
                examples["default"].append({"graph_index": graph_index, "source_row": source_row})
        elif graph_index == source_row:
            correct += 1
            if len(examples["correct"]) < 10:
                examples["correct"].append({"graph_index": graph_index, "source_row": source_row})
        else:
            wrong += 1
            if abs(attached_length / actual_length - 1) > 0.1:
                wrong_large_length_gap += 1
            if len(examples["wrong"]) < 10:
                examples["wrong"].append({
                    "graph_index": graph_index,
                    "source_row": source_row,
                    "attached_speed_source_row": graph_index,
                    "actual_length_km": actual_length,
                    "attached_speed_source_length_km": attached_length,
                })
    assert correct + wrong + default == len(graph_source)
    return {
        "legacy_speed_rows": len(ordered),
        "graph_edges_after_0_1_km_filter": len(graph_source),
        "correct_physical_road_speed_join": correct,
        "wrong_physical_road_speed_join": wrong,
        "default_speed_fallback": default,
        "wrong_join_length_gap_over_10pct": wrong_large_length_gap,
        "examples": examples,
    }


def audit_zip(zip_path: Path, member: str, country: str) -> dict:
    pairs: list[tuple[int, float]] = []
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(member) as binary:
            reader = csv.DictReader(io.TextIOWrapper(binary, encoding="utf-8-sig", newline=""))
            for row in reader:
                pairs.append((source_row_from_id(row["road_id"], country), float(row["length_km"])))
    result = join_counts(pairs)
    return {
        "scope": "legacy_graph_reindex_diagnostic_not_new_scientific_result",
        "country": country,
        "source_zip": str(zip_path),
        "source_zip_sha256": sha256(zip_path),
        "source_member": member,
        "graph_code": "result1/network_pipeline.py:104-129",
        "speed_code": "data_procession/compute_road_speed.py:267-296",
        "precondition": "full source-to-speed identity audit PASS for this country",
        **result,
        "note": "Counts are implied by the published code and certified old speed IDs, assuming the graph read the same source road ordering. This does not quantify final OD or health metric error.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--member", required=True)
    parser.add_argument("--country", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit_zip(args.zip, args.member, args.country)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "legacy_speed_rows", "graph_edges_after_0_1_km_filter",
        "correct_physical_road_speed_join", "wrong_physical_road_speed_join",
        "default_speed_fallback", "wrong_join_length_gap_over_10pct"
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
