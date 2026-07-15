"""Global runtime lifecycle state."""

from __future__ import annotations

from enum import Enum
from threading import RLock


class KernelState(str, Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    DEGRADED = "degraded"


class RuntimeState:
    def __init__(self) -> None:
        self._lock = RLock()
        self.state = KernelState.CREATED
        self.active_sessions = 0
        self.total_requests = 0

    def set(self, state: KernelState) -> None:
        with self._lock:
            self.state = state

    def bump_request(self) -> None:
        with self._lock:
            self.total_requests += 1

    def enter_session(self) -> None:
        with self._lock:
            self.active_sessions += 1

    def leave_session(self) -> None:
        with self._lock:
            self.active_sessions = max(0, self.active_sessions - 1)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": self.state.value,
                "active_sessions": self.active_sessions,
                "total_requests": self.total_requests,
            }
