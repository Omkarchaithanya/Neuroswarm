"""Shared enums and value types for the KV Memory Runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any


class StorageTier(IntEnum):
    """Storage tiers ordered from hottest (lowest latency) to coldest."""

    L1_RAM = 1
    L2_COMPRESSED_RAM = 2
    L3_MEMORY_MAPPED = 3
    L4_LMDB = 4
    L5_REDIS = 5
    L3_NVME = 6  # warm disk peer of mmap
    FUTURE_CXL = 90
    FUTURE_MTE = 91


class BlockStatus(str, Enum):
    FREE = "free"
    ALLOCATED = "allocated"
    SHARED = "shared"
    MIGRATING = "migrating"
    CHECKPOINTED = "checkpointed"
    EVICTED = "evicted"
    CORRUPT = "corrupt"


class BlockTemperature(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


@dataclass(slots=True)
class TensorMeta:
    """Opaque tensor metadata for a KV block payload."""

    dtype: str = "uint8"
    shape: tuple[int, ...] = ()
    nbytes: int = 0
    encoding: str = "raw"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dtype": self.dtype,
            "shape": list(self.shape),
            "nbytes": self.nbytes,
            "encoding": self.encoding,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TensorMeta:
        shape = data.get("shape", [])
        return cls(
            dtype=str(data.get("dtype", "uint8")),
            shape=tuple(int(x) for x in shape),
            nbytes=int(data.get("nbytes", 0)),
            encoding=str(data.get("encoding", "raw")),
        )


@dataclass(slots=True)
class PhysicalBlockRecord:
    """Global physical block registry entry."""

    physical_id: str
    content_hash: str
    prefix_hash: str
    tier: StorageTier
    provider_key: str
    refcount: int = 1
    numa_node: int = 0
    layer: int = 0
    head: int = 0
    token_start: int = 0
    token_end: int = 0
    status: BlockStatus = BlockStatus.ALLOCATED
    temperature: BlockTemperature = BlockTemperature.HOT
    last_access: float = 0.0
    access_count: int = 0
    priority: int = 0
    nbytes: int = 0
    compressed: bool = False
    compression: str = "none"
    meta: TensorMeta = field(default_factory=TensorMeta)

    def to_dict(self) -> dict[str, Any]:
        return {
            "physical_id": self.physical_id,
            "content_hash": self.content_hash,
            "prefix_hash": self.prefix_hash,
            "tier": int(self.tier),
            "provider_key": self.provider_key,
            "refcount": self.refcount,
            "numa_node": self.numa_node,
            "layer": self.layer,
            "head": self.head,
            "token_start": self.token_start,
            "token_end": self.token_end,
            "status": self.status.value,
            "temperature": self.temperature.value,
            "last_access": self.last_access,
            "access_count": self.access_count,
            "priority": self.priority,
            "nbytes": self.nbytes,
            "compressed": self.compressed,
            "compression": self.compression,
            "meta": self.meta.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PhysicalBlockRecord:
        return cls(
            physical_id=str(data["physical_id"]),
            content_hash=str(data["content_hash"]),
            prefix_hash=str(data.get("prefix_hash", "")),
            tier=StorageTier(int(data["tier"])),
            provider_key=str(data["provider_key"]),
            refcount=int(data.get("refcount", 1)),
            numa_node=int(data.get("numa_node", 0)),
            layer=int(data.get("layer", 0)),
            head=int(data.get("head", 0)),
            token_start=int(data.get("token_start", 0)),
            token_end=int(data.get("token_end", 0)),
            status=BlockStatus(str(data.get("status", BlockStatus.ALLOCATED.value))),
            temperature=BlockTemperature(str(data.get("temperature", BlockTemperature.HOT.value))),
            last_access=float(data.get("last_access", 0.0)),
            access_count=int(data.get("access_count", 0)),
            priority=int(data.get("priority", 0)),
            nbytes=int(data.get("nbytes", 0)),
            compressed=bool(data.get("compressed", False)),
            compression=str(data.get("compression", "none")),
            meta=TensorMeta.from_dict(data.get("meta", {})),
        )


@dataclass(slots=True)
class PressureSnapshot:
    """Signals consumed by Governor / Cost Router / HAOE."""

    pressure: float
    hit_rate: float
    miss_rate: float
    ram_usage_bytes: int
    storage_usage_bytes: int
    blocks_total: int
    blocks_shared: int
    migration_latency_ms: float
    dominant_tier: StorageTier
    fragmentation: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "pressure": self.pressure,
            "hit_rate": self.hit_rate,
            "miss_rate": self.miss_rate,
            "ram_usage_bytes": self.ram_usage_bytes,
            "storage_usage_bytes": self.storage_usage_bytes,
            "blocks_total": self.blocks_total,
            "blocks_shared": self.blocks_shared,
            "migration_latency_ms": self.migration_latency_ms,
            "dominant_tier": int(self.dominant_tier),
            "fragmentation": self.fragmentation,
        }
