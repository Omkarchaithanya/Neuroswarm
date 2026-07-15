"""Profiling lifecycle orchestration."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LifecyclePhase(str, Enum):
    UNINITIALIZED = "uninitialized"
    INITIALIZED = "initialized"
    CAPABILITY_DETECTED = "capability_detected"
    COLLECTING = "collecting"
    EXPORTING = "exporting"
    SHUTDOWN = "shutdown"


class ProfilingLifecycle:
    """Tracks RPF lifecycle; failures never propagate."""

    def __init__(self) -> None:
        self.phase = LifecyclePhase.UNINITIALIZED
        self.last_error = ""

    def transition(self, phase: LifecyclePhase) -> None:
        self.phase = phase

    def run_safe(self, label: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            self.last_error = f"{label}: {exc}"
            logger.warning("rpf lifecycle %s failed: %s", label, exc)
            return None
