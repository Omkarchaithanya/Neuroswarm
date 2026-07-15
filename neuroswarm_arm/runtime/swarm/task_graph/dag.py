"""Pure-Python DAG algorithms (networkx optional accelerate)."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING, Iterable

from .enums import EdgeKind
from .exceptions import CycleError, NodeNotFoundError

if TYPE_CHECKING:
    from .graph import TaskGraph

try:
    import networkx as nx

    _HAS_NX = True
except ImportError:  # pragma: no cover
    nx = None  # type: ignore[assignment]
    _HAS_NX = False


class DAGAnalyzer:
    """Topo sort, cycles, layers, critical path, reachability, components."""

    def __init__(self, graph: TaskGraph) -> None:
        self.graph = graph
        self._adj: dict[str, list[str]] = defaultdict(list)
        self._rev: dict[str, list[str]] = defaultdict(list)
        self._edge_kinds: dict[tuple[str, str], list[EdgeKind]] = defaultdict(list)
        for edge in graph.edges:
            # Soft / priority edges do not block readiness by default
            self._edge_kinds[(edge.src, edge.dst)].append(edge.kind)
            if edge.kind in {EdgeKind.SOFT, EdgeKind.PRIORITY}:
                continue
            self._adj[edge.src].append(edge.dst)
            self._rev[edge.dst].append(edge.src)
        for nid in graph.nodes:
            self._adj.setdefault(nid, [])
            self._rev.setdefault(nid, [])
        self._nx = None
        if _HAS_NX:
            g = nx.DiGraph()
            for nid in graph.nodes:
                g.add_node(nid)
            for u, vs in self._adj.items():
                for v in vs:
                    g.add_edge(u, v)
            self._nx = g

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
            raise CycleError("task graph contains a cycle")
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

    def execution_layers(self) -> list[list[str]]:
        """Kahn layering: nodes in same layer may run in parallel."""
        if not self.is_dag():
            raise CycleError("task graph contains a cycle")
        indeg = {n: 0 for n in self.graph.nodes}
        for u, vs in self._adj.items():
            for v in vs:
                indeg[v] = indeg.get(v, 0) + 1
        layer = sorted(n for n, d in indeg.items() if d == 0)
        layers: list[list[str]] = []
        remaining = set(self.graph.nodes)
        while layer:
            layers.append(layer)
            remaining -= set(layer)
            nxt: list[str] = []
            for u in layer:
                for v in self._adj.get(u, ()):
                    indeg[v] -= 1
                    if indeg[v] == 0:
                        nxt.append(v)
            layer = sorted(nxt)
        if remaining:
            raise CycleError(f"unreachable residual nodes: {sorted(remaining)}")
        return layers

    def dependency_barriers(self) -> list[dict[str, object]]:
        """Detect join barriers: nodes with >1 hard predecessor."""
        barriers: list[dict[str, object]] = []
        for nid in self.graph.nodes:
            preds = self._rev.get(nid, [])
            if len(preds) > 1:
                barriers.append(
                    {
                        "node_id": nid,
                        "predecessors": list(preds),
                        "barrier_width": len(preds),
                    }
                )
        return barriers

    def ready_nodes(self, completed: Iterable[str]) -> list[str]:
        done = set(completed)
        ready: list[str] = []
        for nid in self.graph.nodes:
            if nid in done:
                continue
            preds = self._rev.get(nid, [])
            if all(p in done for p in preds):
                ready.append(nid)
        return sorted(ready)

    def roots(self) -> list[str]:
        return sorted(n for n in self.graph.nodes if not self._rev.get(n))

    def leaves(self) -> list[str]:
        return sorted(n for n in self.graph.nodes if not self._adj.get(n))

    def successors(self, node_id: str) -> list[str]:
        self._require(node_id)
        return list(self._adj.get(node_id, []))

    def predecessors(self, node_id: str) -> list[str]:
        self._require(node_id)
        return list(self._rev.get(node_id, []))

    def reachable_from(self, node_id: str) -> set[str]:
        self._require(node_id)
        seen: set[str] = set()
        stack = [node_id]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            stack.extend(self._adj.get(u, []))
        return seen

    def ancestors_of(self, node_id: str) -> set[str]:
        self._require(node_id)
        seen: set[str] = set()
        stack = [node_id]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            stack.extend(self._rev.get(u, []))
        return seen

    def subtree(self, node_id: str) -> set[str]:
        """Node + all descendants."""
        return self.reachable_from(node_id)

    def downstream(self, node_id: str) -> set[str]:
        """Strict descendants (excludes self)."""
        return self.reachable_from(node_id) - {node_id}

    def connected_components(self) -> list[set[str]]:
        """Weakly connected components over undirected projection."""
        undirected: dict[str, set[str]] = {n: set() for n in self.graph.nodes}
        for u, vs in self._adj.items():
            for v in vs:
                undirected[u].add(v)
                undirected[v].add(u)
        seen: set[str] = set()
        comps: list[set[str]] = []
        for start in self.graph.nodes:
            if start in seen:
                continue
            comp: set[str] = set()
            stack = [start]
            while stack:
                u = stack.pop()
                if u in comp:
                    continue
                comp.add(u)
                stack.extend(undirected.get(u, ()))
            seen |= comp
            comps.append(comp)
        return comps

    def critical_path(self) -> list[str]:
        """Longest path by estimated_latency (ms)."""
        if not self.graph.nodes:
            return []
        order = self.topological_order()
        dist: dict[str, float] = {n: 0.0 for n in self.graph.nodes}
        pred: dict[str, str | None] = {n: None for n in self.graph.nodes}
        for u in order:
            node_u = self.graph.nodes[u]
            base = float(node_u.estimated_latency)
            for v in self._adj.get(u, ()):
                cand = dist[u] + base
                if cand >= dist[v]:
                    dist[v] = cand
                    pred[v] = u
            dist[u] = dist[u]  # noqa: B018 — keep explicit
            # include self weight at sink comparison below
        # add own latency to path score for leaves
        best_end = max(
            self.graph.nodes,
            key=lambda n: dist[n] + float(self.graph.nodes[n].estimated_latency),
        )
        path: list[str] = []
        cur: str | None = best_end
        while cur is not None:
            path.append(cur)
            cur = pred[cur]
        path.reverse()
        return path

    def critical_path_latency_ms(self) -> float:
        path = self.critical_path()
        return sum(float(self.graph.nodes[n].estimated_latency) for n in path)

    def depth(self) -> int:
        return len(self.execution_layers())

    def width(self) -> int:
        layers = self.execution_layers()
        return max((len(layer) for layer in layers), default=0)

    def disconnected_nodes(self) -> list[str]:
        """Nodes with no edges and graph has >1 node."""
        if len(self.graph.nodes) <= 1:
            return []
        touched: set[str] = set()
        for edge in self.graph.edges:
            if edge.kind in {EdgeKind.SOFT, EdgeKind.PRIORITY}:
                # still counts as connected for orphan detection
                touched.add(edge.src)
                touched.add(edge.dst)
            else:
                touched.add(edge.src)
                touched.add(edge.dst)
        # Also count soft edges above; for orphans use all edges:
        touched = set()
        for edge in self.graph.edges:
            touched.add(edge.src)
            touched.add(edge.dst)
        return sorted(set(self.graph.nodes) - touched)

    def missing_dependencies(self) -> list[tuple[str, str]]:
        """Edges referencing unknown nodes, or node.dependencies missing."""
        missing: list[tuple[str, str]] = []
        for edge in self.graph.edges:
            if edge.src not in self.graph.nodes:
                missing.append((edge.src, edge.dst))
            if edge.dst not in self.graph.nodes:
                missing.append((edge.src, edge.dst))
        for nid, node in self.graph.nodes.items():
            for dep in node.dependencies:
                if dep not in self.graph.nodes:
                    missing.append((dep, nid))
        return missing

    def _require(self, node_id: str) -> None:
        if node_id not in self.graph.nodes:
            raise NodeNotFoundError(node_id)
