"""Thread-safe reference counting helpers."""

from __future__ import annotations

from threading import RLock


class RefCountedLock:
    """RLock-backed reference counter used by physical blocks and sharing."""

    def __init__(self, initial: int = 0) -> None:
        self._lock = RLock()
        self._count = int(initial)

    def acquire_ref(self) -> int:
        with self._lock:
            self._count += 1
            return self._count

    def release_ref(self) -> int:
        with self._lock:
            if self._count <= 0:
                self._count = 0
                return 0
            self._count -= 1
            return self._count

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def set(self, value: int) -> None:
        with self._lock:
            self._count = max(0, int(value))
