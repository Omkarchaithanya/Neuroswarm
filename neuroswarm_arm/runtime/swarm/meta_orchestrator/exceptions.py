"""Exceptions for the Meta Orchestrator subsystem."""

from __future__ import annotations


class MetaOrchestratorError(Exception):
    """Base error for the Meta Orchestrator subsystem."""


class ValidationError(MetaOrchestratorError):
    """Workflow / graph / assignment validation failure."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class InvalidWorkflowStateError(MetaOrchestratorError):
    """Illegal workflow status transition."""

    def __init__(self, current: object, target: object) -> None:
        super().__init__(f"invalid workflow transition: {current} -> {target}")
        self.current = current
        self.target = target


class WorkflowNotFoundError(MetaOrchestratorError):
    """Requested workflow / execution id is unknown."""

    def __init__(self, execution_id: str) -> None:
        super().__init__(f"workflow execution not found: {execution_id}")
        self.execution_id = execution_id


class AssignmentError(MetaOrchestratorError):
    """Agent candidate selection / assignment failure."""

    def __init__(self, message: str, *, node_id: str | None = None) -> None:
        super().__init__(message)
        self.node_id = node_id


class CoordinationError(MetaOrchestratorError):
    """Coordination loop failure (dispatch, monitor, aggregate)."""

    def __init__(self, message: str, *, node_id: str | None = None) -> None:
        super().__init__(message)
        self.node_id = node_id


class ReadinessError(MetaOrchestratorError):
    """Ready-node discovery failure."""


class SynchronizationError(MetaOrchestratorError):
    """Barrier / join synchronization failure."""

    def __init__(self, message: str, *, barrier_id: str | None = None) -> None:
        super().__init__(message)
        self.barrier_id = barrier_id


class AggregationError(MetaOrchestratorError):
    """Result aggregation failure."""


class CheckpointCoordinationError(MetaOrchestratorError):
    """Checkpoint create / restore coordination failure."""

    def __init__(self, message: str, *, checkpoint_id: str | None = None) -> None:
        super().__init__(message)
        self.checkpoint_id = checkpoint_id


class RetryCoordinationError(MetaOrchestratorError):
    """Retry coordination failure (not the retry engine itself)."""

    def __init__(self, message: str, *, node_id: str | None = None) -> None:
        super().__init__(message)
        self.node_id = node_id


class RollbackCoordinationError(MetaOrchestratorError):
    """Rollback notification coordination failure."""


class SerializationError(MetaOrchestratorError):
    """Serialize / deserialize failure."""


class CancellationError(MetaOrchestratorError):
    """Workflow cancelled."""

    def __init__(self, message: str = "cancelled", *, forced: bool = False) -> None:
        super().__init__(message)
        self.forced = forced
