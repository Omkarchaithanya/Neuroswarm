"""Workflow completion detection and final metric rollup."""

from __future__ import annotations

from ._utils import utc_now
from .events import EventBus, WorkflowCompleted
from .lifecycle import WorkflowLifecycle
from .metrics import OrchestratorMetrics
from .models import WorkflowExecution
from .workflow_state import WorkflowStatus


class CompletionEvaluator:
    """Decide when a workflow is complete / failed and finalize metrics."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: OrchestratorMetrics | None = None,
        lifecycle: WorkflowLifecycle | None = None,
        fail_fast: bool = False,
    ) -> None:
        self.events = events
        self.metrics = metrics
        self.lifecycle = lifecycle or WorkflowLifecycle()
        self.fail_fast = fail_fast

    def is_complete(self, execution: WorkflowExecution) -> bool:
        all_nodes = execution.node_set()
        if not all_nodes:
            return (
                not execution.pending_nodes
                and not execution.ready_nodes
                and not execution.current_nodes
            )
        settled = (
            set(execution.completed_nodes)
            | set(execution.skipped_nodes)
            | set(execution.failed_nodes)
        )
        return settled >= all_nodes and not execution.current_nodes

    def should_fail(self, execution: WorkflowExecution) -> bool:
        if self.fail_fast and execution.failed_nodes:
            return True
        if self.is_complete(execution) and execution.failed_nodes:
            # Fail if any failures and no remaining work (unless all failures skipped)
            remaining_failures = [
                n for n in execution.failed_nodes if n not in execution.skipped_nodes
            ]
            return bool(remaining_failures)
        return False

    def finalize(self, execution: WorkflowExecution) -> WorkflowExecution:
        elapsed = max(
            0.0, (utc_now() - execution.created_at).total_seconds() * 1000.0
        )
        execution.metrics.workflow_latency_ms = elapsed
        total = max(1, execution.metrics.nodes_completed + execution.metrics.nodes_failed)
        execution.metrics.failure_rate = execution.metrics.nodes_failed / total
        execution.metrics.parallelism = float(len(execution.current_nodes))

        if execution.cancel_requested:
            self.lifecycle.mark_cancelled(execution)
            return execution

        if self.should_fail(execution):
            self.lifecycle.mark_failed(execution)
            if self.metrics is not None:
                self.metrics.record_workflow_failed()
                self.metrics.observe_workflow_latency(elapsed)
            return execution

        if self.is_complete(execution):
            self.lifecycle.mark_completed(execution)
            if self.metrics is not None:
                self.metrics.record_workflow_completed()
                self.metrics.observe_workflow_latency(elapsed)
            if self.events is not None:
                self.events.emit(
                    WorkflowCompleted(
                        execution.workflow_id,
                        execution.execution_id,
                        nodes_completed=execution.metrics.nodes_completed,
                        latency_ms=elapsed,
                    )
                )
        return execution

    def status_after_tick(self, execution: WorkflowExecution) -> WorkflowStatus:
        if self.lifecycle.is_terminal(execution):
            return execution.status
        if execution.current_nodes:
            return WorkflowStatus.RUNNING
        if execution.ready_nodes:
            return WorkflowStatus.RUNNING
        if execution.pending_nodes:
            return WorkflowStatus.WAITING
        return execution.status
