"""Lifecycle transitions for rollback operation status."""

from __future__ import annotations

from .exceptions import LifecycleError
from .models import RollbackStatus

_ALLOWED: dict[RollbackStatus, set[RollbackStatus]] = {
    RollbackStatus.PENDING: {
        RollbackStatus.VALIDATED,
        RollbackStatus.CANCELLED,
        RollbackStatus.FAILED,
    },
    RollbackStatus.VALIDATED: {
        RollbackStatus.PREPARED,
        RollbackStatus.CANCELLED,
        RollbackStatus.FAILED,
    },
    RollbackStatus.PREPARED: {
        RollbackStatus.COMPLETED,
        RollbackStatus.CANCELLED,
        RollbackStatus.FAILED,
    },
    RollbackStatus.COMPLETED: set(),
    RollbackStatus.FAILED: set(),
    RollbackStatus.CANCELLED: set(),
}


def can_transition(current: RollbackStatus, target: RollbackStatus) -> bool:
    if current == target:
        return True
    return target in _ALLOWED.get(current, set())


def transition(
    rollback_id: str,
    current: RollbackStatus,
    target: RollbackStatus,
) -> RollbackStatus:
    if current == target:
        return current
    if not can_transition(current, target):
        raise LifecycleError(rollback_id, current, target)
    return target
