"""MAKS — Multi-Agent KV Memory Operating System (NEXUS Layer 5).

Global KV lifecycle: allocation, page pool, sharing, refcount, migration,
dedup, eviction, capability discovery, telemetry.
Provider HAL: RAM / mmap / Redis / NVMe today; MTE / CXL stubs for future ARM.
Cognitive Mem0/OKF remain orthogonal — never merge into inference KV pages.
"""

from __future__ import annotations

from .capability import CapabilityFlags, CapabilityRegistry, IBackendKVCapability
from .config import MAKSConfig, load_maks_config
from .factory import build_maks
from .manager import KVManager
from .models import (
    KVHandle,
    KVIdentity,
    KVMetadata,
    KVRegistryRecord,
    KVState,
    PrefetchRequest,
    ProviderName,
)
from .pool import GlobalPagePool, PageMeta

__all__ = [
    "MAKSConfig",
    "load_maks_config",
    "build_maks",
    "KVManager",
    "KVHandle",
    "KVIdentity",
    "KVMetadata",
    "KVRegistryRecord",
    "KVState",
    "PrefetchRequest",
    "ProviderName",
    "GlobalPagePool",
    "PageMeta",
    "CapabilityRegistry",
    "CapabilityFlags",
    "IBackendKVCapability",
]
