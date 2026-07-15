"""Dependency graph analysis — topo order, critical path, priority inheritance.

Uses networkx when available; otherwise a pure-Python DAG implementation so
minimal Docker images without the full ML stack still run HAOE.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable

from ..interfaces.types import EdgeKind, PriorityClass
from ..core.task_graph import TaskEdge, TaskGraph, TaskNode

try:
    import networkx as nx

    _HAS_NX = True
except ImportError:  # pragma: no cover
    nx = None  # type: ignore[assignment]
    _HAS_NX = False


class DependencyGraph:
    def __init__(self, graph: TaskGraph) -> None:
        self.graph = graph
        self._adj: dict[str, list[str]] = defaultdict(list)
        self._rev: dict[str, list[str]] = defaultdict(list)
        self._edge_map: dict[tuple[str, str], TaskEdge] = {}
        for edge in graph.edges:
            if edge.kind is EdgeKind.CANCEL:
                continue
            self._adj[edge.src].append(edge.dst)
            self._rev[edge.dst].append(edge.src)
            self._edge_map[(edge.src, edge.dst)] = edge
        self._nx = None
        if _HAS_NX:
            self._nx = nx.DiGraph()
            for nid in graph.nodes:
                self._nx.add_node(nid)
            for (u, v), edge in self._edge_map.items():
                self._nx.add_edge(u, v, edge=edge)

    def is_dag(self) -> bool:
        if self._nx is not None:
            return nx.is_directed_acyclic_graph(self._nx)
        return self._is_dag_pure()

    def _is_dag_pure(self) -> bool:
        indeg = {n: 0 for n in self.graph.nodes}
        for u, vs in self._adj.items():
            for v in vs:
                indeg[v] = indeg.get(v, 0) + 1
        q = deque([n for n, d in indeg.items() if d == 0])
        seen = 0
        while q:
            u = q.popleft()
            seen += 1
            for v in self._adj.get(u, ()):
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        return seen == len(self.graph.nodes)

    def topological_order(self) -> list[str]:
        if not self.is_dag():
            raise ValueError("task graph contains a cycle")
        if self._nx is not None:
            return list(nx.topological_sort(self._nx))
        indeg = {n: 0 for n in self.graph.nodes}
        for u, vs in self._adj.items():
            for v in vs:
                indeg[v] = indeg.get(v, 0) + 1
        q = deque(sorted(n for n, d in indeg.items() if d == 0))
        order: list[str] = []
        while q:
            u = q.popleft()
            order.append(u)
            for v in sorted(self._adj.get(u, ())):
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        return order

    def ready_nodes(self, completed: Iterable[str]) -> list[str]:
        done = set(completed)
        ready: list[str] = []
        for nid in self.graph.nodes:
            if nid in done:
                continue
            preds = self._rev.get(nid, [])
            if all(p in done for p in preds):
                if self._predicates_satisfied(nid, done):
                    ready.append(nid)
        return ready

    def _predicates_satisfied(self, nid: str, done: set[str]) -> bool:
        for pred in self._rev.get(nid, []):
            edge = self._edge_map.get((pred, nid))
            if edge is None:
                continue
            if edge.kind is EdgeKind.CONDITIONAL and edge.condition is not None:
                if not edge.condition(self.graph.context):
                    return False
        return True

    def critical_path(self) -> list[str]:
        if not self.graph.nodes or not self.is_dag():
            return []
        if self._nx is not None:
            weighted = self._nx.copy()
            for u, v in weighted.edges:
                node: TaskNode = self.graph.nodes[v]
                weighted[u][v]["weight"] = max(0.001, node.estimate.expected_latency_ms)
            try:
                return list(nx.dag_longest_path(weighted, weight="weight"))
            except Exception:
                return self.topological_order()
        return self._longest_path_pure()

    def _longest_path_pure(self) -> list[str]:
        order = self.topological_order()
        dist = {n: 0.0 for n in self.graph.nodes}
        pred: dict[str, str | None] = {n: None for n in self.graph.nodes}
        for u in order:
            for v in self._adj.get(u, ()):
                w = max(0.001, self.graph.nodes[v].estimate.expected_latency_ms)
                if dist[u] + w > dist[v]:
                    dist[v] = dist[u] + w
                    pred[v] = u
        if not dist:
            return []
        end = max(dist, key=lambda n: dist[n])
        path: list[str] = []
        cur: str | None = end
        while cur is not None:
            path.append(cur)
            cur = pred[cur]
        path.reverse()
        return path

    def inherit_priorities(self) -> None:
        path = set(self.critical_path())
        if not path:
            return
        for nid in path:
            node = self.graph.nodes[nid]
            if node.priority > PriorityClass.HIGH:
                node.priority = PriorityClass.HIGH
