import networkx as nx
import pytest

from recalc.physical_edges import (
    PhysicalEdge,
    build_scenario_multigraphs,
    compare_fixed_and_rerouted,
    minimum_weight_projection,
    physical_edge_id,
)


def test_physical_id_uses_unfiltered_source_row():
    raw_rows = [0, 1, 2, 3]
    surviving_rows = [raw_rows[i] for i in (1, 3)]
    assert [physical_edge_id("Kenya", row) for row in surviving_rows] == [
        "Kenya_road_1",
        "Kenya_road_3",
    ]


def test_parallel_roads_can_switch_under_extreme_conditions():
    roads = [
        PhysicalEdge("A", 0, 1, 1, 1, 0.01),  # baseline 1 h, extreme 100 h
        PhysicalEdge("B", 0, 1, 2, 1, 1),  # baseline 2 h, extreme 2 h
    ]
    g0, g1 = build_scenario_multigraphs(roads)
    assert g0.number_of_edges() == g1.number_of_edges() == 2
    assert set(g0[0][1]) == {"A", "B"}
    assert minimum_weight_projection(g0)[0][1]["physical_edge_id"] == "A"
    assert minimum_weight_projection(g1)[0][1]["physical_edge_id"] == "B"
    comparison = compare_fixed_and_rerouted(roads, 0, 1)
    assert comparison.baseline_hours == pytest.approx(1)
    assert comparison.fixed_route_extreme_hours == pytest.approx(100)
    assert comparison.rerouted_extreme_hours == pytest.approx(2)
    assert comparison.baseline_physical_edge_ids == ("A",)
    assert comparison.rerouted_physical_edge_ids == ("B",)


def test_passability_is_not_applied_twice_to_effective_speed():
    road = PhysicalEdge("r", 0, 1, 30, 60, 30, p_block=0.5)
    assert road.w0_hours == pytest.approx(0.5)
    assert road.w1_hours == pytest.approx(1.0)
    assert compare_fixed_and_rerouted(
        [road], 0, 1
    ).fixed_route_extreme_hours == pytest.approx(1.0)


def test_projection_keeps_winning_edge_length_and_metadata_together():
    slow = PhysicalEdge("slow", 0, 1, 10, 2, 2, p_block=0.7)
    fast = PhysicalEdge("fast", 0, 1, 1, 1, 1, p_block=0.2)
    g0, _ = build_scenario_multigraphs([slow, fast])
    chosen = minimum_weight_projection(g0)[0][1]
    assert chosen["physical_edge_id"] == "fast"
    assert chosen["length_km"] == 1
    assert chosen["p_block"] == pytest.approx(0.2)
    assert chosen["w0_hours"] == pytest.approx(1)


def test_border_connector_is_not_paving_eligible():
    connector = PhysicalEdge(
        "border:1", 0, 1, 0.2, 40, 40, edge_type="border_connector"
    )
    g0, _ = build_scenario_multigraphs([connector])
    assert not g0[0][1]["border:1"]["paving_eligible"]


def test_duplicate_id_or_bad_numeric_inputs_fail_closed():
    edge = PhysicalEdge("x", 0, 1, 1, 1, 1)
    with pytest.raises(ValueError, match="duplicate physical_edge_id"):
        build_scenario_multigraphs([edge, edge])
    with pytest.raises(ValueError, match="v_extreme_effective"):
        PhysicalEdge("y", 0, 1, 1, 1, 0)
    with pytest.raises(ValueError, match="p_block"):
        PhysicalEdge("z", 0, 1, 1, 1, 1, p_block=1.1)
    with pytest.raises(ValueError, match="source_row"):
        physical_edge_id("Kenya", -1)


def test_unreachable_od_remains_explicit():
    with pytest.raises(nx.NetworkXNoPath):
        compare_fixed_and_rerouted(
            [PhysicalEdge("x", 0, 1, 1, 1, 1), PhysicalEdge("y", 2, 3, 1, 1, 1)],
            0,
            2,
        )
