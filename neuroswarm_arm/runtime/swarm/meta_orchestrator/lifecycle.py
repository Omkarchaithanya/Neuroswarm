"""Workflow lifecycle state machine."""

from __future__ import annotations

from .exceptions import InvalidWorkflowStateError
from .models import WorkflowExecution
from .workflow_state import (
    TERMINAL_WORKFLOW_STATUSES,
    WORKFLOW_TRANSITIONS,
    WorkflowStatus,
)
from ._utils import utc_now


class WorkflowLifecycle:
    """Enforce WorkflowStatus transitions on WorkflowExecution."""

    def transition(self, execution: WorkflowExecution, target: WorkflowStatus) -> WorkflowExecution:
        current = execution.status
        if current == target:
            return execution
        allowed = WORKFLOW_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise InvalidWorkflowStateError(current, target)
        execution.status = target
        execution.updated_at = utc_now()
        return execution

    def mark_ready(self, execution: WorkflowExecution) -> WorkflowExecution:
        return self.transition(execution, WorkflowStatus.READY)

    def mark_running(self, execution: WorkflowExecution) -> WorkflowExecution:
        return self.transition(execution, WorkflowStatus.RUNNING)

    def mark_waiting(self, execution: WorkflowExecution) -> WorkflowExecution:
        return self.transition(execution, WorkflowStatus.WAITING)

    def mark_completed(self, execution: WorkflowExecution) -> WorkflowExecution:
        return self.transition(execution, WorkflowStatus.COMPLETED)

    def mark_failed(self, execution: WorkflowExecution) -> WorkflowExecution:
        return self.transition(execution, WorkflowStatus.FAILED)

    def mark_cancelled(self, execution: WorkflowExecution) -> WorkflowExecution:
        return self.transition(execution, WorkflowStatus.CANCELLED)

    def mark_checkpointed(self, execution: WorkflowExecution) -> WorkflowExecution:
        return self.transition(execution, WorkflowStatus.CHECKPOINTED)

    def mark_restored(self, execution: WorkflowExecution) -> WorkflowExecution:
        return self.transition(execution, WorkflowStatus.RESTORED)

    def is_terminal(self, execution: WorkflowExecution) -> bool:
        return execution.status in TERMINAL_WORKFLOW_STATUSES

    def can_transition(self, current: WorkflowStatus, target: WorkflowStatus) -> bool:
        return target in WORKFLOW_TRANSITIONS.get(current, frozenset())
