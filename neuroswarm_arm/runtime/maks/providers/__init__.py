"""Provider HAL package — re-exports storage backends (plan: providers/)."""

from __future__ import annotations

from ..backends import (
    FutureCXLBackend,
    FutureMTEBackend,
    MMapBackend,
    NVMeBackend,
    RAMBackend,
    RedisBackend,
    build_default_backends,
    build_mmap_backend,
    build_nvme_backend,
    build_ram_backend,
    build_redis_backend,
)

# Plan naming
build_default_providers = build_default_backends

__all__ = [
    "RAMBackend",
    "MMapBackend",
    "RedisBackend",
    "NVMeBackend",
    "FutureMTEBackend",
    "FutureCXLBackend",
    "build_default_backends",
    "build_default_providers",
    "build_ram_backend",
    "build_mmap_backend",
    "build_redis_backend",
    "build_nvme_backend",
]
