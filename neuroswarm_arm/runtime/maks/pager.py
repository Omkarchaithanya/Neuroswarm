"""Pager — page in/out between tiers via MigrationEngine + TierManager."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import KVTier, ProviderName

if TYPE_CHECKING:
    from .manager import KVManager
    from .tier_manager import TierManager


class Pager:
    """Background-friendly page demote/promote. Rollback via re-promote."""

    def __init__(self, manager: KVManager, tier_manager: TierManager) -> None:
        self.manager = manager
        self.tiers = tier_manager
        self._checkpoints: dict[str, tuple[str, str]] = {}  # kv_id → (provider, location)

    async def page_out(self, kv_id: str, *, reason: str = "pressure") -> str | None:
        rec = await self.manager.registry.get(kv_id)
        if rec is None or rec.pinned:
            return None
        self._checkpoints[kv_id] = (rec.provider.value, rec.location)
        nxt = self.tiers.next_demote(rec.provider)
        if nxt is None:
            return None
        loc = await self.manager.migrate(kv_id, nxt, reason=reason)
        if hasattr(self.manager, "pool"):
            self.manager.pool.set_tier(kv_id, self.tiers.tier_for_provider(nxt), nxt)
        return loc

    async def page_in(self, kv_id: str, *, reason: str = "warm") -> str | None:
        rec = await self.manager.registry.get(kv_id)
        if rec is None:
            return None
        nxt = self.tiers.next_promote(rec.provider)
        if nxt is None:
            return None
        loc = await self.manager.migrate(kv_id, nxt, reason=reason)
        if hasattr(self.manager, "pool"):
            self.manager.pool.set_tier(kv_id, KVTier.HOT if nxt is ProviderName.RAM else self.tiers.tier_for_provider(nxt), nxt)
        return loc

    async def rollback(self, kv_id: str) -> bool:
        """Restore last checkpointed provider if possible."""
        ckpt = self._checkpoints.get(kv_id)
        if not ckpt:
            return False
        provider, _loc = ckpt
        try:
            await self.manager.migrate(kv_id, provider, reason="rollback")
            return True
        except Exception:
            return False
