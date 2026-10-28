import math

import networkx as nx
import pandas as pd
import pytest

from hpc.route_decomposition import decompose_od_routes


def _case():
    edges = pd.DataFrame(
        [
            ("slow_extreme", 0, 1, 1.0, 10.0, 10.0),
            ("parallel", 0, 1, 2.0, 2.0, 12.0),
            ("next", 1, 2, 1.0, 1.0, 10.0),
            ("direct", 0, 2, 5.0, 5.0, 40.0),
        ],
        columns=["road_id", "u", "v", "w0", "w1", "length_km"],
    )
    normal = nx.Graph()
    normal.add_edge(0, 1, weight=1.0, road_id="slow_extreme")
    normal.add_edge(1, 2, weight=1.0, road_id="next")
    normal.add_edge(0, 2, weight=5.0, road_id="direct")
    extreme = nx.Graph()
    extreme.add_edge(0, 1, weight=2.0, road_id="parallel")
    extreme.add_edge(1, 2, weight=1.0, road_id="next")
    extreme.add_edge(0, 2, weight=5.0, road_id="direct")
    return normal, extreme, edges


def test_fixed_route_holds_physical_road_not_just_node_path():
    g0, g1, edges = _case()
    out = decompose_od_routes(g0, g1, edges, [{"id": "a", "node": 0}, {"id": "b", "node": 2}])
    assert len(out) == 1
    row = out.iloc[0]
    assert row["baseline_path_road_ids"] == ["slow_extreme", "next"]
    assert row["t_baseline_h"] == 2.0
    assert row["t_fixed_extreme_h"] == 11.0
    assert row["t_rerouted_extreme_h"] == 3.0
    assert row["baseline_path_length_km"] == 20.0
    assert math.isclose(row["direct_path_increase_pct"], 450.0)
    assert math.isclose(row["rerouting_relief_pct_of_fixed"], 100 * 8 / 11)


def test_graph_road_identity_mismatch_is_rejected():
    g0, g1, edges = _case()
    g1[0][1]["road_id"] = "slow_extreme"
    with pytest.raises(ValueError, match="Graph w1 disagrees"):
        decompose_od_routes(g0, g1, edges, [{"id": "a", "node": 0}, {"id": "b", "node": 2}])


def test_same_snapped_node_and_missing_node_are_explicit():
    g0, g1, edges = _case()
    out = decompose_od_routes(g0, g1, edges, [{"id": "a", "node": 0}, {"id": "same", "node": 0}, {"id": "missing", "node": 99}])
    assert set(out["status"]) == {"same_snapped_node", "baseline_unreachable"}
