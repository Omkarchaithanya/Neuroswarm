"""Tier manager — Hot / Warm / Cold placement over provider HAL."""

from __future__ import annotations

from .interfaces import IKVProvider
from .models import KVTier, ProviderName


# Canonical demotion / promotion ladders (CXL last — stub until AVAILABLE)
DEMOTE_LADDER: tuple[ProviderName, ...] = (
    ProviderName.RAM,
    ProviderName.MMAP,
    ProviderName.REDIS,
    ProviderName.NVME,
    ProviderName.FUTURE_CXL,
)

PROMOTE_LADDER: tuple[ProviderName, ...] = tuple(reversed(DEMOTE_LADDER[:-1]))  # skip CXL on promote


class TierManager:
    """Map logical tiers ↔ providers. Upper layers never import provider impls."""

    TIER_DEFAULT_PROVIDER = {
        KVTier.HOT: ProviderName.RAM,
        KVTier.WARM: ProviderName.MMAP,
        KVTier.COLD: ProviderName.NVME,
    }

    def __init__(self, providers: dict[str, IKVProvider]) -> None:
        self.providers = providers

    def provider_for_tier(self, tier: KVTier) -> IKVProvider:
        name = self.TIER_DEFAULT_PROVIDER[tier]
        key = name.value
        if key in self.providers and getattr(self.providers[key], "AVAILABLE", True):
            return self.providers[key]
        # Fallback cascade
        for candidate in DEMOTE_LADDER:
            p = self.providers.get(candidate.value)
            if p is not None and getattr(p, "AVAILABLE", True):
                return p
        raise RuntimeError("no available KV providers")

    def next_demote(self, current: ProviderName | str) -> ProviderName | None:
        cur = current if isinstance(current, ProviderName) else ProviderName(str(current).lower())
        try:
            idx = DEMOTE_LADDER.index(cur)
        except ValueError:
            return ProviderName.MMAP
        for nxt in DEMOTE_LADDER[idx + 1 :]:
            p = self.providers.get(nxt.value)
            if p is not None and getattr(p, "AVAILABLE", True):
                return nxt
        return None

    def next_promote(self, current: ProviderName | str) -> ProviderName | None:
        cur = current if isinstance(current, ProviderName) else ProviderName(str(current).lower())
        order = list(PROMOTE_LADDER)
        try:
            idx = order.index(cur)
        except ValueError:
            return ProviderName.RAM
        for nxt in order[idx + 1 :]:
            p = self.providers.get(nxt.value)
            if p is not None and getattr(p, "AVAILABLE", True):
                return nxt
        if cur is not ProviderName.RAM:
            return ProviderName.RAM
        return None

    def tier_for_provider(self, provider: ProviderName | str) -> KVTier:
        name = provider if isinstance(provider, ProviderName) else ProviderName(str(provider).lower())
        if name is ProviderName.RAM or name is ProviderName.FUTURE_MTE:
            return KVTier.HOT
        if name in {ProviderName.MMAP, ProviderName.REDIS}:
            return KVTier.WARM
        return KVTier.COLD

    def distribution(self, provider_counts: dict[str, int]) -> dict[str, int]:
        out = {"hot": 0, "warm": 0, "cold": 0}
        for name, count in provider_counts.items():
            try:
                tier = self.tier_for_provider(name)
            except Exception:
                tier = KVTier.COLD
            out[tier.value] += count
        return out
