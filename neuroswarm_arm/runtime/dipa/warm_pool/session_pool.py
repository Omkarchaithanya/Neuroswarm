"""Session warm pool."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import monotonic


@dataclass
class SessionSlot:
    session_id: str
    model: str = ""
    created: float = field(default_factory=monotonic)


class SessionPool:
    def __init__(self, max_sessions: int = 1024) -> None:
        self.max_sessions = max_sessions
        self._lock = Lock()
        self._sessions: dict[str, SessionSlot] = {}

    def bind(self, session_id: str, model: str) -> None:
        with self._lock:
            if len(self._sessions) >= self.max_sessions and session_id not in self._sessions:
                oldest = min(self._sessions.values(), key=lambda s: s.created)
                self._sessions.pop(oldest.session_id, None)
            self._sessions[session_id] = SessionSlot(session_id=session_id, model=model)

    def get(self, session_id: str) -> SessionSlot | None:
        with self._lock:
            return self._sessions.get(session_id)
