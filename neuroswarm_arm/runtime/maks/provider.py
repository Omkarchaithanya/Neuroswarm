"""MAKS KVProvider ABC re-export + base adapter helpers."""

from __future__ import annotations

from .interfaces import IKVProvider, KVProvider
from .models import LocalityHint, ProviderStats

__all__ = ["IKVProvider", "KVProvider", "LocalityHint", "ProviderStats", "BaseKVProvider"]


class BaseKVProvider(IKVProvider):
    """Shared pin/warm bookkeeping for adapters."""

    AVAILABLE = True

    def __init__(self) -> None:
        self._pinned: set[str] = set()
        self._warm: set[str] = set()
        self._cold: set[str] = set()
        self._locations: dict[str, str] = {}

    async def allocate(self, kv_id: str, size: int, *, hint: LocalityHint | None = None) -> str:
        loc = f"{self.name}://{kv_id}"
        self._locations[kv_id] = loc
        return loc

    async def share(self, kv_id: str, consumer_id: str) -> str:
        return f"share:{kv_id}:{consumer_id}"

    async def migrate(self, kv_id: str, target: IKVProvider) -> str:
        data = await self.load(kv_id)
        await target.store(kv_id, data)
        await target.allocate(kv_id, len(data))
        await self.delete(kv_id)
        return f"{target.name}://{kv_id}"

    async def pin(self, kv_id: str) -> None:
        self._pinned.add(kv_id)
        self._cold.discard(kv_id)

    async def unpin(self, kv_id: str) -> None:
        self._pinned.discard(kv_id)

    async def warm(self, kv_id: str) -> None:
        self._warm.add(kv_id)
        self._cold.discard(kv_id)

    async def cold(self, kv_id: str) -> None:
        if kv_id in self._pinned:
            return
        self._cold.add(kv_id)
        self._warm.discard(kv_id)

    async def flush(self) -> None:
        return None

    def is_pinned(self, kv_id: str) -> bool:
        return kv_id in self._pinned
