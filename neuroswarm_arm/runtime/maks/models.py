"""MAKS domain models (Pydantic)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class KVState(str, Enum):
    ALLOCATED = "allocated"
    WARMED = "warmed"
    SHARED = "shared"
    PINNED = "pinned"
    MIGRATED = "migrated"
    RELEASED = "released"
    EVICTED = "evicted"
    DESTROYED = "destroyed"


class KVTier(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class ProviderName(str, Enum):
    RAM = "ram"
    MMAP = "mmap"
    REDIS = "redis"
    NVME = "nvme"
    FUTURE_MTE = "future_mte"
    FUTURE_CXL = "future_cxl"


class HashAlgo(str, Enum):
    SHA256 = "sha256"
    BLAKE3 = "blake3"
    ROLLING = "rolling"  # future


class EvictionPolicyName(str, Enum):
    SCORED = "scored"  # Memory OS default — multi-signal, not plain LRU
    LRU = "lru"
    LFU = "lfu"
    CLOCK = "clock"
    ARC = "arc"
    TEMPERATURE = "temperature"
    COST_AWARE = "cost_aware"
    S3FIFO = "s3fifo"


class KVIdentity(BaseModel):
    """AQR-safe identity — different quant/RoPE/tokenizer cannot share blindly."""

    model_id: str = ""
    quantization: str = ""
    tokenizer_version: str = ""
    rope_config: str = ""
    context_window: int = 0

    def fingerprint(self) -> str:
        return "|".join(
            [
                self.model_id,
                self.quantization,
                self.tokenizer_version,
                self.rope_config,
                str(self.context_window),
            ]
        )

    def compatible_with(self, other: KVIdentity) -> bool:
        return self.fingerprint() == other.fingerprint()


class KVHandle(BaseModel):
    kv_id: str
    provider: ProviderName = ProviderName.RAM
    location: str = ""
    share_token: str = ""


class MigrationEvent(BaseModel):
    ts: float
    from_provider: str
    to_provider: str
    reason: str = ""


class KVMetadata(BaseModel):
    token_count: int = 0
    layer_count: int = 0
    head_count: int = 0
    kv_size: int = 0
    backend: str = ""
    compression: str = "none"
    content_hash: str = ""
    prefix_hash: str = ""
    prompt_hash: str = ""
    identity_hash: str = ""
    creation_latency_ms: float = 0.0
    reuse_count: int = 0
    migration_count: int = 0
    hit_count: int = 0
    miss_count: int = 0
    prefill_source: str = ""
    producer: str = ""
    consumers: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class KVRegistryRecord(BaseModel):
    kv_id: str
    owner_agent: str = ""
    readers: list[str] = Field(default_factory=list)
    identity: KVIdentity = Field(default_factory=KVIdentity)
    prompt_hash: str = ""
    conversation_id: str = ""
    session_id: str = ""
    created_at: float = 0.0
    last_access: float = 0.0
    ttl_s: float = 0.0
    refcount: int = 0
    provider: ProviderName = ProviderName.RAM
    location: str = ""
    tier: KVTier = KVTier.HOT
    pinned: bool = False
    migration_history: list[MigrationEvent] = Field(default_factory=list)
    dedup_key: str = ""
    version: int = 1
    state: KVState = KVState.ALLOCATED
    metadata: KVMetadata = Field(default_factory=KVMetadata)
    access_count: int = 0
    priority: int = 0
    cost_score: float = 0.0
    numa_node: int = 0
    capability_token: str = ""


class SharePermission(BaseModel):
    kv_id: str
    owner: str
    consumer: str
    can_read: bool = True
    can_write: bool = False
    token: str = ""


class PrefetchRequest(BaseModel):
    kv_id: str = ""
    prompt_hash: str = ""
    identity: KVIdentity = Field(default_factory=KVIdentity)
    session_id: str = ""
    agent_id: str = ""
    priority: int = 0
    pin: bool = False


class ProviderStats(BaseModel):
    name: str
    available: bool = True
    usage_bytes: int = 0
    entry_count: int = 0
    latency_ms_ema: float = 0.0
    extra: dict[str, Any] = Field(default_factory=dict)


class LocalityHint(BaseModel):
    """HAOE locality / affinity hint for allocation."""

    numa_node: int = 0
    affinity_cores: list[int] = Field(default_factory=list)
    agent_id: str = ""
    priority: int = 0


class ARMORAPolicySnapshot(BaseModel):
    """Policy surface consumed from ARMORA (or config stub)."""

    max_memory_bytes: int = 0
    max_cost: float = 0.0
    max_cache_entries: int = 0
    eviction_policy: EvictionPolicyName = EvictionPolicyName.SCORED
    ttl_s: float = 0.0
    budget: float = 0.0
    priority: int = 0
