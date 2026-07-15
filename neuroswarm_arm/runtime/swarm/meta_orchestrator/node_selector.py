"""Select which ready nodes to dispatch next (priority / barrier aware)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Sequence

from neuroswarm_arm.runtime.swarm.task_graph.enums import NodeType, Priority

from .dependency_manager import DependencyManager

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.swarm.task_graph.graph import TaskGraph


class NodeSelector:
    """Order ready nodes for coordination dispatch — not a scheduler."""

    def __init__(self, graph: TaskGraph) -> None:
        self.graph = graph
        self.deps = DependencyManager(graph)

    def select(
        self,
        ready: Sequence[str],
        *,
        max_parallel: int | None = None,
        prefer_barriers_last: bool = True,
    ) -> list[str]:
        """Return ordered subset of ready nodes to assign this tick."""
        if not ready:
            return []

        def sort_key(nid: str) -> tuple:
            node = self.graph.nodes[nid]
            prio = int(getattr(node, "priority", Priority.NORMAL))
            is_barrier = 1 if prefer_barriers_last and self.deps.is_barrier(nid) else 0
            is_aggregate = 1 if getattr(node, "node_type", None) == NodeType.AGGREGATE else 0
            return (prio, is_barrier, is_aggregate, nid)

        ordered = sorted(ready, key=sort_key)
        if max_parallel is not None and max_parallel > 0:
            return ordered[:max_parallel]
        return ordered

    def select_fan_out(self, ready: Iterable[str]) -> list[str]:
        """Prefer non-barrier parallel siblings first."""
        return self.select(list(ready), prefer_barriers_last=True)
