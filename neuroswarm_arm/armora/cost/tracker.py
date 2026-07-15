"""In-flight mutable cost session tracker (reports stay immutable)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from .schemas import CostPrediction, ObservedRuntimeSignals, RequestContext, utcnow


@dataclass
class CostSession:
    execution_id: str
    context: RequestContext
    prediction: CostPrediction | None = None
    observed: ObservedRuntimeSignals = field(default_factory=ObservedRuntimeSignals)
    opened_at: str = field(default_factory=lambda: utcnow().isoformat())
    closed: bool = False

    def update_observed(self, **kwargs: Any) -> None:
        data = self.observed.model_dump()
        data.update(kwargs)
        self.observed = ObservedRuntimeSignals.model_validate(data)


class CostTracker:
    """Mutable in-flight sessions keyed by execution_id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, CostSession] = {}

    def open(
        self,
        context: RequestContext,
        *,
        prediction: CostPrediction | None = None,
    ) -> CostSession:
        session = CostSession(
            execution_id=context.execution_id,
            context=context,
            prediction=prediction,
        )
        with self._lock:
            self._sessions[context.execution_id] = session
        return session

    def get(self, execution_id: str) -> CostSession | None:
        with self._lock:
            return self._sessions.get(execution_id)

    def record(self, execution_id: str, **kwargs: Any) -> CostSession | None:
        with self._lock:
            session = self._sessions.get(execution_id)
            if session is None or session.closed:
                return session
            session.update_observed(**kwargs)
            return session

    def close(self, execution_id: str) -> CostSession | None:
        with self._lock:
            session = self._sessions.pop(execution_id, None)
            if session is not None:
                session.closed = True
            return session

    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)
