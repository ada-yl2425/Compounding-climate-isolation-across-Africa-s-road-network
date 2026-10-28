"""Isolated formula checks for the archived TGR diagnostic, not formal C07."""

import numpy as np
import pandas as pd

from hpc.audit_legacy_tgr_sources import (
    audit_node_table,
    baseline_group_means,
    weighted_step_quantile,
)


def test_weighted_step_quantile_uses_population_first_crossing():
    values = np.array([1.0, 2.0, 100.0])
    weights = np.array([1.0, 8.0, 1.0])
    assert weighted_step_quantile(values, weights, 0.50) == 2.0
    assert weighted_step_quantile(values, weights, 0.90) == 2.0


def test_baseline_groups_are_not_delta_quantiles():
    t0 = np.arange(1.0, 11.0)
    delta = np.arange(10.0, 0.0, -1.0)
    weights = np.ones(10)
    mid, upper, n_mid, n_upper = baseline_group_means(t0, delta, weights)
    assert (n_mid, n_upper) == (3, 2)
    assert mid == 6.0
    assert upper == 1.5


def test_zero_median_delta_keeps_tgr_undefined_not_one():
    frame = pd.DataFrame(
        {
            "t_normal": [1.0] * 10,
            "t_extreme": [1.0] * 8 + [2.0] * 2,
            "population": [1.0] * 10,
        }
    )
    result = audit_node_table(frame)
    assert result["p50_delta_weighted_h"] == 0
    assert result["p90_delta_weighted_h"] == 1
    assert np.isnan(result["tail_ratio_delta_weighted"])
    assert result["n_nodes_valid"] == 10
