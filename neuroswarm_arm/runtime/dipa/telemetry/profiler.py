"""Lightweight profiler hooks."""

from __future__ import annotations

from time import monotonic
from typing import Any


class Profiler:
    def __init__(self) -> None:
        self._marks: dict[str, float] = {}

    def mark(self, name: str) -> None:
        self._marks[name] = monotonic()

    def elapsed_ms(self, name: str) -> float:
        start = self._marks.get(name)
        if start is None:
            return 0.0
        return (monotonic() - start) * 1000.0

    def snapshot(self) -> dict[str, Any]:
        return {k: self.elapsed_ms(k) for k in self._marks}
