"""Shared KV engine facade."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..interfaces.sharing import IKVSharingBackend
from ..utils.config import KVRuntimeConfig
from .lmdb_share import LMDBSharingBackend
from .mmap_share import MemoryMappedSharingBackend
from .redis_share import RedisSharingBackend
from .shm import SharedMemoryBackend


def build_sharing_backend(cfg: KVRuntimeConfig) -> IKVSharingBackend:
    name = (cfg.sharing_backend or "mmap").lower()
    if name in {"shm", "shared", "shared_memory"}:
        return SharedMemoryBackend()
    if name == "redis":
        return RedisSharingBackend(cfg.redis_url)
    if name == "lmdb":
        return LMDBSharingBackend(cfg.root / "share" / "lmdb")
    return MemoryMappedSharingBackend(cfg.root / "share" / "mmap")


@dataclass
class SharedKVEngine:
    backend: IKVSharingBackend

    @property
    def name(self) -> str:
        return self.backend.name

    async def store(self, key: str, data: bytes) -> None:
        await self.backend.store(key, data)

    async def load(self, key: str) -> bytes:
        return await self.backend.load(key)

    async def share(self, key: str, consumer_id: str) -> str:
        return await self.backend.share(key, consumer_id)

    async def release(self, key: str, consumer_id: str) -> None:
        await self.backend.release(key, consumer_id)

    async def reference_count(self, key: str) -> int:
        return await self.backend.reference_count(key)

    async def delete(self, key: str) -> None:
        await self.backend.delete(key)
