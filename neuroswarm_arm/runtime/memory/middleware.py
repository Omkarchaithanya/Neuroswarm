"""Retries + circuit breaker middleware around providers."""

from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

from neuroswarm_arm.runtime.memory.exceptions import MemoryCircuitOpenError, MemoryProviderError
from neuroswarm_arm.runtime.memory.logging import log_event

T = TypeVar("T")


class CircuitBreaker:
    def __init__(self, *, fail_threshold: int = 5, reset_seconds: float = 30.0) -> None:
        self.fail_threshold = fail_threshold
        self.reset_seconds = reset_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if time.monotonic() - self._opened_at >= self.reset_seconds:
                self._opened_at = None
                self._failures = 0
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.fail_threshold:
                self._opened_at = time.monotonic()
                log_event("circuit_open", failures=self._failures)

    @property
    def open(self) -> bool:
        return not self.allow()


def with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 2,
    circuit: CircuitBreaker | None = None,
    label: str = "memory_op",
) -> T:
    if circuit is not None and not circuit.allow():
        raise MemoryCircuitOpenError(f"circuit open for {label}")
    last_exc: Exception | None = None
    for i in range(max(1, attempts)):
        try:
            result = fn()
            if circuit is not None:
                circuit.record_success()
            return result
        except MemoryCircuitOpenError:
            raise
        except Exception as exc:  # noqa: BLE001 — provider boundary
            last_exc = exc
            if circuit is not None:
                circuit.record_failure()
            log_event("retry", label=label, attempt=i + 1, error=str(exc))
    raise MemoryProviderError(f"{label} failed after {attempts} attempts: {last_exc}") from last_exc
