"""Lifecycle and retention policies for cognitive memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.memory.schemas import MemoryRecord, MemoryType


@dataclass(slots=True)
class LifecyclePolicy:
    """Decide archival, expiry, promotion, demotion."""

    config: MemoryRuntimeConfig
    archive_importance_below: float = 0.15
    promote_importance_above: float = 0.85
    demote_importance_below: float = 0.25
    max_access_idle_seconds: int = 60 * 60 * 24 * 30  # 30d

    def default_ttl(self, memory_type: MemoryType) -> int | None:
        overrides: dict[MemoryType, int | None] = {
            MemoryType.COST: 60 * 60 * 24 * 90,
            MemoryType.LATENCY: 60 * 60 * 24 * 30,
            MemoryType.PERFORMANCE: 60 * 60 * 24 * 30,
            MemoryType.BENCHMARK: None,
            MemoryType.REFLECTION: None,
            MemoryType.SYSTEM: None,
            MemoryType.PROMPT: 60 * 60 * 24 * 60,
            MemoryType.TOOL: 60 * 60 * 24 * 90,
        }
        if memory_type in overrides:
            return overrides[memory_type]
        return self.config.default_ttl_seconds

    def is_expired(self, record: MemoryRecord, *, now: datetime | None = None) -> bool:
        if record.ttl_seconds is None:
            return False
        now = now or datetime.now(timezone.utc)
        age = (now - record.timestamp).total_seconds()
        return age > float(record.ttl_seconds)

    def should_archive(self, record: MemoryRecord) -> bool:
        if record.archived:
            return False
        if record.importance < self.archive_importance_below and record.access_count < 2:
            return True
        return False

    def should_promote(self, record: MemoryRecord) -> bool:
        return record.importance >= self.promote_importance_above and not record.archived

    def should_demote(self, record: MemoryRecord) -> bool:
        return (
            record.importance < self.demote_importance_below
            and record.access_count == 0
            and not record.archived
        )

    def apply_defaults(self, record: MemoryRecord) -> MemoryRecord:
        if record.ttl_seconds is None:
            record.ttl_seconds = self.default_ttl(record.type)
        return record
