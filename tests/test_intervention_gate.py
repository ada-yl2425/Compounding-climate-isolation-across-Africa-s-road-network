import networkx as nx
import pandas as pd
import pytest

from hpc.intervention_gate import (
    audit_physical_road_projection,
    projected_weights_after_restoration,
    summarize_selected_road_lengths,
)


def _graphs():
    g0 = nx.Graph()
    g1 = nx.Graph()
    gc = nx.Graph()
    g0.add_edge(1, 2, weight=1.0, road_id="a")
    g1.add_edge(1, 2, weight=2.0, road_id="b")
    gc.add_edge(1, 2)
    return g0, g1, gc


def _roads():
    return pd.DataFrame(
        [
            {"road_id": "a", "u": 1, "v": 2, "w0": 1.0, "w1": 5.0, "length_km": 2.0},
            {"road_id": "b", "u": 2, "v": 1, "w0": 2.0, "w1": 2.0, "length_km": 3.0},
        ]
    )


def test_parallel_roads_are_not_a_physical_bridge():
    result = audit_physical_road_projection(_roads(), *_graphs())
    assert result["routing_projection_pass"] is True
    assert result["physical_bridge_and_percolation_pass"] is False
    assert result["n_collapsed_roads"] == 1
    assert result["n_false_physical_bridges_if_simple_graph"] == 1


def test_extreme_projection_must_pick_its_own_fastest_road():
    g0, g1, gc = _graphs()
    g1[1][2]["weight"] = 5.0
    g1[1][2]["road_id"] = "a"
    result = audit_physical_road_projection(_roads(), g0, g1, gc)
    assert result["routing_projection_pass"] is False
    assert result["extreme_weight_mismatches"] == [(1, 2)]


def test_length_summary_uses_selected_road_id_not_endpoint_pair():
    summary = summarize_selected_road_lengths(_roads(), ["b"])
    assert summary == {
        "n_roads": 1,
        "total_length_km": 3.0,
        "mean_length_km": 3.0,
        "median_length_km": 3.0,
    }
    with pytest.raises(ValueError, match="missing"):
        summarize_selected_road_lengths(_roads(), ["unknown"])


def test_duplicate_physical_ids_rejected():
    roads = _roads()
    roads.loc[1, "road_id"] = "a"
    with pytest.raises(ValueError, match="unique"):
        audit_physical_road_projection(roads, *_graphs())


def test_restoring_one_physical_road_reprojects_parallel_minimum():
    roads = _roads()
    # At extreme, b is currently faster (2 h). Paving a changes a to 1 h.
    assert projected_weights_after_restoration(roads, []) == {(1, 2): 2.0}
    assert projected_weights_after_restoration(roads, ["a"]) == {(1, 2): 1.0}
    # Paving b has no effect: a still takes 5 h; b already takes 2 h.
    assert projected_weights_after_restoration(roads, ["b"]) == {(1, 2): 2.0}
