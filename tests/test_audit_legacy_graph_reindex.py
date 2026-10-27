import pytest

from hpc.audit_legacy_graph_reindex import join_counts, source_row_from_id


def test_graph_renumber_joins_wrong_or_defaults_after_source_gaps():
    outcome = join_counts([(0, 0.2), (8, 0.2), (12, 0.2)])
    assert outcome["graph_edges_after_0_1_km_filter"] == 3
    assert outcome["correct_physical_road_speed_join"] == 1
    assert outcome["wrong_physical_road_speed_join"] == 0
    assert outcome["default_speed_fallback"] == 2


def test_short_speed_road_can_be_misjoined_to_graph_edge():
    outcome = join_counts([(0, 0.06), (1, 0.3), (2, 0.3)])
    assert outcome["graph_edges_after_0_1_km_filter"] == 2
    assert outcome["correct_physical_road_speed_join"] == 0
    assert outcome["wrong_physical_road_speed_join"] == 2
    assert outcome["default_speed_fallback"] == 0


def test_bad_road_ids_and_duplicates_fail_closed():
    assert source_row_from_id("Kenya_road_8", "Kenya") == 8
    with pytest.raises(ValueError):
        source_row_from_id("Uganda_road_8", "Kenya")
    with pytest.raises(ValueError):
        join_counts([(0, 1), (0, 2)])
