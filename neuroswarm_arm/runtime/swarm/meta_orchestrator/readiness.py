"""Ready node discovery — respect deps, conditions, cancel, retry, checkpoints."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from neuroswarm_arm.runtime.swarm.task_graph.conditions import condition_from_dict
from neuroswarm_arm.runtime.swarm.task_graph.enums import EdgeKind, NodeType
from neuroswarm_arm.runtime.swarm.task_graph.graph import TaskGraph

from .dependency_manager import DependencyManager


class ReadyNodeResolver:
    """Find executable nodes for incremental coordination.

    Does not schedule. Does not execute. Pure readiness discovery.
    """

    def __init__(self, graph: TaskGraph) -> None:
        self.graph = graph
        self.deps = DependencyManager(graph)

    def resolve(
        self,
        *,
        completed: Iterable[str] = (),
        failed: Iterable[str] = (),
        skipped: Iterable[str] = (),
        running: Iterable[str] = (),
        cancelled: Iterable[str] = (),
        retrying: Iterable[str] = (),
        checkpoint_resume: Iterable[str] = (),
        condition_ctx: Mapping[str, Any] | None = None,
        cancel_requested: bool = False,
    ) -> list[str]:
        """Return sorted ready node ids."""
        if cancel_requested:
            return []

        done = set(completed) | set(skipped)
        blocked = set(failed) | set(cancelled) | set(running)
        retry_set = set(retrying)
        resume = set(checkpoint_resume)
        ctx = dict(condition_ctx or {})
        statuses = dict(ctx.get("node_statuses", {}))
        for nid in done:
            statuses.setdefault(nid, "succeeded")
        for nid in failed:
            statuses.setdefault(nid, "failed")
        for nid in skipped:
            statuses.setdefault(nid, "skipped")
        ctx["node_statuses"] = statuses

        ready: list[str] = []
        for nid, node in self.graph.nodes.items():
            if nid in done or nid in blocked:
                continue
            # Checkpoint resume: node already checkpointed → ready to continue
            if nid in resume:
                ready.append(nid)
                continue
            if nid in retry_set:
                # Retrying nodes become ready once put back into retry set
                if self.deps.hard_predecessors_satisfied(nid, done, skipped=skipped):
                    ready.append(nid)
                continue
            if not self.deps.hard_predecessors_satisfied(nid, done, skipped=skipped):
                continue
            if not self._edge_conditions_ok(nid, done, ctx):
                continue
            if not self._node_condition_ok(node, ctx):
                continue
            ready.append(nid)
        return sorted(ready)

    def _edge_conditions_ok(
        self, node_id: str, completed: set[str], ctx: Mapping[str, Any]
    ) -> bool:
        """Evaluate conditional edges into this node."""
        for edge in self.graph.edges:
            if edge.dst != node_id:
                continue
            if edge.kind not in {EdgeKind.CONDITIONAL, EdgeKind.HARD, EdgeKind.CONTROL, EdgeKind.DATA}:
                continue
            if not edge.condition:
                continue
            # Soft skip: if predecessor not completed, hard-dep already failed above
            if edge.src not in completed and edge.kind == EdgeKind.CONDITIONAL:
                # Conditional edge without completed src → not ready
                return False
            cond = condition_from_dict(edge.condition)
            if not cond.evaluate(ctx):
                return False
        return True

    def _node_condition_ok(self, node: Any, ctx: Mapping[str, Any]) -> bool:
        if not getattr(node, "condition", None):
            return True
        cond = condition_from_dict(node.condition)
        return bool(cond.evaluate(ctx))

    def should_skip(
        self,
        node_id: str,
        *,
        completed: Iterable[str],
        condition_ctx: Mapping[str, Any] | None = None,
    ) -> bool:
        """True when node condition fails but preds satisfied → skip candidate."""
        node = self.graph.nodes[node_id]
        done = set(completed)
        if not self.deps.hard_predecessors_satisfied(node_id, done):
            return False
        ctx = dict(condition_ctx or {})
        if node.condition and not self._node_condition_ok(node, ctx):
            return True
        if not self._edge_conditions_ok(node_id, done, ctx):
            # Conditional join false → skip rather than block forever
            for edge in self.graph.edges:
                if edge.dst == node_id and edge.condition and edge.src in done:
                    return True
        return False

    def incremental(
        self,
        previously_ready: Iterable[str],
        *,
        completed: Iterable[str],
        **kwargs: Any,
    ) -> list[str]:
        """Ready set minus previously observed ready (new discoveries only)."""
        prev = set(previously_ready)
        current = set(self.resolve(completed=completed, **kwargs))
        return sorted(current - prev)
