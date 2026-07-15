"""Cost-aware eviction — prefer low reuse / high size / low priority."""

from __future__ import annotations

from ..interfaces import IEvictionPolicy
from ..models import KVRegistryRecord
from .lru import _pick


class CostAwarePolicy(IEvictionPolicy):
    def select_victims(
        self,
        records: list[KVRegistryRecord],
        *,
        bytes_needed: int = 0,
        count: int = 1,
    ) -> list[str]:
        candidates = [r for r in records if not r.pinned and r.refcount <= 1]

        def score(r: KVRegistryRecord) -> float:
            # Higher score = better eviction candidate
            reuse = max(1, r.metadata.reuse_count + r.access_count)
            size = max(1, r.metadata.kv_size)
            return (size / reuse) - (r.priority * 1000.0) - r.cost_score

        candidates.sort(key=score, reverse=True)
        return _pick(candidates, bytes_needed=bytes_needed, count=count)
