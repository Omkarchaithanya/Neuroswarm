"""Typed errors for the Sub Swarm subsystem."""

from __future__ import annotations


class SubSwarmError(Exception):
    """Base error for the Sub Swarm subsystem."""


class ValidationError(SubSwarmError):
    """Template or composition failed validation."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class TemplateNotFoundError(SubSwarmError):
    """Requested template id/name is not present."""

    def __init__(self, key: str) -> None:
        super().__init__(f"swarm template not found: {key}")
        self.key = key


class DuplicateTemplateError(ValidationError):
    """Duplicate id or name in the registry."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message, field=field)


class LifecycleError(SubSwarmError):
    """Illegal lifecycle state transition."""

    def __init__(self, template_id: str, current: object, target: object) -> None:
        super().__init__(
            f"invalid lifecycle for {template_id}: {current} -> {target}"
        )
        self.template_id = template_id
        self.current = current
        self.target = target


class CompositionError(SubSwarmError):
    """Template composition failure (merge/extend/circular)."""


class CircularCompositionError(CompositionError):
    """Circular composition detected in provenance chain."""

    def __init__(self, chain: list[str]) -> None:
        path = " -> ".join(chain)
        super().__init__(f"circular composition: {path}")
        self.chain = list(chain)


class SerializationError(SubSwarmError):
    """Serialize / deserialize failure."""


class SelectionError(SubSwarmError):
    """No eligible swarm template for selection request."""


class VersionError(SubSwarmError):
    """Version parse / mismatch / migration failure."""
