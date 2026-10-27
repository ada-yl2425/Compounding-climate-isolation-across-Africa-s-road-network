"""Guard the five legacy graph builders against post-filter ID renumbering."""

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BUILDERS = (
    ("result1/network_pipeline.py", "build_graphs_from_shp"),
    ("result1/run_africa_layer.py", "build_country_graph"),
    ("data_procession/bottleneck_network.py", "_build_country_graph"),
    ("data_procession/compute_health_accessibility.py", "build_graphs"),
    ("result2/network_buffering_decomposition.py", "build_graphs"),
)


@pytest.mark.parametrize("filename,function_name", BUILDERS)
def test_road_id_is_assigned_before_filter_reset(filename, function_name):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    id_assignments = [
        node.lineno for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "gdf"
            and isinstance(target.slice, ast.Constant)
            and target.slice.value == "road_id"
            for target in node.targets
        )
    ]
    reset_calls = [
        node.lineno for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "reset_index"
    ]
    assert len(id_assignments) == 1
    assert reset_calls
    assert id_assignments[0] < min(reset_calls)
