"""NUMA / locality-aware allocator facade."""

from __future__ import annotations

from .interfaces import IKVProvider
from .models import LocalityHint, ProviderName


class KVAllocator:
    """Chooses provider + records locality hints for HAOE affinity."""

    def __init__(
        self,
        providers: dict[str, IKVProvider],
        *,
        default_provider: ProviderName = ProviderName.RAM,
        ram_budget_bytes: int = 0,
    ) -> None:
        self.providers = providers
        self.default_provider = default_provider
        self.ram_budget_bytes = ram_budget_bytes
        self._allocated_bytes = 0

    def choose_provider(self, *, size: int, hint: LocalityHint | None = None) -> IKVProvider:
        name = self.default_provider.value
        # Under RAM pressure prefer mmap
        if self.ram_budget_bytes > 0 and (self._allocated_bytes + size) > self.ram_budget_bytes:
            name = ProviderName.MMAP.value
        prov = self.providers.get(name) or self.providers[ProviderName.RAM.value]
        return prov

    async def allocate(
        self,
        kv_id: str,
        size: int,
        *,
        hint: LocalityHint | None = None,
        provider_name: ProviderName | None = None,
    ) -> tuple[IKVProvider, str]:
        if provider_name is not None:
            prov = self.providers[provider_name.value]
        else:
            prov = self.choose_provider(size=size, hint=hint)
        loc = await prov.allocate(kv_id, size, hint=hint)
        self._allocated_bytes += size
        return prov, loc

    def release_bytes(self, size: int) -> None:
        self._allocated_bytes = max(0, self._allocated_bytes - size)

    @property
    def used_bytes(self) -> int:
        return self._allocated_bytes
