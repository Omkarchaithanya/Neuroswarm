"""MAKS configuration (NSA_MAKS_* + compose with NSA_KV_*)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .models import EvictionPolicyName, HashAlgo, ProviderName


def _env_bool(name: str, default: str = "1") -> bool:
    return os.getenv(name, default) not in {"0", "false", "False", "no", "NO"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return float(raw)


@dataclass(slots=True)
class MAKSConfig:
    root: Path = field(default_factory=lambda: Path(os.getenv("NSA_MAKS_STORE", os.getenv("NSA_KV_STORE", "work/kv"))))
    default_provider: ProviderName = ProviderName.RAM
    registry_backend: str = field(default_factory=lambda: os.getenv("NSA_MAKS_REGISTRY", "sqlite"))
    redis_url: str = field(
        default_factory=lambda: os.getenv("NSA_MAKS_REDIS_URL", os.getenv("NSA_KV_REDIS_URL", "redis://localhost:6379/0"))
    )
    hash_algo: HashAlgo = HashAlgo.SHA256
    eviction_policy: EvictionPolicyName = EvictionPolicyName.SCORED
    default_backend_id: str = field(default_factory=lambda: os.getenv("NSA_MAKS_BACKEND", "opaque"))
    page_bytes: int = field(default_factory=lambda: _env_int("NSA_MAKS_PAGE_BYTES", 64 * 1024))
    compression: str = field(default_factory=lambda: os.getenv("NSA_MAKS_COMPRESSION", os.getenv("NSA_KV_COMPRESSION", "zstd")))
    ram_budget_bytes: int = field(
        default_factory=lambda: _env_int("NSA_MAKS_RAM_BUDGET", _env_int("NSA_KV_RAM_BUDGET", 512 * 1024 * 1024))
    )
    max_cache_entries: int = field(default_factory=lambda: _env_int("NSA_MAKS_MAX_ENTRIES", 100_000))
    default_ttl_s: float = field(default_factory=lambda: _env_float("NSA_MAKS_TTL", 0.0))
    pressure_threshold: float = field(
        default_factory=lambda: _env_float("NSA_MAKS_PRESSURE", _env_float("NSA_KV_PRESSURE_THRESHOLD", 0.70))
    )
    enable_scheduler: bool = field(default_factory=lambda: _env_bool("NSA_MAKS_SCHEDULER", "1"))
    scheduler_interval_s: float = field(default_factory=lambda: _env_float("NSA_MAKS_SCHEDULER_INTERVAL", 1.0))
    enable_dedup: bool = field(
        default_factory=lambda: _env_bool("NSA_MAKS_ENABLE_DEDUP", os.getenv("NSA_MAKS_DEDUP", "1"))
    )
    enable_prefix_reuse: bool = field(default_factory=lambda: _env_bool("NSA_MAKS_PREFIX", "1"))
    orphan_grace_s: float = field(default_factory=lambda: _env_float("NSA_MAKS_ORPHAN_GRACE", 300.0))
    max_memory_bytes: int = field(default_factory=lambda: _env_int("NSA_MAKS_MAX_MEMORY", 0))
    max_cost: float = field(default_factory=lambda: _env_float("NSA_MAKS_MAX_COST", 0.0))

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        (self.root / "maks").mkdir(parents=True, exist_ok=True)
        (self.root / "maks" / "registry").mkdir(parents=True, exist_ok=True)
        if isinstance(self.default_provider, str):
            self.default_provider = ProviderName(self.default_provider.lower())
        if isinstance(self.hash_algo, str):
            self.hash_algo = HashAlgo(self.hash_algo.lower())
        if isinstance(self.eviction_policy, str):
            self.eviction_policy = EvictionPolicyName(self.eviction_policy.lower())


def load_maks_config(root: Path | None = None) -> MAKSConfig:
    cfg = MAKSConfig()
    if root is not None:
        cfg.root = Path(root)
        cfg.__post_init__()
    # Allow override of default provider via env
    prov = os.getenv("NSA_MAKS_DEFAULT_PROVIDER")
    if prov:
        cfg.default_provider = ProviderName(prov.lower())
    algo = os.getenv("NSA_MAKS_HASH")
    if algo:
        cfg.hash_algo = HashAlgo(algo.lower())
    policy = os.getenv("NSA_MAKS_EVICTION")
    if policy:
        cfg.eviction_policy = EvictionPolicyName(policy.lower())
    return cfg
