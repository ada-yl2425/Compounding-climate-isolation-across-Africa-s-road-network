"""Identity-preserving road weights and a small fixed-route comparison.

This is an opt-in foundation for new analyses, not a patch to legacy outputs.
``v_normal_effective`` and ``v_extreme_effective`` must already include any
passability factor adopted by the speed model. ``p_block`` is metadata and is
never applied a second time to travel time here.

Each PhysicalEdge represents one source road feature (or one explicit
synthetic connector). Parallel features remain distinct. Source row numbers
must refer to the unfiltered source file, so an intervening surface or length
filter cannot change a physical edge's identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Hashable, Iterable, Literal

import networkx as nx

Scenario = Literal["normal", "extreme"]


def physical_edge_id(country: str, source_row: int) -> str:
    """Return the legacy-compatible ID assigned before any road filtering."""
    if (
        not country
        or country.strip() != country
        or not country.replace("_", "").isalnum()
    ):
        raise ValueError("country must be a nonempty folder name without spaces")
    if (
        isinstance(source_row, bool)
        or not isinstance(source_row, int)
        or source_row < 0
    ):
        raise ValueError("source_row must be a nonnegative integer")
    return f"{country}_road_{source_row}"


@dataclass(frozen=True, slots=True)
class PhysicalEdge:
    physical_edge_id: str
    u: Hashable
    v: Hashable
    length_km: float
    v_normal_effective: float
    v_extreme_effective: float
    p_block: float = 0.0
    edge_type: str = "road"

    def __post_init__(self) -> None:
        if not self.physical_edge_id:
            raise ValueError("physical_edge_id is required")
        if self.u == self.v:
            raise ValueError("self-loop road edges are not supported")
        for name in ("length_km", "v_normal_effective", "v_extreme_effective"):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not isfinite(self.p_block) or not 0 <= self.p_block <= 1:
            raise ValueError("p_block must be in [0, 1]")
        if self.edge_type not in ("road", "border_connector"):
            raise ValueError("edge_type must be road or border_connector")

    @property
    def w0_hours(self) -> float:
        return self.length_km / self.v_normal_effective

    @property
    def w1_hours(self) -> float:
        return self.length_km / self.v_extreme_effective

    @property
    def paving_eligible(self) -> bool:
        return self.edge_type == "road"


def build_scenario_multigraphs(
    edges: Iterable[PhysicalEdge],
) -> tuple[nx.MultiGraph, nx.MultiGraph]:
    """Build aligned scenario graphs keyed by immutable physical-edge ID."""
    normal, extreme = nx.MultiGraph(), nx.MultiGraph()
    seen: set[str] = set()
    for edge in edges:
        if edge.physical_edge_id in seen:
            raise ValueError(f"duplicate physical_edge_id: {edge.physical_edge_id}")
        seen.add(edge.physical_edge_id)
        common = {
            "physical_edge_id": edge.physical_edge_id,
            "length_km": edge.length_km,
            "p_block": edge.p_block,
            "edge_type": edge.edge_type,
            "paving_eligible": edge.paving_eligible,
            "w0_hours": edge.w0_hours,
            "w1_hours": edge.w1_hours,
        }
        normal.add_edge(
            edge.u, edge.v, key=edge.physical_edge_id, weight=edge.w0_hours, **common
        )
        extreme.add_edge(
            edge.u, edge.v, key=edge.physical_edge_id, weight=edge.w1_hours, **common
        )
    return normal, extreme


def minimum_weight_projection(graph: nx.MultiGraph) -> nx.Graph:
    """Make a routing-only simple graph, retaining each winner's exact ID.

    Project each scenario separately: its fastest parallel road may differ.
    Ties are resolved by physical-edge ID for reproducibility.
    """
    projected = nx.Graph()
    projected.add_nodes_from(graph.nodes(data=True))
    for u, v, key, data in graph.edges(keys=True, data=True):
        candidate = (float(data["weight"]), str(key))
        if projected.has_edge(u, v):
            incumbent = (projected[u][v]["weight"], projected[u][v]["physical_edge_id"])
            if candidate >= incumbent:
                continue
        projected.add_edge(u, v, **dict(data))
    return projected


@dataclass(frozen=True, slots=True)
class RouteComparison:
    baseline_hours: float
    fixed_route_extreme_hours: float
    rerouted_extreme_hours: float
    baseline_physical_edge_ids: tuple[str, ...]
    rerouted_physical_edge_ids: tuple[str, ...]


def compare_fixed_and_rerouted(
    edges: Iterable[PhysicalEdge], origin: Hashable, destination: Hashable
) -> RouteComparison:
    """Compare identical OD with a fixed baseline path and extreme rerouting.

    Raises NetworkXNoPath for unreachable OD. This small reference
    implementation is for fixtures/pilots, not continent-scale all-pairs runs.
    """
    normal_multi, extreme_multi = build_scenario_multigraphs(edges)
    g0 = minimum_weight_projection(normal_multi)
    g1 = minimum_weight_projection(extreme_multi)
    baseline_path = nx.shortest_path(g0, origin, destination, weight="weight")
    extreme_path = nx.shortest_path(g1, origin, destination, weight="weight")

    def path_edge_ids(graph: nx.Graph, path: list[Hashable]) -> tuple[str, ...]:
        return tuple(graph[u][v]["physical_edge_id"] for u, v in zip(path, path[1:]))

    baseline_ids = path_edge_ids(g0, baseline_path)
    extreme_ids = path_edge_ids(g1, extreme_path)
    fixed_hours = sum(
        g0[u][v]["w1_hours"] for u, v in zip(baseline_path, baseline_path[1:])
    )
    return RouteComparison(
        baseline_hours=nx.path_weight(g0, baseline_path, "weight"),
        fixed_route_extreme_hours=fixed_hours,
        rerouted_extreme_hours=nx.path_weight(g1, extreme_path, "weight"),
        baseline_physical_edge_ids=baseline_ids,
        rerouted_physical_edge_ids=extreme_ids,
    )
