"""KV lifecycle state machine."""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock

from .exceptions import KVStateError
from .models import KVState

# Allowed transitions (from -> set of to)
_TRANSITIONS: dict[KVState, set[KVState]] = {
    KVState.ALLOCATED: {KVState.WARMED, KVState.SHARED, KVState.PINNED, KVState.RELEASED, KVState.DESTROYED},
    KVState.WARMED: {KVState.SHARED, KVState.PINNED, KVState.MIGRATED, KVState.RELEASED, KVState.EVICTED},
    KVState.SHARED: {KVState.PINNED, KVState.MIGRATED, KVState.WARMED, KVState.RELEASED, KVState.EVICTED},
    KVState.PINNED: {KVState.SHARED, KVState.WARMED, KVState.MIGRATED, KVState.RELEASED},
    KVState.MIGRATED: {KVState.WARMED, KVState.SHARED, KVState.PINNED, KVState.RELEASED, KVState.EVICTED},
    KVState.RELEASED: {KVState.EVICTED, KVState.DESTROYED, KVState.WARMED},
    KVState.EVICTED: {KVState.DESTROYED, KVState.ALLOCATED},
    KVState.DESTROYED: set(),
}

LifecycleCallback = Callable[[str, KVState, KVState], None]


class LifecycleManager:
    """Per-KV state machine with optional callbacks."""

    def __init__(self) -> None:
        self._states: dict[str, KVState] = {}
        self._callbacks: list[LifecycleCallback] = []
        self._lock = RLock()

    def on_transition(self, cb: LifecycleCallback) -> None:
        self._callbacks.append(cb)

    def get(self, kv_id: str) -> KVState | None:
        with self._lock:
            return self._states.get(kv_id)

    def bind(self, kv_id: str, state: KVState = KVState.ALLOCATED) -> KVState:
        with self._lock:
            self._states[kv_id] = state
            return state

    def transition(self, kv_id: str, to: KVState) -> KVState:
        with self._lock:
            cur = self._states.get(kv_id)
            if cur is None:
                raise KVStateError(f"unknown kv_id={kv_id}")
            allowed = _TRANSITIONS.get(cur, set())
            if to not in allowed:
                raise KVStateError(f"illegal transition {cur.value} → {to.value} for {kv_id}")
            self._states[kv_id] = to
            for cb in self._callbacks:
                cb(kv_id, cur, to)
            return to

    def try_transition(self, kv_id: str, to: KVState) -> bool:
        try:
            self.transition(kv_id, to)
            return True
        except KVStateError:
            return False

    def unbind(self, kv_id: str) -> None:
        with self._lock:
            self._states.pop(kv_id, None)

    def is_pinned(self, kv_id: str) -> bool:
        return self.get(kv_id) is KVState.PINNED
