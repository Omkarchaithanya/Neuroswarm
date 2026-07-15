"""Progress monitoring for workflow coordination."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ._utils import utc_now
from .models import ProgressSnapshot, WorkflowExecution
from .workflow_state import WorkflowStatus

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.swarm.task_graph.graph import TaskGraph


class ProgressMonitor:
    """Track completed / pending / ready / running counts and health."""

    def snapshot(self, execution: WorkflowExecution) -> ProgressSnapshot:
        elapsed = self._elapsed_ms(execution.created_at)
        total = len(execution.node_set()) or (
            len(execution.completed_nodes)
            + len(execution.pending_nodes)
            + len(execution.failed_nodes)
            + len(execution.current_nodes)
        )
        completed = len(execution.completed_nodes)
        failed = len(execution.failed_nodes)
        health = 1.0
        if total > 0:
            health = max(0.0, 1.0 - (failed / total))
            if execution.status == WorkflowStatus.FAILED:
                health = min(health, 0.25)
            elif execution.status == WorkflowStatus.CANCELLED:
                health = min(health, 0.5)

        eta = self._estimate_completion_ms(execution, elapsed, total, completed)
        parallelism = len(execution.current_nodes)

        return ProgressSnapshot(
            execution_id=execution.execution_id,
            status=execution.status,
            completed_nodes=list(execution.completed_nodes),
            pending_nodes=list(execution.pending_nodes),
            ready_nodes=list(execution.ready_nodes),
            running_nodes=list(execution.current_nodes),
            failed_nodes=list(execution.failed_nodes),
            elapsed_ms=elapsed,
            estimated_completion_ms=eta,
            health=health,
            parallelism=parallelism,
            metadata={
                "total_nodes": total,
                "skipped": len(execution.skipped_nodes),
            },
        )

    def refresh_execution_sets(
        self,
        execution: WorkflowExecution,
        *,
        ready: list[str],
        graph: TaskGraph | None = None,
    ) -> WorkflowExecution:
        all_nodes = execution.node_set()
        if not all_nodes and graph is not None:
            all_nodes = set(graph.nodes.keys())
        done = set(execution.completed_nodes) | set(execution.skipped_nodes)
        failed = set(execution.failed_nodes)
        running = set(execution.current_nodes)
        execution.ready_nodes = list(ready)
        execution.pending_nodes = sorted(
            n for n in all_nodes if n not in done and n not in failed and n not in running
        )
        execution.touch()
        return execution

    def _elapsed_ms(self, created_at: datetime) -> float:
        now = utc_now()
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return max(0.0, (now - created_at).total_seconds() * 1000.0)

    def _estimate_completion_ms(
        self,
        execution: WorkflowExecution,
        elapsed_ms: float,
        total: int,
        completed: int,
    ) -> float | None:
        if total <= 0 or completed <= 0:
            # Fall back to sum of estimated latencies on pending if graph present
            graph = execution.graph
            if graph is not None and hasattr(graph, "nodes"):
                pending = set(execution.pending_nodes) | set(execution.ready_nodes) | set(
                    execution.current_nodes
                )
                est = sum(
                    float(getattr(graph.nodes[n], "estimated_latency", 0.0))
                    for n in pending
                    if n in graph.nodes
                )
                return elapsed_ms + est if est > 0 else None
            return None
        rate = completed / elapsed_ms if elapsed_ms > 0 else 0.0
        remaining = total - completed - len(execution.skipped_nodes)
        if rate <= 0 or remaining <= 0:
            return elapsed_ms if remaining <= 0 else None
        return elapsed_ms + (remaining / rate)
