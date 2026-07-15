"""Provider registry and default factory."""

from __future__ import annotations

from pathlib import Path
from threading import RLock

from ..compression import IKVCompression, build_compression
from ..interfaces.provider import IKVProvider
from ..interfaces.types import StorageTier
from ..utils.config import KVRuntimeConfig
from .compressed_ram import CompressedRAMProvider
from .cxl import CXLProvider
from .lmdb_provider import LMDBProvider
from .mmap_provider import MemoryMappedProvider
from .mte import MTEProvider
from .nvme import NVMeProvider
from .ram import RAMProvider
from .redis_provider import RedisProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, IKVProvider] = {}
        self._by_tier: dict[StorageTier, IKVProvider] = {}
        self._lock = RLock()
        self._stubs: dict[str, IKVProvider] = {}

    def register(self, provider: IKVProvider, *, stub: bool = False) -> None:
        with self._lock:
            if stub:
                self._stubs[provider.name] = provider
                return
            self._by_name[provider.name] = provider
            self._by_tier[provider.tier] = provider

    def get(self, name: str) -> IKVProvider:
        with self._lock:
            if name in self._by_name:
                return self._by_name[name]
            if name in self._stubs:
                return self._stubs[name]
            raise KeyError(name)

    def for_tier(self, tier: StorageTier) -> IKVProvider:
        with self._lock:
            if tier not in self._by_tier:
                raise KeyError(f"no provider for tier {tier}")
            return self._by_tier[tier]

    def has_tier(self, tier: StorageTier) -> bool:
        with self._lock:
            return tier in self._by_tier

    def get_tier(self, tier: StorageTier) -> IKVProvider | None:
        with self._lock:
            return self._by_tier.get(tier)

    def list_providers(self) -> list[dict[str, object]]:
        with self._lock:
            out = [
                {
                    "name": p.name,
                    "tier": int(p.tier),
                    "usage_bytes": p.usage_bytes(),
                    "stub": False,
                }
                for p in self._by_name.values()
            ]
            out.extend(
                {
                    "name": p.name,
                    "tier": int(p.tier),
                    "usage_bytes": 0,
                    "stub": True,
                }
                for p in self._stubs.values()
            )
            return out

    def ram_usage(self) -> int:
        with self._lock:
            total = 0
            for tier in (StorageTier.L1_RAM, StorageTier.L2_COMPRESSED_RAM):
                p = self._by_tier.get(tier)
                if p is not None:
                    total += p.usage_bytes()
            return total

    def storage_usage(self) -> int:
        with self._lock:
            return sum(p.usage_bytes() for p in self._by_name.values())


def build_default_providers(
    cfg: KVRuntimeConfig,
    compression: IKVCompression | None = None,
) -> ProviderRegistry:
    codec = compression or build_compression(cfg.compression)
    registry = ProviderRegistry()
    registry.register(RAMProvider())
    registry.register(CompressedRAMProvider(codec))
    registry.register(MemoryMappedProvider(cfg.root / "mmap"))
    registry.register(NVMeProvider(cfg.root / "nvme"))
    try:
        registry.register(LMDBProvider(cfg.root / "lmdb", map_size=cfg.lmdb_map_size))
    except Exception:
        # LMDB optional until package installed; mmap/nvme cover durable tiers.
        pass
    try:
        registry.register(RedisProvider(cfg.redis_url))
    except Exception:
        pass
    registry.register(CXLProvider(), stub=True)
    registry.register(MTEProvider(), stub=True)
    return registry
