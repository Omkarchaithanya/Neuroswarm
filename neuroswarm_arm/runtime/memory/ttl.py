"""TTL expiry helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from neuroswarm_arm.runtime.memory.policies import LifecyclePolicy
from neuroswarm_arm.runtime.memory.schemas import MemoryRecord


class TTLManager:
    def __init__(self, policy: LifecyclePolicy) -> None:
        self.policy = policy

    def expired(self, record: MemoryRecord, *, now: datetime | None = None) -> bool:
        return self.policy.is_expired(record, now=now or datetime.now(timezone.utc))

    def filter_live(self, records: list[MemoryRecord]) -> list[MemoryRecord]:
        now = datetime.now(timezone.utc)
        return [r for r in records if not self.expired(r, now=now)]
