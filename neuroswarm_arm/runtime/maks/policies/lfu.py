"""LFU eviction policy."""

from __future__ import annotations

from ..interfaces import IEvictionPolicy
from ..models import KVRegistryRecord
from .lru import _pick


class LFUPolicy(IEvictionPolicy):
    def select_victims(
        self,
        records: list[KVRegistryRecord],
        *,
        bytes_needed: int = 0,
        count: int = 1,
    ) -> list[str]:
        candidates = [r for r in records if not r.pinned and r.refcount <= 1]
        candidates.sort(key=lambda r: (r.access_count, r.last_access))
        return _pick(candidates, bytes_needed=bytes_needed, count=count)
