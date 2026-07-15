"""Lifecycle transitions for experience envelopes (not record bodies)."""

from __future__ import annotations

from .exceptions import LifecycleError
from .models import RecordLifecycle

_ALLOWED: dict[RecordLifecycle, set[RecordLifecycle]] = {
    RecordLifecycle.RECORDED: {
        RecordLifecycle.ARCHIVED,
        RecordLifecycle.EXPORTED,
    },
    RecordLifecycle.ARCHIVED: {RecordLifecycle.EXPORTED},
    RecordLifecycle.EXPORTED: set(),
}


def can_transition(current: RecordLifecycle, target: RecordLifecycle) -> bool:
    if current == target:
        return True
    return target in _ALLOWED.get(current, set())


def transition(
    execution_id: str,
    current: RecordLifecycle,
    target: RecordLifecycle,
) -> RecordLifecycle:
    if current == target:
        return current
    if not can_transition(current, target):
        raise LifecycleError(execution_id, current, target)
    return target
