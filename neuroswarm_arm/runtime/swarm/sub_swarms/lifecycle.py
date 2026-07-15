"""Swarm template lifecycle states and legal transitions."""

from __future__ import annotations

from enum import Enum

from .exceptions import LifecycleError


class LifecycleState(str, Enum):
    """Lifecycle for a registered swarm template."""

    CREATED = "created"
    REGISTERED = "registered"
    READY = "ready"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
    ARCHIVED = "archived"


_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.CREATED: frozenset(
        {LifecycleState.REGISTERED, LifecycleState.ARCHIVED}
    ),
    LifecycleState.REGISTERED: frozenset(
        {
            LifecycleState.READY,
            LifecycleState.DISABLED,
            LifecycleState.DEPRECATED,
            LifecycleState.ARCHIVED,
        }
    ),
    LifecycleState.READY: frozenset(
        {
            LifecycleState.DEPRECATED,
            LifecycleState.DISABLED,
            LifecycleState.ARCHIVED,
        }
    ),
    LifecycleState.DEPRECATED: frozenset(
        {
            LifecycleState.READY,
            LifecycleState.DISABLED,
            LifecycleState.ARCHIVED,
        }
    ),
    LifecycleState.DISABLED: frozenset(
        {
            LifecycleState.READY,
            LifecycleState.REGISTERED,
            LifecycleState.ARCHIVED,
        }
    ),
    LifecycleState.ARCHIVED: frozenset(),
}


def can_transition(current: LifecycleState, target: LifecycleState) -> bool:
    if current is target:
        return True
    return target in _TRANSITIONS.get(current, frozenset())


def transition(
    template_id: str,
    current: LifecycleState,
    target: LifecycleState,
) -> LifecycleState:
    if not can_transition(current, target):
        raise LifecycleError(template_id, current, target)
    return target


def is_selectable(status: LifecycleState) -> bool:
    """Only READY templates are eligible for deterministic selection."""
    return status is LifecycleState.READY
