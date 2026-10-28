# Pan-African fixed-route decomposition gate (engineering plan)

This is **not** a reviewer-facing recalculation. The current two-country pilot uses the archived speed table only to test graph/OD identity; the formal result must use the new terrain-informed climate-to-speed output and its validated manifest. No legacy graph pickle may be loaded.

## Paper OD and aggregation

- Manuscript: **49 national capitals plus 34 non-capital megacities**. Archived `africa_layer/africa_nodes.csv` has 84 records, including the WestSahara capital with no road result. Exclude that row explicitly: 83 nodes, 49 countries, 3,403 unordered pairs, of which 3,294 are international and 109 domestic before connectivity filtering.
- The old `run_africa_layer.py` computes all unordered city pairs and summarizes them together. For the paper's **international** 36.3% travel-time claim, filter to cross-country, connected pairs, then specify whether the aggregate is the arithmetic mean of pair percentages or the percentage change of mean pair time. Preserve both separately; they are not interchangeable.
- OD identity must use `node_id` and record the country, city type, original coordinates, snapped node, and snap distance. Name-only joins and silent omission at the 0.5° snapping limit fail the gate.

## Physical and synthetic edge identity

- Country graph builders assign road ID **before** length filtering, preserving the speed writer's source-row identity. Normal and extreme simple-graph projections can select different physical parallel roads for the same endpoint pair. Save the `road_id` selected in **each** scenario.
- For each baseline route, fixed-extreme time sums the terrain-informed `length_km/V_extreme` of the **same baseline physical road IDs**. Rerouted-extreme time is a new shortest path using extreme edge weights. Never infer the fixed-route edge from the extreme graph's endpoint pair.
- Cross-border connectors use the old rule (candidate border nodes within 0.2°, connector time `111 × EuclideanDegrees / 40 km/h`), but label IDs `synthetic_border_*`. They have the same weight in both scenarios and must be excluded from climate-exposed *physical-road* speed summaries. Report connector count and aggregate distance separately. This rule is an idealized border model; border-control time is not included.
- `hpc/pan_africa_route_gate.py` rejects stale/mismatched source weights, synthetic-as-physical IDs, scenario topology differences, and missing source road IDs. A formal run must also independently validate the new speed table against the source road rows and provenance.

## Efficient full-49 execution after the terrain gate

1. Produce one versioned compressed terrain/speed input bundle and a SHA-256 manifest. Reuse the already transferred official road RARs on cx3; transfer no per-edge files. Verify all 49 archives and new speed partitions before compute.
2. Run 49 independently restartable country graph-preparation jobs with limited concurrency. Each writes Zstd Parquet: graph-selected edge endpoints/normal/extreme physical IDs and weights, physical `road_id` crosswalk with both scenario weights, nodes/coordinates, border candidates, source/input hashes, and invariant counts. This avoids retaining all GeoDataFrames and intermediate NetworkX graphs in the final process.
3. Verify all 49 per-country manifests, then assemble two graph views with one shared vertex index; add synthetic connectors once and store their crosswalk rows. Use igraph (compact adjacency) for 83-source shortest-path computations, with physical `road_id` on every projected edge. Do **not** use NetworkX 83 repeated whole-continent searches or the old pickle.
4. For each source, get the baseline road-ID sequence for each destination, sum its extreme crosswalk weights, and compute extreme shortest times on the corresponding extreme graph. Save one pair-level Zstd Parquet (including road-ID sequence and status), one edge crosswalk Parquet, 83-node snap table, and SHA-256/definition JSON. Recompute the single-country pilot first on new speeds and compare route identities and invariants, not its old numerical results.
5. Exact gate: 83/49 OD, 3,403 unique unordered pairs, 3,294 international before connectivity filtering; no invalid/missing road IDs, no stale weight; `t_rerouted_extreme <= t_fixed_extreme` for every connected pair; baseline path sum equals baseline shortest time; all synthetic connectors unchanged between scenarios. Record all unreachable/same-node cases and the denominator of each reported summary. Freeze a code commit and input/output hashes before making paper claims.

Suggested PBS request for consolidated graph/OD: start with one 64–128 GiB node and benchmark peak memory/time on 2, then 5 diverse countries; only then run 49. Country partitions can run concurrently (e.g. 4) without 49 full-graph copies. The code bundle and outputs should be moved as a few compressed archives, not thousands of small files.

## Current two-country pilot

Benin + BurkinaFaso source Shapefile/legacy-speed row alignment passed C00. `hpc/pilot_pan_africa_route_gate.py` rebuilds their graphs, merges them with synthetic connectors, loads the paper OD ZIP, and tests physical/connector crosswalks and fixed-versus-rerouted decomposition. This pilot is a **GO/NO-GO for implementation only**, not a published effect estimate. Its PBS script is `hpc/pbs_pan_africa_route_gate_two_country.pbs`.
