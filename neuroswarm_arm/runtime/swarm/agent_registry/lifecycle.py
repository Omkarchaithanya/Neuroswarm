"""Agent lifecycle states and legal transitions."""

from __future__ import annotations

from enum import Enum

from .exceptions import LifecycleError


class LifecycleState(str, Enum):
    """Runtime lifecycle for a registered agent capability."""

    CREATED = "created"
    REGISTERED = "registered"
    LOADED = "loaded"
    READY = "ready"
    BUSY = "busy"
    PAUSED = "paused"
    DISABLED = "disabled"
    FAILED = "failed"
    RESTARTING = "restarting"
    RETIRED = "retired"


# Allowed transitions: current -> frozenset of targets
_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.CREATED: frozenset(
        {LifecycleState.REGISTERED, LifecycleState.RETIRED}
    ),
    LifecycleState.REGISTERED: frozenset(
        {
            LifecycleState.LOADED,
            LifecycleState.DISABLED,
            LifecycleState.RETIRED,
            LifecycleState.FAILED,
        }
    ),
    LifecycleState.LOADED: frozenset(
        {
            LifecycleState.READY,
            LifecycleState.DISABLED,
            LifecycleState.FAILED,
            LifecycleState.RETIRED,
        }
    ),
    LifecycleState.READY: frozenset(
        {
            LifecycleState.BUSY,
            LifecycleState.PAUSED,
            LifecycleState.DISABLED,
            LifecycleState.FAILED,
            LifecycleState.RETIRED,
        }
    ),
    LifecycleState.BUSY: frozenset(
        {
            LifecycleState.READY,
            LifecycleState.PAUSED,
            LifecycleState.FAILED,
            LifecycleState.DISABLED,
        }
    ),
    LifecycleState.PAUSED: frozenset(
        {
            LifecycleState.READY,
            LifecycleState.DISABLED,
            LifecycleState.RETIRED,
            LifecycleState.FAILED,
        }
    ),
    LifecycleState.DISABLED: frozenset(
        {
            LifecycleState.READY,
            LifecycleState.LOADED,
            LifecycleState.RETIRED,
            LifecycleState.RESTARTING,
        }
    ),
    LifecycleState.FAILED: frozenset(
        {
            LifecycleState.RESTARTING,
            LifecycleState.DISABLED,
            LifecycleState.RETIRED,
        }
    ),
    LifecycleState.RESTARTING: frozenset(
        {
            LifecycleState.LOADED,
            LifecycleState.READY,
            LifecycleState.FAILED,
            LifecycleState.RETIRED,
        }
    ),
    LifecycleState.RETIRED: frozenset(),
}


def can_transition(current: LifecycleState, target: LifecycleState) -> bool:
    if current is target:
        return True
    return target in _TRANSITIONS.get(current, frozenset())


def transition(
    agent_id: str,
    current: LifecycleState,
    target: LifecycleState,
) -> LifecycleState:
    """Return target if legal; raise LifecycleError otherwise."""
    if can_transition(current, target):
        return target
    raise LifecycleError(agent_id, current, target)


def is_selectable(state: LifecycleState) -> bool:
    """Whether agent may be considered by the selector."""
    return state in {LifecycleState.READY, LifecycleState.BUSY}


def is_active(state: LifecycleState) -> bool:
    return state not in {
        LifecycleState.DISABLED,
        LifecycleState.RETIRED,
        LifecycleState.FAILED,
        LifecycleState.CREATED,
    }
