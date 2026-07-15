"""Exceptions for the Task Graph subsystem."""

from __future__ import annotations


class TaskGraphError(Exception):
    """Base error for the Task Graph subsystem."""


class ValidationError(TaskGraphError):
    """Graph failed structural or semantic validation."""

    def __init__(self, message: str, *, report: object | None = None) -> None:
        super().__init__(message)
        self.report = report


class CycleError(ValidationError):
    """Graph contains one or more cycles."""


class FrozenGraphError(TaskGraphError):
    """Mutation attempted on a frozen (immutable) graph definition."""


class NodeNotFoundError(TaskGraphError):
    """Requested node id is not present in the graph."""

    def __init__(self, node_id: str) -> None:
        super().__init__(f"node not found: {node_id}")
        self.node_id = node_id


class EdgeNotFoundError(TaskGraphError):
    """Requested edge is not present in the graph."""


class InvalidTransitionError(TaskGraphError):
    """Illegal node status transition."""

    def __init__(self, node_id: str, current: object, target: object) -> None:
        super().__init__(
            f"invalid transition for {node_id}: {current} -> {target}"
        )
        self.node_id = node_id
        self.current = current
        self.target = target


class ExecutionError(TaskGraphError):
    """Graph execution failed."""


class NodeExecutionError(ExecutionError):
    """A single node handler failed."""

    def __init__(self, node_id: str, cause: BaseException) -> None:
        super().__init__(f"node {node_id} failed: {cause}")
        self.node_id = node_id
        self.cause = cause


class TimeoutError(ExecutionError):
    """Node, subgraph, or workflow timeout elapsed."""

    def __init__(self, scope: str, *, node_id: str | None = None) -> None:
        msg = f"timeout: {scope}"
        if node_id:
            msg = f"timeout: {scope} (node={node_id})"
        super().__init__(msg)
        self.scope = scope
        self.node_id = node_id


class CancellationError(ExecutionError):
    """Execution cancelled."""

    def __init__(self, message: str = "cancelled", *, forced: bool = False) -> None:
        super().__init__(message)
        self.forced = forced


class SerializationError(TaskGraphError):
    """Serialize/deserialize failure."""


class ConditionError(TaskGraphError):
    """Condition evaluation failure."""


class AdapterError(TaskGraphError):
    """HAOE (or other) adapter conversion failure."""
