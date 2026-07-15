"""Best-effort CPU affinity binder."""

from __future__ import annotations

import os
import sys
from typing import Sequence


class AffinityBinder:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._bound: list[int] = []

    def bind(self, cores: Sequence[int]) -> bool:
        if not self.enabled or not cores:
            return False
        if sys.platform != "linux":
            return False
        try:
            os.sched_setaffinity(0, set(int(c) for c in cores))
            self._bound = list(cores)
            return True
        except (AttributeError, OSError, ValueError, PermissionError):
            return False

    def unbind(self) -> bool:
        if sys.platform != "linux":
            return False
        try:
            n = os.cpu_count() or 1
            os.sched_setaffinity(0, set(range(n)))
            self._bound = []
            return True
        except (AttributeError, OSError, PermissionError):
            return False

    def current(self) -> list[int]:
        if sys.platform != "linux":
            return list(self._bound)
        try:
            return sorted(os.sched_getaffinity(0))
        except (AttributeError, OSError):
            return list(self._bound)
