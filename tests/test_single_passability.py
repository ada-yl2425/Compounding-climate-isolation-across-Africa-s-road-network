"""Single passability factor in old graph builders and future CV analyses."""

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from result3.bottleneck_stability import compute_future_cv as future_cv
from sensitivity.rcp85_future_stability import compute_future_cv as rcp85_cv


ROOT = Path(__file__).resolve().parents[1]
GRAPH_BUILDERS = (
    "result1/network_pipeline.py",
    "result1/run_africa_layer.py",
    "data_procession/bottleneck_network.py",
    "data_procession/compute_health_accessibility.py",
    "result2/network_buffering_decomposition.py",
)


@pytest.mark.parametrize("filename", GRAPH_BUILDERS)
def test_old_graph_extreme_weight_does_not_apply_passability_twice(filename):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    assignments = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "w1" for target in node.targets)
    ]
    assert len(assignments) == 1
    expression = assignments[0].value
    assert isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Div)
    assert isinstance(expression.left, ast.Name) and expression.left.id == "lkm"
    assert isinstance(expression.right, ast.Name) and expression.right.id == "V_e"


def test_future_cv_ignores_p_block_already_in_effective_speed():
    edges = pd.DataFrame({"CV": [0.0]})
    roads = pd.DataFrame({"V_normal": [60.0], "V_extreme": [30.0], "p_block": [0.5]})
    assert future_cv(edges, roads, pd.Series([0]))[0] == pytest.approx(1.0)
    arrays = {"V_normal": np.array([60.0]), "V_extreme": np.array([30.0]),
              "p_block": np.array([0.5])}
    assert rcp85_cv(np.array([0.0]), arrays, np.array([0]))[0] == pytest.approx(1.0)
