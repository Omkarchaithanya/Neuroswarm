"""Retry coordination — decisions only, no backoff engine."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.task_graph.node import TaskNode

from .events import EventBus, RetryRequested
from .exceptions import RetryCoordinationError
from .metrics import OrchestratorMetrics
from .models import RetryDecision, WorkflowExecution


class RetryCoordinator:
    """Emit retry / skip / fallback decisions. Does not sleep or re-execute."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: OrchestratorMetrics | None = None,
    ) -> None:
        self.events = events
        self.metrics = metrics
        self._attempts: dict[str, int] = {}

    def decide(
        self,
        node: TaskNode,
        *,
        execution: WorkflowExecution,
        error: str | None = None,
        fallback_agent_id: str | None = None,
    ) -> RetryDecision:
        key = f"{execution.execution_id}:{node.id}"
        attempt = self._attempts.get(key, 0) + 1
        self._attempts[key] = attempt
        max_attempts = int(getattr(node.retry_policy, "max_attempts", 3) or 3)

        if attempt > max_attempts:
            decision = RetryDecision(
                node_id=node.id,
                attempt=attempt,
                max_attempts=max_attempts,
                reason=error or "max_attempts_exceeded",
                skip=True,
                metadata={"action": "skip"},
            )
        else:
            decision = RetryDecision(
                node_id=node.id,
                attempt=attempt,
                max_attempts=max_attempts,
                reason=error or "retry",
                fallback_agent_id=fallback_agent_id,
                skip=False,
                metadata={"action": "retry"},
            )

        execution.metrics.retry_requests += 1
        if self.metrics is not None:
            self.metrics.record_retry()
        if self.events is not None:
            self.events.emit(
                RetryRequested(
                    execution.workflow_id,
                    execution.execution_id,
                    node.id,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    skip=decision.skip,
                    fallback_agent_id=fallback_agent_id or "",
                )
            )
        return decision

    def apply(
        self, execution: WorkflowExecution, decision: RetryDecision
    ) -> WorkflowExecution:
        nid = decision.node_id
        if decision.skip:
            if nid in execution.failed_nodes:
                execution.failed_nodes = [n for n in execution.failed_nodes if n != nid]
            if nid not in execution.skipped_nodes:
                execution.skipped_nodes.append(nid)
        else:
            # Move from failed back to pending/ready for re-coordination
            if nid in execution.failed_nodes:
                execution.failed_nodes = [n for n in execution.failed_nodes if n != nid]
            if nid not in execution.pending_nodes:
                execution.pending_nodes.append(nid)
            execution.node_results.pop(nid, None)
        execution.touch()
        return execution

    def require_node(self, node: TaskNode | None, node_id: str) -> TaskNode:
        if node is None:
            raise RetryCoordinationError(f"unknown node for retry: {node_id}", node_id=node_id)
        return node
