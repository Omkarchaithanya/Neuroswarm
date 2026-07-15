"""Typed errors for the Experience Store subsystem."""

from __future__ import annotations


class ExperienceStoreError(Exception):
    """Base error for the Experience Store subsystem."""


class ValidationError(ExperienceStoreError):
    """Record or payload failed validation."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class DuplicateIdError(ValidationError):
    """Duplicate execution / workflow / snapshot id."""

    def __init__(self, id_value: str, *, kind: str = "execution") -> None:
        super().__init__(f"duplicate {kind} id: {id_value}", field="id")
        self.id_value = id_value
        self.kind = kind


class NotFoundError(ExperienceStoreError):
    """Requested record or handle is missing."""

    def __init__(self, key: str, *, kind: str = "execution") -> None:
        super().__init__(f"{kind} not found: {key}")
        self.key = key
        self.kind = kind


class ImmutabilityError(ExperienceStoreError):
    """Mutation attempted on append-only store."""

    def __init__(self, message: str = "experience store is append-only") -> None:
        super().__init__(message)


class SerializationError(ExperienceStoreError):
    """Serialize / deserialize failure."""


class ExportError(ExperienceStoreError):
    """Dataset or format export failure."""


class ImportError(ExperienceStoreError):
    """Import validation or append failure."""


class RetentionError(ExperienceStoreError):
    """Retention / archive / compaction failure."""


class VersionMismatchError(ValidationError):
    """Schema version incompatible with current migrator."""

    def __init__(self, found: int, expected: int) -> None:
        super().__init__(
            f"schema version mismatch: found={found} expected={expected}",
            field="version",
        )
        self.found = found
        self.expected = expected


class LifecycleError(ExperienceStoreError):
    """Illegal lifecycle state transition."""

    def __init__(self, execution_id: str, current: object, target: object) -> None:
        super().__init__(
            f"invalid lifecycle for {execution_id}: {current} -> {target}"
        )
        self.execution_id = execution_id
        self.current = current
        self.target = target
