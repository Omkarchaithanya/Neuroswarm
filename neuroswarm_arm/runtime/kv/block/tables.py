"""Logical -> Physical block tables (virtual memory model)."""

from __future__ import annotations

from threading import RLock
from typing import Iterable

from ..interfaces.types import PhysicalBlockRecord, StorageTier
from ..utils.hashing import stable_id
from ..utils.locks import RefCountedLock


class LogicalBlockTable:
    """Per-session mapping of logical indices to physical block IDs."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._map: dict[int, str] = {}
        self._lock = RLock()

    def map(self, logical_index: int, physical_id: str) -> None:
        with self._lock:
            self._map[int(logical_index)] = physical_id

    def unmap(self, logical_index: int) -> str | None:
        with self._lock:
            return self._map.pop(int(logical_index), None)

    def resolve(self, logical_index: int) -> str | None:
        with self._lock:
            return self._map.get(int(logical_index))

    def physical_ids(self) -> list[str]:
        with self._lock:
            return [self._map[i] for i in sorted(self._map)]

    def items(self) -> list[tuple[int, str]]:
        with self._lock:
            return sorted(self._map.items())

    def clear(self) -> None:
        with self._lock:
            self._map.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._map)

    def to_dict(self) -> dict[str, str]:
        with self._lock:
            return {str(k): v for k, v in self._map.items()}

    def load_dict(self, data: dict[str, str]) -> None:
        with self._lock:
            self._map = {int(k): str(v) for k, v in data.items()}


class PhysicalBlockTable:
    """Global physical block registry with thread-safe reference counts."""

    def __init__(self) -> None:
        self._blocks: dict[str, PhysicalBlockRecord] = {}
        self._by_hash: dict[str, str] = {}
        self._refcounts: dict[str, RefCountedLock] = {}
        self._lock = RLock()

    def register(self, record: PhysicalBlockRecord) -> PhysicalBlockRecord:
        with self._lock:
            existing = self._by_hash.get(record.content_hash)
            if existing and existing in self._blocks:
                self._refcounts[existing].acquire_ref()
                self._blocks[existing].refcount = self._refcounts[existing].count
                return self._blocks[existing]
            pid = record.physical_id or stable_id("phys")
            record.physical_id = pid
            self._blocks[pid] = record
            self._by_hash[record.content_hash] = pid
            self._refcounts[pid] = RefCountedLock(record.refcount)
            return record

    def get(self, physical_id: str) -> PhysicalBlockRecord | None:
        with self._lock:
            return self._blocks.get(physical_id)

    def get_by_hash(self, content_hash: str) -> PhysicalBlockRecord | None:
        with self._lock:
            pid = self._by_hash.get(content_hash)
            return self._blocks.get(pid) if pid else None

    def acquire(self, physical_id: str) -> int:
        with self._lock:
            rc = self._refcounts[physical_id]
            count = rc.acquire_ref()
            self._blocks[physical_id].refcount = count
            return count

    def release(self, physical_id: str) -> int:
        with self._lock:
            if physical_id not in self._refcounts:
                return 0
            count = self._refcounts[physical_id].release_ref()
            self._blocks[physical_id].refcount = count
            if count == 0:
                rec = self._blocks.pop(physical_id)
                self._by_hash.pop(rec.content_hash, None)
                self._refcounts.pop(physical_id, None)
            return count

    def update_tier(self, physical_id: str, tier: StorageTier, provider_key: str) -> None:
        with self._lock:
            rec = self._blocks[physical_id]
            rec.tier = tier
            rec.provider_key = provider_key

    def touch(self, physical_id: str, now: float) -> None:
        with self._lock:
            rec = self._blocks[physical_id]
            rec.last_access = now
            rec.access_count += 1

    def all_records(self) -> list[PhysicalBlockRecord]:
        with self._lock:
            return list(self._blocks.values())

    def replace(self, records: Iterable[PhysicalBlockRecord]) -> None:
        with self._lock:
            self._blocks.clear()
            self._by_hash.clear()
            self._refcounts.clear()
            for rec in records:
                self._blocks[rec.physical_id] = rec
                self._by_hash[rec.content_hash] = rec.physical_id
                self._refcounts[rec.physical_id] = RefCountedLock(rec.refcount)

    def __len__(self) -> int:
        with self._lock:
            return len(self._blocks)

    def shared_count(self) -> int:
        with self._lock:
            return sum(1 for r in self._blocks.values() if r.refcount > 1)
