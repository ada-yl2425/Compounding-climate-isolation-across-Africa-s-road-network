# C10–C12 physical-road intervention gate (2026-10-28)

Status: **NO-GO for formal Reviewer 1/2 bottleneck, percolation and paving numbers** until the terrain-corrected speed table and physical-road intervention mapping exist. This is an engineering audit, not a new paper result.

## Verified code behavior

1. `result1/network_pipeline.py` builds `G_conn` as a simple `nx.Graph`, but its `df_edges` retains every physical segment. Parallel segments have the same `(u, v)`. `identify_critical_roads` calls `nx.bridges(G_conn)` and reports node-pair bridges. A pair with two physical roads can therefore be a graph bridge while neither road alone is a physical bridge. `save_critical_roads` emits only the selected `G0[u][v].road_id`, not all roads on the pair.
2. `percolation_analysis` overwrites `epb[(u,v)]` and `edv[(u,v)]` for every physical segment on that pair, then ranks/removes simple-graph edges. The retained climate score is last-row-dependent, and the removal fraction uses the number of unique endpoint pairs, not physical road count. Reversing input row order can change the result.
3. `data_procession/bottleneck_network.py` independently uses a simple `nx.Graph`. On parallel segments, its country graph updates both G0 and G1 only when a new segment improves **G0**. G1 therefore need not have the smallest available extreme weight. The pan-Africa checkpoint and igraph then inherit that projection.
4. `result3/paving_experiment.py` changes one igraph edge's G1 weight directly to that edge's G0 weight. The experiment state has no selected physical `road_id`. If G0 and G1 fastest roads differ, this change is not a defined physical paving action. Correct physical restoration is `w1(selected road_id) <- w0(selected road_id)`, followed by taking the minimum of *all* parallel roads for that endpoint pair. The routing graph can remain simple for shortest paths, but the physical-road inventory and route-pair mapping must be retained.
5. The old `02_edge_scores.csv` contains `(u, v), NI, CV, bottleneck, unpaved` but no `road_id` or `length_km`. The old `experiment_state.pkl` stores graph-edge arrays and scores without physical road IDs or lengths. Hence neither source alone can establish the exact length of the approximately 767 selected physical roads in C11; `(u,v)` may map to multiple roads.
6. The random strategy is fixed to `N_RANDOM_TRIALS=5` and RNG seed 42. `04_paving_experiment.csv` saves only mean and population-standard-deviation-like `np.std` of the five recovery rates; it does not save per-trial selections or recoveries. Its uncertainty interval cannot be recovered from mean and SD alone. `sensitivity/bottleneck_recovery_sensitivity.py` also uses five trials.

## Minimum implementation before large batch

- Freeze one terrain-corrected road-speed inventory with stable `road_id`, geometry, `length_km`, `w0`, `w1`, country and source hashes; derive endpoint IDs from the corrected graph. Keep an explicit `road_id -> (u,v)` table and all parallel roads.
- For routing, project `min(w0)` and `min(w1)` **independently** per `(u,v)`; retain the selected physical road ID for each state and assert the projection against the inventory. Do not rely on the old pan-Africa checkpoint.
- Define the intervention budget explicitly. To preserve the old paper comparison, report the historical graph-edge fraction separately; for a physical-road intervention, select specific `road_id`s, count physical roads, and calculate exact selected kilometres. Do not imply that either is an investment-cost estimate.
- For NI/CV strategy, score at a clearly stated unit (physical road or route pair). If the score is route-pair-level, use a deterministic, recorded rule to choose a physical road for treatment. After each selected road is restored, re-project that pair and then recompute the same OD accessibility objective. For NI-only and combined, use identical candidate inventory, budget, OD set and normalization denominator.
- For bridges/percolation, operate on a multigraph or maintain pair multiplicity and remove one physical road at a time, updating connectivity only when the last road on a pair is gone. Persist the scored physical-road order, removal fraction denominator and curve. The old simple-graph bridge/percolation outputs cannot be interpreted as physical-road vulnerability without this change.
- Re-run random baselines with independent recorded seeds and save each trial's selected road IDs or a reproducible selection hash, recovery, numerator/denominator and budget. Save summary mean/median and empirical interval in separate CSV. Five trials are too few for a stable lower-tail interval; choose the repetition count before looking at results.

## Automated gate and evidence

`hpc/intervention_gate.py` and `tests/test_intervention_gate.py` cover unique stable IDs, positive lengths/weights, independent normal/extreme projection, a false physical bridge from two parallel roads, exact selected-road length, and re-projection after restoration. They are preflight checks, not the full C10–C12 algorithm.

- Local: `python -m pytest -q tests/test_intervention_gate.py` → **5 passed**.
- cx3 isolated directory: `/rds/general/user/yl2425/ephemeral/africa_pavement_recalc/intervention-gate-20261028/`; same tests under the project venv with cluster geospatial modules → **5 passed in 8.76 s**. Source/test SHA-256 match local: `2e5e860648ce5a13de821bbd877a647aabef78ae95cb1b58ee687472118bbf07` / `dd37f9e3bf3cf5fb0c01406ecaa2bbcde2d51cf89841cb34cd69c6ca8f12395d`.
- No formal paper metric was computed or approved by this gate. Next pilot should use one corrected-country physical-road table, then two to three morphologically different countries, before the 49-country batch.
