"""KV configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class KVRuntimeConfig:
    root: Path = field(default_factory=lambda: Path(os.getenv("NSA_KV_STORE", "work/kv")))
    block_size_tokens: int = int(os.getenv("NSA_KV_BLOCK_SIZE", "256"))
    pressure_threshold: float = float(os.getenv("NSA_KV_PRESSURE_THRESHOLD", "0.70"))
    ram_budget_bytes: int = int(os.getenv("NSA_KV_RAM_BUDGET", str(512 * 1024 * 1024)))
    compression: str = os.getenv("NSA_KV_COMPRESSION", "zstd")
    default_tier: str = os.getenv("NSA_KV_DEFAULT_TIER", "L1_RAM")
    redis_url: str = os.getenv("NSA_KV_REDIS_URL", "redis://localhost:6379/0")
    lmdb_map_size: int = int(os.getenv("NSA_KV_LMDB_MAP_SIZE", str(1 << 30)))
    enable_background_migration: bool = os.getenv("NSA_KV_BG_MIGRATION", "1") not in {
        "0",
        "false",
        "False",
    }
    migration_interval_s: float = float(os.getenv("NSA_KV_MIGRATION_INTERVAL", "1.0"))
    sharing_backend: str = os.getenv("NSA_KV_SHARING_BACKEND", "mmap")
    numa_preferred_node: int = int(os.getenv("NSA_KV_NUMA_NODE", "-1"))
    checkpoint_dir: Path | None = None

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        if self.checkpoint_dir is None:
            self.checkpoint_dir = self.root / "checkpoints"
        else:
            self.checkpoint_dir = Path(self.checkpoint_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        (self.root / "mmap").mkdir(parents=True, exist_ok=True)
        (self.root / "nvme").mkdir(parents=True, exist_ok=True)
        (self.root / "lmdb").mkdir(parents=True, exist_ok=True)
        (self.root / "share").mkdir(parents=True, exist_ok=True)
        (self.root / "journal").mkdir(parents=True, exist_ok=True)


def load_kv_config(
    root: Path | None = None,
    *,
    block_size_tokens: int | None = None,
    ram_budget_bytes: int | None = None,
) -> KVRuntimeConfig:
    cfg = KVRuntimeConfig()
    if root is not None:
        cfg.root = Path(root)
        cfg.checkpoint_dir = cfg.root / "checkpoints"
        cfg.__post_init__()
    if block_size_tokens is not None:
        cfg.block_size_tokens = block_size_tokens
    if ram_budget_bytes is not None:
        cfg.ram_budget_bytes = ram_budget_bytes
    return cfg
