"""ARM MTE KV provider — tagged mmap sharing via IKVProvider."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from ..exceptions import KVProviderUnavailableError
from ..models import LocalityHint, ProviderStats
from ..native import mte as native_mte
from ..provider import BaseKVProvider
from ..sharing import SharingEngine


@dataclass(slots=True)
class _MTERegion:
    ptr: int
    size: int  # aligned byte size
    data_len: int = 0


class MTEBackend(BaseKVProvider):
    """Memory Tagging Extension zero-copy sharing when hardware exposes user-space MTE."""

    AVAILABLE: bool = native_mte.AVAILABLE

    def __init__(self) -> None:
        super().__init__()
        self._sharing = SharingEngine()
        self._regions: dict[str, _MTERegion] = {}
        self._tag_counter = 0
        if self.AVAILABLE:
            native_mte.enable_mte_sync()
            native_mte.install_tag_fault_handler(self._fault_lookup)

    @property
    def name(self) -> str:
        return "future_mte"

    def _raise(self) -> None:
        raise KVProviderUnavailableError(
            "ARM MTE not exposed in user-space on GCP Axion; use ram/mmap/redis/nvme"
        )

    def _require_available(self) -> None:
        if not self.AVAILABLE:
            self._raise()

    def _next_tag(self) -> int:
        try:
            with open("/dev/urandom", "rb") as ur:
                byte = ur.read(1)
            if byte:
                return (byte[0] % 15) + 1
        except OSError:
            pass
        self._tag_counter = (self._tag_counter % 15) + 1
        return self._tag_counter

    def _fault_lookup(self, addr: int) -> tuple[str, str, int] | None:
        for kv_id, region in self._regions.items():
            base = region.ptr
            end = base + region.size
            if base <= addr < end:
                for consumer in self._sharing.consumers(kv_id):
                    tag = self._sharing.mte_tag(kv_id, consumer)
                    if tag is not None:
                        return kv_id, consumer, tag
        return None

    def resolve_kv_for_consumer(self, consumer_id: str) -> str | None:
        return self._sharing.kv_for_consumer(consumer_id)

    async def allocate(self, kv_id: str, size: int, *, hint: LocalityHint | None = None) -> str:
        self._require_available()
        ptr, aligned = native_mte.mte_mmap(size)
        self._regions[kv_id] = _MTERegion(ptr=ptr, size=aligned)
        loc = f"{self.name}://{kv_id}"
        self._locations[kv_id] = loc
        return loc

    async def store(self, kv_id: str, data: bytes) -> None:
        self._require_available()
        region = self._regions.get(kv_id)
        if region is None:
            await self.allocate(kv_id, len(data))
            region = self._regions[kv_id]
        if len(data) > region.size:
            await self.delete(kv_id)
            await self.allocate(kv_id, len(data))
            region = self._regions[kv_id]
        buf = (ctypes.c_char * region.size).from_address(region.ptr)
        ctypes.memmove(buf, data, len(data))
        region.data_len = len(data)

    async def load(self, kv_id: str) -> bytes:
        self._require_available()
        region = self._regions.get(kv_id)
        if region is None:
            return b""
        buf = (ctypes.c_char * region.data_len).from_address(region.ptr)
        return bytes(buf)

    async def share(self, kv_id: str, consumer_id: str) -> str:
        self._require_available()
        region = self._regions.get(kv_id)
        if region is None:
            self._raise()
        existing = self._sharing.mte_token(kv_id, consumer_id)
        if existing is not None:
            tag = self._sharing.mte_tag(kv_id, consumer_id)
            if tag is not None:
                return f"mte:{tag:02x}:{existing}"
        tag = self._next_tag()
        native_mte.stg_tag(region.ptr, tag)
        perm = self._sharing.grant_mte(kv_id, owner="", consumer=consumer_id, tag=tag)
        return f"mte:{tag:02x}:{perm.token}"

    async def delete(self, kv_id: str) -> None:
        self._require_available()
        region = self._regions.pop(kv_id, None)
        if region is not None:
            native_mte.mte_munmap(region.ptr, region.size)
        self._sharing.revoke_all(kv_id)
        self._locations.pop(kv_id, None)

    async def exists(self, kv_id: str) -> bool:
        if not self.AVAILABLE:
            return False
        return kv_id in self._regions

    async def stats(self) -> ProviderStats:
        if not self.AVAILABLE:
            return ProviderStats(name=self.name, available=False, extra={"reason": "mte_unavailable"})
        return ProviderStats(
            name=self.name,
            available=True,
            extra={
                "regions": len(self._regions),
                "mte_tags": len(self._sharing._mte_tags),
            },
        )

    async def migrate(self, kv_id: str, target) -> str:  # type: ignore[no-untyped-def]
        self._require_available()
        data = await self.load(kv_id)
        await target.store(kv_id, data)
        await target.allocate(kv_id, len(data))
        await self.delete(kv_id)
        return f"{target.name}://{kv_id}"

    async def pin(self, kv_id: str) -> None:
        self._require_available()
        region = self._regions.get(kv_id)
        if region is not None:
            native_mte.mte_promote(region.ptr, region.size)
        await super().pin(kv_id)
