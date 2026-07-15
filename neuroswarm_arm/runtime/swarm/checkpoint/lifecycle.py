"""Lifecycle transitions for checkpoint envelopes (not checkpoint bodies)."""

from __future__ import annotations

from .exceptions import LifecycleError
from .models import CheckpointStatus

_ALLOWED: dict[CheckpointStatus, set[CheckpointStatus]] = {
    CheckpointStatus.ACTIVE: {
        CheckpointStatus.ARCHIVED,
        CheckpointStatus.EXPIRED,
        CheckpointStatus.COMPACTED,
    },
    CheckpointStatus.ARCHIVED: {
        CheckpointStatus.EXPIRED,
        CheckpointStatus.COMPACTED,
    },
    CheckpointStatus.COMPACTED: {CheckpointStatus.EXPIRED},
    CheckpointStatus.EXPIRED: set(),
}


def can_transition(current: CheckpointStatus, target: CheckpointStatus) -> bool:
    if current == target:
        return True
    return target in _ALLOWED.get(current, set())


def transition(
    checkpoint_id: str,
    current: CheckpointStatus,
    target: CheckpointStatus,
) -> CheckpointStatus:
    if current == target:
        return current
    if not can_transition(current, target):
        raise LifecycleError(checkpoint_id, current, target)
    return target
