"""Perf hooks for request lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any


@dataclass
class PerfHooks:
    events: list[dict[str, Any]] = field(default_factory=list)

    def on_phase(self, phase: str, **kwargs: Any) -> None:
        self.events.append({"phase": phase, "ts": monotonic(), **kwargs})

    def clear(self) -> None:
        self.events.clear()
