"""MAKS storage backends."""

from __future__ import annotations

from pathlib import Path

from ..compression import build_compression
from ..config import MAKSConfig
from ..interfaces import IKVProvider
from ..models import ProviderName
from ..native import feature_matrix
from .future_cxl_backend import FutureCXLBackend
from .future_mte_backend import FutureMTEBackend
from .mmap_backend import MMapBackend, build_mmap_backend
from .mte_backend import MTEBackend
from .nvme_backend import NVMeBackend, build_nvme_backend
from .ram_backend import RAMBackend, build_ram_backend
from .redis_backend import RedisBackend, build_redis_backend


def build_default_backends(cfg: MAKSConfig) -> dict[str, IKVProvider]:
    codec = build_compression(cfg.compression)
    mte_backend: IKVProvider = MTEBackend() if feature_matrix().get("mte") else FutureMTEBackend()
    backends: dict[str, IKVProvider] = {
        ProviderName.RAM.value: build_ram_backend(root=cfg.root, use_shared_memory=True),
        ProviderName.MMAP.value: build_mmap_backend(cfg.root),
        ProviderName.REDIS.value: build_redis_backend(cfg.redis_url),
        ProviderName.NVME.value: build_nvme_backend(cfg.root, compression=codec),
        ProviderName.FUTURE_MTE.value: mte_backend,
        ProviderName.FUTURE_CXL.value: FutureCXLBackend(),
    }
    return backends


__all__ = [
    "RAMBackend",
    "MMapBackend",
    "RedisBackend",
    "NVMeBackend",
    "FutureMTEBackend",
    "FutureCXLBackend",
    "MTEBackend",
    "build_default_backends",
    "build_ram_backend",
    "build_mmap_backend",
    "build_redis_backend",
    "build_nvme_backend",
]
