"""Typed errors for the Rollback Manager subsystem."""

from __future__ import annotations


class RollbackError(Exception):
    """Base error for the Rollback Manager subsystem."""


class ValidationError(RollbackError):
    """Rollback operation or plan failed validation."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class DuplicateRollbackError(ValidationError):
    """Duplicate rollback id."""

    def __init__(self, rollback_id: str) -> None:
        super().__init__(
            f"duplicate rollback id: {rollback_id}", field="rollback_id"
        )
        self.rollback_id = rollback_id


class NotFoundError(RollbackError):
    """Requested rollback or handle is missing."""

    def __init__(self, key: str, *, kind: str = "rollback") -> None:
        super().__init__(f"{kind} not found: {key}")
        self.key = key
        self.kind = kind


class ImmutabilityError(RollbackError):
    """Mutation attempted on append-only rollback store."""

    def __init__(self, message: str = "rollback store is append-only") -> None:
        super().__init__(message)


class SerializationError(RollbackError):
    """Serialize / deserialize failure."""


class ChecksumMismatchError(ValidationError):
    """Stored checksum does not match recomputed digest."""

    def __init__(self, rollback_id: str) -> None:
        super().__init__(
            f"checksum mismatch for rollback: {rollback_id}",
            field="checksum",
        )
        self.rollback_id = rollback_id


class VersionMismatchError(ValidationError):
    """Schema version incompatible with current migrator."""

    def __init__(self, found: int, expected: int) -> None:
        super().__init__(
            f"schema version mismatch: found={found} expected={expected}",
            field="version",
        )
        self.found = found
        self.expected = expected


class LifecycleError(RollbackError):
    """Illegal rollback lifecycle state transition."""

    def __init__(self, rollback_id: str, current: object, target: object) -> None:
        super().__init__(
            f"invalid lifecycle for {rollback_id}: {current} -> {target}"
        )
        self.rollback_id = rollback_id
        self.current = current
        self.target = target


class ConsistencyError(RollbackError):
    """Runtime consistency validation failed."""

    def __init__(
        self,
        message: str,
        *,
        violations: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.violations = list(violations or [])


class PolicyError(RollbackError):
    """Invalid rollback policy configuration or evaluation."""


class RollbackPlanningError(RollbackError):
    """Rollback plan could not be produced."""


class RollbackExecutionError(RollbackError):
    """Rollback apply (state-descriptor materialization) failed."""


class CancellationError(RollbackError):
    """Rollback could not be cancelled in current state."""
