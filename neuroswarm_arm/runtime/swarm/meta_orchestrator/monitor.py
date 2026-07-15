"""Observe HAOE execution signals and update workflow node sets."""

from __future__ import annotations

from .events import EventBus, NodeCompleted, NodeFailed
from .metrics import OrchestratorMetrics
from .models import ExecutionSignal, NodeResult, WorkflowExecution


class ExecutionMonitor:
    """Apply ExecutionSignal to WorkflowExecution — coordination only."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: OrchestratorMetrics | None = None,
    ) -> None:
        self.events = events
        self.metrics = metrics

    def apply_signal(
        self, execution: WorkflowExecution, signal: ExecutionSignal
    ) -> WorkflowExecution:
        nid = signal.node_id
        if nid in execution.current_nodes:
            execution.current_nodes = [n for n in execution.current_nodes if n != nid]

        status = signal.status.lower()
        if status in {"succeeded", "checkpointed"}:
            if nid not in execution.completed_nodes:
                execution.completed_nodes.append(nid)
            result = signal.result or NodeResult(node_id=nid, success=True)
            execution.node_results[nid] = result
            execution.metrics.nodes_completed += 1
            if self.events is not None:
                self.events.emit(
                    NodeCompleted(
                        execution.workflow_id,
                        execution.execution_id,
                        nid,
                        status=status,
                    )
                )
        elif status in {"failed", "timed_out"}:
            if nid not in execution.failed_nodes:
                execution.failed_nodes.append(nid)
            result = signal.result or NodeResult(
                node_id=nid, success=False, error=signal.error
            )
            execution.node_results[nid] = result
            execution.metrics.nodes_failed += 1
            if self.metrics is not None:
                self.metrics.record_failure()
            if self.events is not None:
                self.events.emit(
                    NodeFailed(
                        execution.workflow_id,
                        execution.execution_id,
                        nid,
                        error=signal.error or "",
                        status=status,
                    )
                )
        elif status == "cancelled":
            if nid not in execution.skipped_nodes:
                execution.skipped_nodes.append(nid)
        elif status == "skipped":
            if nid not in execution.skipped_nodes:
                execution.skipped_nodes.append(nid)

        execution.touch()
        return execution

    def mark_running(self, execution: WorkflowExecution, node_ids: list[str]) -> WorkflowExecution:
        running = list(execution.current_nodes)
        for nid in node_ids:
            if nid not in running:
                running.append(nid)
            execution.ready_nodes = [n for n in execution.ready_nodes if n != nid]
            execution.pending_nodes = [n for n in execution.pending_nodes if n != nid]
        execution.current_nodes = running
        execution.touch()
        return execution
