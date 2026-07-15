"""Typed errors for the Swarm Context subsystem."""

from __future__ import annotations


class SwarmContextError(Exception):
    """Base error for the Swarm Context Operating System."""


class ValidationError(SwarmContextError):
    """Context failed structural or semantic validation."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class VersionMismatchError(ValidationError):
    """Schema version incompatible with current CONTEXT_SCHEMA_VERSION."""

    def __init__(self, found: str, expected: str) -> None:
        super().__init__(
            f"context schema version mismatch: found={found} expected={expected}",
            field="version",
        )
        self.found = found
        self.expected = expected


class MergeConflictError(SwarmContextError):
    """Merge could not resolve a field conflict under the active policy."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class SnapshotError(SwarmContextError):
    """Snapshot create / restore failure."""


class SerializationError(SwarmContextError):
    """Serialize / deserialize failure."""


class PropagationError(SwarmContextError):
    """Illegal parent/child/fork/branch operation."""


class CheckpointError(SwarmContextError):
    """Checkpoint metadata operation failure (no I/O — structural only)."""


class CacheError(SwarmContextError):
    """Context cache operation failure."""


class BudgetError(ValidationError):
    """Invalid budget limits or usage."""


class InvalidReferenceError(ValidationError):
    """Invalid external reference (Mem0/OKF/registry handle)."""
