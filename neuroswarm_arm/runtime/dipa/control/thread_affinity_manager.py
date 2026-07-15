"""ThreadAffinityManager — best-effort CPU pinning (Axion-safe)."""

from __future__ import annotations

import os
import threading
from typing import Any, Mapping, Sequence


class ThreadAffinityManager:
    def __init__(self) -> None:
        self._applied: dict[str, list[int]] = {}
        self._supported = hasattr(os, "sched_setaffinity")

    @property
    def supported(self) -> bool:
        return bool(self._supported)

    def available_cpus(self) -> list[int]:
        if self._supported:
            try:
                return sorted(os.sched_getaffinity(0))
            except Exception:
                pass
        n = os.cpu_count() or 1
        return list(range(n))

    def bind(self, name: str, cpus: Sequence[int]) -> bool:
        cpu_set = set(int(c) for c in cpus)
        if not cpu_set:
            return False
        if not self._supported:
            self._applied[name] = sorted(cpu_set)
            return False
        try:
            os.sched_setaffinity(0, cpu_set)
            self._applied[name] = sorted(cpu_set)
            return True
        except Exception:
            self._applied[name] = sorted(cpu_set)
            return False

    def bind_current_thread(self, cpus: Sequence[int]) -> bool:
        return self.bind(f"thread-{threading.get_ident()}", cpus)

    def snapshot(self) -> Mapping[str, Any]:
        return {
            "supported": self._supported,
            "available": self.available_cpus(),
            "applied": dict(self._applied),
        }
