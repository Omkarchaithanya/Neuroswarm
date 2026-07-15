"""Best-effort thread pinning via AffinityProvider."""

from __future__ import annotations

import threading
from typing import Sequence

from ..interfaces import IAffinityProvider


class ThreadPinning:
    """Pin the *current* thread when the OS supports it."""

    def __init__(self, provider: IAffinityProvider, *, enabled: bool = True) -> None:
        self._provider = provider
        self._enabled = enabled
        self._successes = 0
        self._failures = 0

    def pin(self, cores: Sequence[int]) -> bool:
        if not self._enabled or not cores:
            return False
        ok = self._provider.bind(cores)
        if ok:
            self._successes += 1
        else:
            self._failures += 1
        return ok

    def unpin(self) -> bool:
        if not self._enabled:
            return False
        return self._provider.unbind()

    @property
    def thread_name(self) -> str:
        return threading.current_thread().name

    @property
    def efficiency(self) -> float:
        total = self._successes + self._failures
        if total == 0:
            return 1.0
        return self._successes / total
