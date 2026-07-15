"""Typed errors for the Checkpoint Manager subsystem."""

from __future__ import annotations


class CheckpointError(Exception):
    """Base error for the Checkpoint Manager subsystem."""


class ValidationError(CheckpointError):
    """Checkpoint or policy failed validation."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class DuplicateCheckpointError(ValidationError):
    """Duplicate checkpoint id."""

    def __init__(self, checkpoint_id: str) -> None:
        super().__init__(
            f"duplicate checkpoint id: {checkpoint_id}", field="checkpoint_id"
        )
        self.checkpoint_id = checkpoint_id


class NotFoundError(CheckpointError):
    """Requested checkpoint or handle is missing."""

    def __init__(self, key: str, *, kind: str = "checkpoint") -> None:
        super().__init__(f"{kind} not found: {key}")
        self.key = key
        self.kind = kind


class ImmutabilityError(CheckpointError):
    """Mutation attempted on append-only checkpoint store."""

    def __init__(self, message: str = "checkpoint store is append-only") -> None:
        super().__init__(message)


class SerializationError(CheckpointError):
    """Serialize / deserialize failure."""


class ChecksumMismatchError(ValidationError):
    """Stored checksum does not match recomputed digest."""

    def __init__(self, checkpoint_id: str) -> None:
        super().__init__(
            f"checksum mismatch for checkpoint: {checkpoint_id}",
            field="checksum",
        )
        self.checkpoint_id = checkpoint_id


class VersionMismatchError(ValidationError):
    """Schema version incompatible with current migrator."""

    def __init__(self, found: int, expected: int) -> None:
        super().__init__(
            f"schema version mismatch: found={found} expected={expected}",
            field="version",
        )
        self.found = found
        self.expected = expected


class LifecycleError(CheckpointError):
    """Illegal checkpoint lifecycle state transition."""

    def __init__(self, checkpoint_id: str, current: object, target: object) -> None:
        super().__init__(
            f"invalid lifecycle for {checkpoint_id}: {current} -> {target}"
        )
        self.checkpoint_id = checkpoint_id
        self.current = current
        self.target = target


class RetentionError(CheckpointError):
    """Retention / archive / compaction failure."""


class PolicyError(CheckpointError):
    """Invalid checkpoint policy configuration or evaluation."""


class RecoveryPlanningError(CheckpointError):
    """Recovery plan could not be produced."""


class RollbackPlanningError(CheckpointError):
    """Rollback metadata could not be produced."""
