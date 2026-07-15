"""Temperature-based eviction (cold first)."""

from __future__ import annotations

from ..interfaces import IEvictionPolicy
from ..models import KVRegistryRecord, KVTier
from .lru import _pick

_TIER_RANK = {KVTier.COLD: 0, KVTier.WARM: 1, KVTier.HOT: 2}


class TemperaturePolicy(IEvictionPolicy):
    def select_victims(
        self,
        records: list[KVRegistryRecord],
        *,
        bytes_needed: int = 0,
        count: int = 1,
    ) -> list[str]:
        candidates = [r for r in records if not r.pinned and r.refcount <= 1]
        candidates.sort(key=lambda r: (_TIER_RANK.get(r.tier, 1), r.last_access))
        return _pick(candidates, bytes_needed=bytes_needed, count=count)
