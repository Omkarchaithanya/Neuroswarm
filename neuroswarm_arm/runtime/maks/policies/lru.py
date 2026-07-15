"""LRU eviction policy."""

from __future__ import annotations

from ..interfaces import IEvictionPolicy
from ..models import KVRegistryRecord


class LRUPolicy(IEvictionPolicy):
    def select_victims(
        self,
        records: list[KVRegistryRecord],
        *,
        bytes_needed: int = 0,
        count: int = 1,
    ) -> list[str]:
        candidates = [r for r in records if not r.pinned and r.refcount <= 1]
        candidates.sort(key=lambda r: r.last_access)
        return _pick(candidates, bytes_needed=bytes_needed, count=count)


def _pick(candidates: list[KVRegistryRecord], *, bytes_needed: int, count: int) -> list[str]:
    out: list[str] = []
    freed = 0
    for rec in candidates:
        out.append(rec.kv_id)
        freed += rec.metadata.kv_size
        if bytes_needed > 0 and freed >= bytes_needed:
            break
        if bytes_needed <= 0 and len(out) >= count:
            break
    return out
