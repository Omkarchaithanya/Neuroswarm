"""Retention policies — archive / expire / compact (no delete by default)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ._utils import utc_now
from .events import (
    CheckpointArchived,
    CheckpointExpired,
    EventBus,
    RetentionApplied,
)
from .exceptions import RetentionError
from .metrics import CheckpointMetrics
from .models import CheckpointStatus
from .repository import ICheckpointRepository


@dataclass
class RetentionPolicy:
    """When to archive / expire checkpoints and prune envelope metadata."""

    max_age: timedelta | None = None
    max_active_per_execution: int | None = None
    max_active_total: int | None = None
    prune_metadata_keys: tuple[str, ...] = ()
    allow_hard_delete: bool = False
    expire_archived_after: timedelta | None = None


class RetentionManager:
    """Apply retention without mutating immutable Checkpoint bodies."""

    def __init__(
        self,
        repository: ICheckpointRepository,
        *,
        events: EventBus | None = None,
        metrics: CheckpointMetrics | None = None,
    ) -> None:
        self.repository = repository
        self.events = events or EventBus()
        self.metrics = metrics or CheckpointMetrics()

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
        expired: list[str] = []
        compacted: list[str] = []

        active = list(self.repository.list_all(include_archived=False))

        if policy.max_age is not None:
            cutoff = now - policy.max_age
            for ckpt in active:
                ts = ckpt.timestamp
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    self._archive(ckpt.checkpoint_id, ckpt.workflow_id, ckpt.execution_id)
                    archived.append(ckpt.checkpoint_id)

        if policy.max_active_per_execution is not None:
            by_exec: dict[str, list] = {}
            for ckpt in self.repository.list_all(include_archived=False):
                by_exec.setdefault(ckpt.execution_id, []).append(ckpt)
            for _eid, items in by_exec.items():
                if len(items) <= policy.max_active_per_execution:
                    continue
                ordered = sorted(items, key=lambda c: c.timestamp)
                overflow = len(ordered) - policy.max_active_per_execution
                for ckpt in ordered[:overflow]:
                    if ckpt.checkpoint_id not in archived:
                        self._archive(
                            ckpt.checkpoint_id, ckpt.workflow_id, ckpt.execution_id
                        )
                        archived.append(ckpt.checkpoint_id)

        if policy.max_active_total is not None:
            active = list(self.repository.list_all(include_archived=False))
            if len(active) > policy.max_active_total:
                ordered = sorted(active, key=lambda c: c.timestamp)
                overflow = len(ordered) - policy.max_active_total
                for ckpt in ordered[:overflow]:
                    if ckpt.checkpoint_id not in archived:
                        self._archive(
                            ckpt.checkpoint_id, ckpt.workflow_id, ckpt.execution_id
                        )
                        archived.append(ckpt.checkpoint_id)

        if policy.expire_archived_after is not None:
            expire_cutoff = now - policy.expire_archived_after
            for ckpt in self.repository.list_all(include_archived=True):
                env = self.repository.get_envelope(ckpt.checkpoint_id)
                if env.status != CheckpointStatus.ARCHIVED:
                    continue
                archived_at = env.archived_at or env.recorded_at
                if archived_at.tzinfo is None:
                    archived_at = archived_at.replace(tzinfo=timezone.utc)
                if archived_at < expire_cutoff:
                    self.repository.expire(ckpt.checkpoint_id)
                    expired.append(ckpt.checkpoint_id)
                    self.events.emit(
                        CheckpointExpired(
                            ckpt.checkpoint_id,
                            workflow_id=ckpt.workflow_id,
                            execution_id=ckpt.execution_id,
                        )
                    )

        pruned = 0
        if policy.prune_metadata_keys:
            for ckpt in self.repository.list_all(include_archived=True):
                env = self.repository.get_envelope(ckpt.checkpoint_id)
                meta = dict(env.metadata)
                changed = False
                for key in policy.prune_metadata_keys:
                    if key in meta:
                        meta.pop(key)
                        changed = True
                        pruned += 1
                if changed:
                    self.repository.set_envelope(
                        env.model_copy(update={"metadata": meta})
                    )
                    compacted.append(ckpt.checkpoint_id)

        result = {
            "archived": archived,
            "expired": expired,
            "compacted": compacted,
            "pruned_keys": pruned,
        }
        self.metrics.incr("retention_operations")
        self.events.emit(RetentionApplied(**{k: len(v) if isinstance(v, list) else v for k, v in result.items()}))
        return result

    def _archive(
        self, checkpoint_id: str, workflow_id: str, execution_id: str
    ) -> None:
        self.repository.archive(checkpoint_id)
        self.events.emit(
            CheckpointArchived(
                checkpoint_id,
                workflow_id=workflow_id,
                execution_id=execution_id,
            )
        )
