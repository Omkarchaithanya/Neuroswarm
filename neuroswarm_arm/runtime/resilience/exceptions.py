"""Typed errors for the Runtime Model Resilience Engine."""

from __future__ import annotations


class ResilienceError(Exception):
    """Base error for RMRE."""


class ValidationError(ResilienceError):
    """Profile, policy, or plan failed validation."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class PolicyError(ResilienceError):
    """Invalid resilience policy configuration or evaluation."""


class ConstraintViolation(ResilienceError):
    """Candidate rejected by the constraint solver."""

    def __init__(self, message: str, *, constraint: str | None = None) -> None:
        super().__init__(message)
        self.constraint = constraint


class HealthError(ResilienceError):
    """Health evaluation failure."""


class SerializationError(ResilienceError):
    """Serialize / deserialize failure."""


class VersionMismatchError(ValidationError):
    """Schema version incompatible with current migrator."""

    def __init__(self, found: int, expected: int) -> None:
        super().__init__(
            f"schema version mismatch: found={found} expected={expected}",
            field="version",
        )
        self.found = found
        self.expected = expected


class RecoveryError(ResilienceError):
    """Recovery transition could not be recorded or completed."""


class CandidateError(ResilienceError):
    """Candidate generation failure."""
