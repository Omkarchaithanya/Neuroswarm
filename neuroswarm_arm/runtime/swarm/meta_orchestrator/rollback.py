"""Rollback coordination — notify only, no durable undo."""

from __future__ import annotations

from .events import EventBus, RollbackNotified
from .exceptions import RollbackCoordinationError
from .models import RollbackPlan, WorkflowExecution


class RollbackCoordinator:
    """Produce rollback notifications and target node sets."""

    def __init__(self, *, events: EventBus | None = None) -> None:
        self.events = events

    def plan(
        self,
        execution: WorkflowExecution,
        *,
        target_nodes: list[str] | None = None,
        reason: str = "failure",
        from_failed: bool = True,
    ) -> RollbackPlan:
        if target_nodes is None:
            targets = list(execution.failed_nodes) if from_failed else list(execution.completed_nodes)
        else:
            targets = list(target_nodes)
        if not targets and not execution.checkpoint_reference:
            raise RollbackCoordinationError("no rollback targets and no checkpoint")
        return RollbackPlan(
            execution_id=execution.execution_id,
            target_nodes=targets,
            checkpoint_reference=execution.checkpoint_reference,
            reason=reason,
        )

    def notify(self, execution: WorkflowExecution, plan: RollbackPlan) -> WorkflowExecution:
        if self.events is not None:
            self.events.emit(
                RollbackNotified(
                    execution.workflow_id,
                    execution.execution_id,
                    targets=list(plan.target_nodes),
                    checkpoint_reference=plan.checkpoint_reference or "",
                    reason=plan.reason,
                )
            )
        execution.metadata = {
            **execution.metadata,
            "last_rollback": plan.model_dump(mode="json"),
        }
        execution.touch()
        return execution
