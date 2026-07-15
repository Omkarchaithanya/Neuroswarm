"""Content-hash deduplication engine."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from ..block.tables import PhysicalBlockTable
from ..interfaces.types import PhysicalBlockRecord
from ..utils.hashing import content_hash


@dataclass
class DedupResult:
    physical_id: str
    reused: bool
    content_hash: str


class DeduplicationEngine:
    """Reuse identical physical blocks via content hash."""

    def __init__(self, physical: PhysicalBlockTable) -> None:
        self.physical = physical
        self._lock = RLock()
        self.lookups = 0
        self.hits = 0

    def find(self, payload: bytes) -> PhysicalBlockRecord | None:
        h = content_hash(payload)
        with self._lock:
            self.lookups += 1
            rec = self.physical.get_by_hash(h)
            if rec is not None:
                self.hits += 1
            return rec

    def register_or_reuse(self, record: PhysicalBlockRecord, payload: bytes) -> DedupResult:
        h = content_hash(payload)
        record.content_hash = h
        with self._lock:
            self.lookups += 1
            existing = self.physical.get_by_hash(h)
            if existing is not None:
                self.hits += 1
                self.physical.acquire(existing.physical_id)
                return DedupResult(
                    physical_id=existing.physical_id,
                    reused=True,
                    content_hash=h,
                )
            registered = self.physical.register(record)
            return DedupResult(
                physical_id=registered.physical_id,
                reused=False,
                content_hash=h,
            )

    @property
    def dedup_ratio(self) -> float:
        with self._lock:
            if self.lookups == 0:
                return 0.0
            return float(self.hits) / float(self.lookups)
