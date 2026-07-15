"""RAM backend — multiprocessing.shared_memory pools via Plane-2 RAM + optional shm share."""

from __future__ import annotations

from pathlib import Path

from neuroswarm_arm.runtime.kv.providers.ram import RAMProvider
from neuroswarm_arm.runtime.kv.sharing.shm import SharedMemoryBackend

from ..models import ProviderStats
from ._adapter import Plane2ProviderAdapter


class RAMBackend(Plane2ProviderAdapter):
    """L1 hot tier. Uses in-process RAM; share() can fan out via SharedMemoryBackend."""

    def __init__(self, *, use_shared_memory: bool = False) -> None:
        super().__init__(RAMProvider(), name="ram")
        self._shm: SharedMemoryBackend | None = SharedMemoryBackend() if use_shared_memory else None

    async def share(self, kv_id: str, consumer_id: str) -> str:
        if self._shm is not None and await self.exists(kv_id):
            data = await self.load(kv_id)
            await self._shm.store(kv_id, data)
            return await self._shm.share(kv_id, consumer_id)
        return await super().share(kv_id, consumer_id)

    async def stats(self) -> ProviderStats:
        st = await super().stats()
        st.extra["shared_memory"] = self._shm is not None
        return st


def build_ram_backend(*, root: Path | None = None, use_shared_memory: bool = False) -> RAMBackend:
    _ = root
    return RAMBackend(use_shared_memory=use_shared_memory)
