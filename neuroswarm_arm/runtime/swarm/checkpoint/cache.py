"""In-memory cache for latest checkpoints, recovery plans, validation results."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from .checkpoint import Checkpoint
from .recovery import RecoveryPlan

T = TypeVar("T")


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: float | None = None


@dataclass
class CheckpointCache:
    """Bounded TTL cache for hot restore / planning paths."""

    max_entries: int = 1024
    default_ttl_seconds: float | None = 300.0
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _latest_execution: dict[str, _Entry[Checkpoint]] = field(default_factory=dict)
    _latest_workflow: dict[str, _Entry[Checkpoint]] = field(default_factory=dict)
    _by_id: dict[str, _Entry[Checkpoint]] = field(default_factory=dict)
    _recovery_plans: dict[str, _Entry[RecoveryPlan]] = field(default_factory=dict)
    _validation: dict[str, _Entry[bool]] = field(default_factory=dict)

    def put_checkpoint(self, checkpoint: Checkpoint) -> None:
        with self._lock:
            entry = _Entry(checkpoint, self._expiry())
            self._by_id[checkpoint.checkpoint_id] = entry
            self._latest_execution[checkpoint.execution_id] = entry
            self._latest_workflow[checkpoint.workflow_id] = entry
            self._evict_if_needed(self._by_id)

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        with self._lock:
            return self._get(self._by_id, checkpoint_id)

    def latest_for_execution(self, execution_id: str) -> Checkpoint | None:
        with self._lock:
            return self._get(self._latest_execution, execution_id)

    def latest_for_workflow(self, workflow_id: str) -> Checkpoint | None:
        with self._lock:
            return self._get(self._latest_workflow, workflow_id)

    def put_recovery_plan(self, key: str, plan: RecoveryPlan) -> None:
        with self._lock:
            self._recovery_plans[key] = _Entry(plan, self._expiry())
            self._evict_if_needed(self._recovery_plans)

    def get_recovery_plan(self, key: str) -> RecoveryPlan | None:
        with self._lock:
            return self._get(self._recovery_plans, key)

    def put_validation(self, checkpoint_id: str, ok: bool) -> None:
        with self._lock:
            self._validation[checkpoint_id] = _Entry(ok, self._expiry())
            self._evict_if_needed(self._validation)

    def get_validation(self, checkpoint_id: str) -> bool | None:
        with self._lock:
            return self._get(self._validation, checkpoint_id)

    def invalidate(self, checkpoint_id: str | None = None) -> None:
        with self._lock:
            if checkpoint_id is None:
                self._latest_execution.clear()
                self._latest_workflow.clear()
                self._by_id.clear()
                self._recovery_plans.clear()
                self._validation.clear()
                return
            self._by_id.pop(checkpoint_id, None)
            self._validation.pop(checkpoint_id, None)

    def _expiry(self) -> float | None:
        if self.default_ttl_seconds is None:
            return None
        return time.monotonic() + self.default_ttl_seconds

    def _get(self, store: dict[str, _Entry[Any]], key: str) -> Any | None:
        entry = store.get(key)
        if entry is None:
            return None
        if entry.expires_at is not None and time.monotonic() > entry.expires_at:
            store.pop(key, None)
            return None
        return entry.value

    def _evict_if_needed(self, store: dict[str, _Entry[Any]]) -> None:
        while len(store) > self.max_entries:
            store.pop(next(iter(store)))
