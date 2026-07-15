"""Copy-on-write for shared physical blocks."""

from __future__ import annotations

from dataclasses import dataclass

from ..interfaces.types import BlockStatus, PhysicalBlockRecord
from ..utils.hashing import content_hash, stable_id
from .tables import PhysicalBlockTable


@dataclass
class CopyOnWriteEngine:
    """Clone shared physical blocks before mutation."""

    physical: PhysicalBlockTable

    def needs_cow(self, physical_id: str) -> bool:
        rec = self.physical.get(physical_id)
        return rec is not None and rec.refcount > 1

    def clone(
        self,
        physical_id: str,
        payload: bytes,
        *,
        provider_key: str,
    ) -> PhysicalBlockRecord:
        src = self.physical.get(physical_id)
        if src is None:
            raise KeyError(f"unknown physical block: {physical_id}")
        new_hash = content_hash(payload)
        existing = self.physical.get_by_hash(new_hash)
        if existing is not None:
            self.physical.acquire(existing.physical_id)
            return existing
        clone = PhysicalBlockRecord(
            physical_id=stable_id("phys"),
            content_hash=new_hash,
            prefix_hash=src.prefix_hash,
            tier=src.tier,
            provider_key=provider_key,
            refcount=1,
            numa_node=src.numa_node,
            layer=src.layer,
            head=src.head,
            token_start=src.token_start,
            token_end=src.token_end,
            status=BlockStatus.ALLOCATED,
            temperature=src.temperature,
            last_access=src.last_access,
            access_count=0,
            priority=src.priority,
            nbytes=len(payload),
            compressed=src.compressed,
            compression=src.compression,
            meta=src.meta,
        )
        return self.physical.register(clone)
