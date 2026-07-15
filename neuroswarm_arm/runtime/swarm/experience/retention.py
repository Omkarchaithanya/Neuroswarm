"""Retention policies — archive / compact / prune metadata (no delete by default)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ._utils import utc_now
from .events import EventBus, ExecutionArchived
from .exceptions import RetentionError
from .lifecycle import transition
from .metrics import ExperienceMetrics
from .models import RecordEnvelope, RecordLifecycle
from .repository import IExperienceRepository


@dataclass
class RetentionPolicy:
    """When to archive active executions and prune envelope metadata."""

    max_age: timedelta | None = None
    max_active_records: int | None = None
    prune_metadata_keys: tuple[str, ...] = ()
    allow_hard_delete: bool = False


class RetentionManager:
    """Apply retention without mutating immutable ExecutionRecord bodies."""

    def __init__(
        self,
        repository: IExperienceRepository,
        *,
        events: EventBus | None = None,
        metrics: ExperienceMetrics | None = None,
    ) -> None:
        self.repository = repository
        self.events = events or EventBus()
        self.metrics = metrics or ExperienceMetrics()

    def apply(
        self,
        policy: RetentionPolicy,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if policy.allow_hard_delete:
            raise RetentionError(
                "hard delete disabled by default; set allow_hard_delete only via "
                "explicit future extension"
            )
        now = now or utc_now()
        archived: list[str] = []
        active = list(self.repository.list_executions())

        # Age-based archive
        if policy.max_age is not None:
            cutoff = now - policy.max_age
            for record in active:
                ts = record.timestamp
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    self._archive(record.execution_id, record.workflow_id)
                    archived.append(record.execution_id)

        # Count-based archive (oldest first)
        if policy.max_active_records is not None:
            active = list(self.repository.list_executions())
            if len(active) > policy.max_active_records:
                ordered = sorted(active, key=lambda r: r.timestamp)
                overflow = len(ordered) - policy.max_active_records
                for record in ordered[:overflow]:
                    if record.execution_id not in archived:
                        self._archive(record.execution_id, record.workflow_id)
                        archived.append(record.execution_id)

        pruned = 0
        if policy.prune_metadata_keys:
            pruned = self._prune_envelope_metadata(policy.prune_metadata_keys)

        self.repository.index().compact()
        self.metrics.incr("retention_operations")
        return {
            "archived": archived,
            "archived_count": len(archived),
            "metadata_keys_pruned": pruned,
            "compacted": True,
        }

    def archive(self, execution_id: str) -> RecordEnvelope:
        record = self.repository.get_execution(execution_id)
        return self._archive(execution_id, record.workflow_id)

    def compact(self) -> None:
        self.repository.index().compact()
        self.metrics.incr("retention_operations")

    def _archive(self, execution_id: str, workflow_id: str | None) -> RecordEnvelope:
        env = self.repository.get_envelope(execution_id)
        transition(execution_id, env.lifecycle, RecordLifecycle.ARCHIVED)
        updated = self.repository.archive_execution(execution_id)
        self.events.emit(ExecutionArchived(execution_id, workflow_id))
        return updated

    def _prune_envelope_metadata(self, keys: tuple[str, ...]) -> int:
        pruned = 0
        for record in self.repository.list_executions():
            try:
                env = self.repository.get_envelope(record.execution_id)
            except Exception:
                continue
            meta = dict(env.metadata)
            changed = False
            for key in keys:
                if key in meta:
                    del meta[key]
                    changed = True
                    pruned += 1
            if changed:
                self.repository.set_envelope(
                    RecordEnvelope(
                        execution_id=env.execution_id,
                        lifecycle=env.lifecycle,
                        recorded_at=env.recorded_at,
                        archived_at=env.archived_at,
                        exported_at=env.exported_at,
                        metadata=meta,
                    )
                )
        return pruned
