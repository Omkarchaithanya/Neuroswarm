"""Barrier synchronization — join / fan-out / fan-in / conditional joins."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from neuroswarm_arm.runtime.swarm.task_graph.enums import NodeType
from neuroswarm_arm.runtime.swarm.task_graph.graph import TaskGraph

from .dependency_manager import DependencyManager
from .events import BarrierReleased, EventBus
from .exceptions import SynchronizationError


class BarrierSynchronizer:
    """Coordinate barrier release. No execution. No scheduling."""

    def __init__(
        self,
        graph: TaskGraph,
        *,
        events: EventBus | None = None,
    ) -> None:
        self.graph = graph
        self.deps = DependencyManager(graph)
        self.events = events

    def fan_out_ready(
        self,
        root_completed: str,
        *,
        completed: Iterable[str],
        ready: Iterable[str],
    ) -> list[str]:
        """Successors of a completed node that are currently ready (parallel siblings)."""
        done = set(completed)
        ready_set = set(ready)
        return sorted(
            s for s in self.deps.successors(root_completed) if s in ready_set and s not in done
        )

    def fan_in_satisfied(self, join_node_id: str, completed: Iterable[str]) -> bool:
        """True when all hard predecessors of a join have completed (or skipped)."""
        return self.deps.hard_predecessors_satisfied(join_node_id, completed)

    def aggregation_barrier_ready(
        self, node_id: str, completed: Iterable[str]
    ) -> bool:
        node = self.graph.nodes[node_id]
        if node.node_type not in {NodeType.AGGREGATE, NodeType.PARALLEL}:
            return self.fan_in_satisfied(node_id, completed)
        return self.fan_in_satisfied(node_id, completed)

    def conditional_join_ready(
        self,
        node_id: str,
        *,
        completed: Iterable[str],
        condition_ctx: Mapping[str, Any] | None = None,
        required_preds: Iterable[str] | None = None,
    ) -> bool:
        """Conditional join: only listed (or all) predecessors must be done."""
        done = set(completed)
        preds = list(required_preds) if required_preds is not None else self.deps.predecessors(node_id)
        if not preds:
            return True
        if not all(p in done for p in preds):
            return False
        _ = condition_ctx  # evaluated upstream by ReadyNodeResolver
        return True

    def waiting_barriers(self, completed: Iterable[str], pending: Iterable[str]) -> list[str]:
        """Barrier nodes still waiting on unresolved predecessors."""
        done = set(completed)
        pending_set = set(pending)
        waiting: list[str] = []
        for barrier in self.deps.barriers():
            nid = str(barrier["node_id"])
            if nid not in pending_set or nid in done:
                continue
            if not self.fan_in_satisfied(nid, done):
                waiting.append(nid)
        return sorted(waiting)

    def release_if_ready(
        self,
        node_id: str,
        *,
        completed: Iterable[str],
        workflow_id: str = "",
        execution_id: str = "",
    ) -> bool:
        if not self.deps.is_barrier(node_id):
            return True
        if not self.fan_in_satisfied(node_id, completed):
            return False
        if self.events is not None and workflow_id and execution_id:
            self.events.emit(
                BarrierReleased(
                    workflow_id,
                    execution_id,
                    node_id,
                    width=self.deps.barrier_width(node_id),
                )
            )
        return True

    def assert_barrier(self, node_id: str) -> None:
        if node_id not in self.graph.nodes:
            raise SynchronizationError(f"unknown barrier node: {node_id}", barrier_id=node_id)
