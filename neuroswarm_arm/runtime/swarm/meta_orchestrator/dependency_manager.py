"""Dependency tracking for workflow nodes and barriers."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Iterable

from neuroswarm_arm.runtime.swarm.task_graph.dag import DAGAnalyzer
from neuroswarm_arm.runtime.swarm.task_graph.enums import EdgeKind

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.swarm.task_graph.graph import TaskGraph


class DependencyManager:
    """Track predecessors / successors and join-barrier membership."""

    def __init__(self, graph: TaskGraph) -> None:
        self.graph = graph
        self._analyzer = DAGAnalyzer(graph)
        self._adj: dict[str, list[str]] = defaultdict(list)
        self._rev: dict[str, list[str]] = defaultdict(list)
        self._conditional: dict[tuple[str, str], dict] = {}
        for edge in graph.edges:
            if edge.kind in {EdgeKind.SOFT, EdgeKind.PRIORITY}:
                continue
            self._adj[edge.src].append(edge.dst)
            self._rev[edge.dst].append(edge.src)
            if edge.kind == EdgeKind.CONDITIONAL or edge.condition:
                self._conditional[(edge.src, edge.dst)] = dict(edge.condition or {})
        for nid in graph.nodes:
            self._adj.setdefault(nid, [])
            self._rev.setdefault(nid, [])

    @property
    def analyzer(self) -> DAGAnalyzer:
        return self._analyzer

    def predecessors(self, node_id: str) -> list[str]:
        return list(self._rev.get(node_id, []))

    def successors(self, node_id: str) -> list[str]:
        return list(self._adj.get(node_id, []))

    def hard_predecessors_satisfied(
        self, node_id: str, completed: Iterable[str], *, skipped: Iterable[str] = ()
    ) -> bool:
        done = set(completed) | set(skipped)
        return all(p in done for p in self.predecessors(node_id))

    def barriers(self) -> list[dict[str, object]]:
        return self._analyzer.dependency_barriers()

    def is_barrier(self, node_id: str) -> bool:
        return len(self.predecessors(node_id)) > 1

    def barrier_width(self, node_id: str) -> int:
        return len(self.predecessors(node_id))

    def conditional_edge(self, src: str, dst: str) -> dict | None:
        return self._conditional.get((src, dst))

    def unresolved_predecessors(self, node_id: str, completed: Iterable[str]) -> list[str]:
        done = set(completed)
        return [p for p in self.predecessors(node_id) if p not in done]
