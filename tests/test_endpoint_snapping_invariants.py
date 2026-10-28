"""Road identity invariants for the unchanged 0.0045-degree snap rule."""

import numpy as np

from result1.network_pipeline import _merge_endpoints


def test_transitive_chain_cannot_collapse_both_ends_of_one_road():
    # Road 0's two endpoints are within the snap distance of different ends
    # of road 1; naive union-find joins the ends indirectly into a self-loop.
    points = np.array([[0.0, 0.0], [0.006, 0.0],
                       [0.003, 0.0], [0.003, 0.0001]])
    node_ids, _ = _merge_endpoints(points, {(0, 1), (2, 3)}, 0.0045)
    assert node_ids[0] != node_ids[1]
    assert node_ids[2] != node_ids[3]


def test_coincident_endpoints_of_same_road_stay_distinct():
    points = np.array([[0.0, 0.0], [0.0, 0.0]])
    node_ids, _ = _merge_endpoints(points, {(0, 1)}, 0.0045)
    assert node_ids == [0, 1]


def test_distinct_roads_can_still_snap_nearby_endpoints():
    points = np.array([[0.0, 0.0], [0.01, 0.0],
                       [0.0101, 0.0], [0.02, 0.0]])
    node_ids, _ = _merge_endpoints(points, {(0, 1), (2, 3)}, 0.0045)
    assert node_ids[1] == node_ids[2]
    assert node_ids[0] != node_ids[1]
    assert node_ids[2] != node_ids[3]
