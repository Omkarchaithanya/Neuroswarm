"""Per-backend circuit breaker with failure threshold and reset window."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _Breaker:
    failures: int = 0
    opened_at: float = 0.0
    state: CircuitState = CircuitState.CLOSED


@dataclass
class CircuitBreaker:
    """Trip open after *failure_threshold* failures; reset after *reset_window_s*."""

    failure_threshold: int = 5
    reset_window_s: float = 30.0
    _breakers: dict[str, _Breaker] = field(default_factory=dict, init=False, repr=False)

    def _entry(self, backend: str) -> _Breaker:
        if backend not in self._breakers:
            self._breakers[backend] = _Breaker()
        return self._breakers[backend]

    def allow(self, backend: str) -> bool:
        """Return ``True`` when calls to *backend* are permitted."""
        br = self._entry(backend)
        if br.state == CircuitState.CLOSED:
            return True
        if br.state == CircuitState.OPEN:
            if (time.monotonic() - br.opened_at) >= self.reset_window_s:
                br.state = CircuitState.HALF_OPEN
                return True
            return False
        # HALF_OPEN — allow a probe
        return True

    def record_success(self, backend: str) -> None:
        br = self._entry(backend)
        br.failures = 0
        br.state = CircuitState.CLOSED
        br.opened_at = 0.0

    def record_failure(self, backend: str) -> None:
        br = self._entry(backend)
        br.failures += 1
        if br.state == CircuitState.HALF_OPEN or br.failures >= self.failure_threshold:
            br.state = CircuitState.OPEN
            br.opened_at = time.monotonic()

    def state(self, backend: str) -> CircuitState:
        br = self._entry(backend)
        if br.state == CircuitState.OPEN and (
            time.monotonic() - br.opened_at
        ) >= self.reset_window_s:
            br.state = CircuitState.HALF_OPEN
        return br.state

    def reset(self, backend: str | None = None) -> None:
        if backend is None:
            self._breakers.clear()
            return
        self._breakers.pop(backend, None)
