"""Mutable execution-state boundary vs immutable snapshots."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .models import _Base


class MutableExecutionState(_Base):
    """Runtime-only mutable counters / scratch not frozen into snapshots by default.

    Snapshots capture a deep copy of SwarmContext; this object may sit alongside
    for executor-local bookkeeping without polluting the shared OS state.
    """

    dirty: bool = False
    local_scratch: dict[str, Any] = Field(default_factory=dict)
    pending_events: list[str] = Field(default_factory=list)
    cancel_requested: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    def mark_dirty(self) -> MutableExecutionState:
        return self.model_copy(update={"dirty": True})

    def clear(self) -> MutableExecutionState:
        return MutableExecutionState()

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")
