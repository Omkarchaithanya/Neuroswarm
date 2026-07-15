"""Migration engine — move KV across RAM/mmap/Redis/NVMe."""

from __future__ import annotations

from .exceptions import KVNotFoundError, KVProviderUnavailableError, KVPinnedError
from .interfaces import IKVProvider
from .metadata import now_ts
from .models import KVTier, MigrationEvent, ProviderName
from .registry import KVRegistry

_PROVIDER_TIER = {
    ProviderName.RAM: KVTier.HOT,
    ProviderName.MMAP: KVTier.WARM,
    ProviderName.REDIS: KVTier.WARM,
    ProviderName.NVME: KVTier.COLD,
}

_COOLER = [ProviderName.RAM, ProviderName.MMAP, ProviderName.REDIS, ProviderName.NVME]


class MigrationEngine:
    def __init__(
        self,
        registry: KVRegistry,
        providers: dict[str, IKVProvider],
    ) -> None:
        self.registry = registry
        self.providers = providers
        self.migration_count = 0

    def get_provider(self, name: ProviderName | str) -> IKVProvider:
        key = name.value if isinstance(name, ProviderName) else name
        prov = self.providers.get(key)
        if prov is None:
            raise KVNotFoundError(f"provider {key}")
        if not getattr(prov, "AVAILABLE", True):
            raise KVProviderUnavailableError(key)
        return prov

    async def migrate(
        self,
        kv_id: str,
        target: ProviderName | str,
        *,
        reason: str = "",
    ) -> str:
        rec = await self.registry.get(kv_id)
        if rec is None:
            raise KVNotFoundError(kv_id)
        if rec.pinned and reason not in {"pin_preserve", "admin"}:
            # Allow migrate while pinned only for admin
            pass

        target_name = ProviderName(target) if isinstance(target, str) else target
        if rec.provider is target_name:
            return rec.location

        src = self.get_provider(rec.provider)
        dst = self.get_provider(target_name)
        data = await src.load(kv_id)
        await dst.allocate(kv_id, len(data))
        await dst.store(kv_id, data)
        try:
            await src.delete(kv_id)
        except Exception:
            pass

        event = MigrationEvent(
            ts=now_ts(),
            from_provider=rec.provider.value,
            to_provider=target_name.value,
            reason=reason,
        )
        rec.migration_history.append(event)
        rec.provider = target_name
        rec.location = f"{target_name.value}://{kv_id}"
        rec.tier = _PROVIDER_TIER.get(target_name, KVTier.WARM)
        rec.metadata.migration_count += 1
        rec.metadata.backend = target_name.value
        await self.registry.upsert(rec)
        self.migration_count += 1
        return rec.location

    async def demote(self, kv_id: str, *, reason: str = "pressure") -> str | None:
        rec = await self.registry.get(kv_id)
        if rec is None or rec.pinned:
            return None
        try:
            idx = _COOLER.index(rec.provider)
        except ValueError:
            return None
        if idx >= len(_COOLER) - 1:
            return None
        return await self.migrate(kv_id, _COOLER[idx + 1], reason=reason)

    async def promote(self, kv_id: str, *, reason: str = "reuse") -> str | None:
        rec = await self.registry.get(kv_id)
        if rec is None:
            return None
        try:
            idx = _COOLER.index(rec.provider)
        except ValueError:
            return None
        if idx <= 0:
            return None
        return await self.migrate(kv_id, _COOLER[idx - 1], reason=reason)
