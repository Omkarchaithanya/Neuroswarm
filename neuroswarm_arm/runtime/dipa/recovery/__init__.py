"""DIPA recovery subsystem — retries, timeouts, circuits, fallbacks."""

from __future__ import annotations

from .circuit_breaker import CircuitBreaker, CircuitState
from .degraded_mode import DegradedMode
from .fallback_manager import FallbackKind, FallbackManager, FallbackTarget, parse_fallback
from .recovery_manager import RecoveryManager, RecoveryStack
from .retry_manager import RetryManager
from .timeout_manager import TimeoutManager

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "DegradedMode",
    "FallbackKind",
    "FallbackManager",
    "FallbackTarget",
    "RecoveryManager",
    "RecoveryStack",
    "RetryManager",
    "TimeoutManager",
    "parse_fallback",
]
