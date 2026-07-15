"""HAOE runtime configuration (NSA_HAOE_* env vars).

Mirrors neuroswarm_arm.runtime.kv.utils.config — HAOE-local, not AppConfig.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..interfaces.types import PoolKind


def _env_bool(name: str, default: str = "1") -> bool:
    return os.getenv(name, default) not in {"0", "false", "False", "no", "NO"}


def _pool_sizes_from_env() -> dict[str, int]:
    defaults = {
        PoolKind.INFERENCE.value: 2,
        PoolKind.MEMORY.value: 2,
        PoolKind.EMBEDDING.value: 2,
        PoolKind.TOOL.value: 2,
        PoolKind.PLANNER.value: 1,
        PoolKind.BACKGROUND.value: 2,
        PoolKind.TELEMETRY.value: 1,
        PoolKind.MAINTENANCE.value: 1,
    }
    out: dict[str, int] = {}
    for kind, default in defaults.items():
        key = f"NSA_HAOE_POOL_{kind.upper()}"
        out[kind] = int(os.getenv(key, str(default)))
    return out


@dataclass(slots=True)
class HAOERuntimeConfig:
    root: Path = field(
        default_factory=lambda: Path(os.getenv("NSA_HAOE_ROOT", "work/haoe"))
    )
    checkpoint_dir: Path | None = None
    affinity_enabled: bool = field(
        default_factory=lambda: _env_bool("NSA_HAOE_AFFINITY", "1")
    )
    work_stealing: bool = field(
        default_factory=lambda: _env_bool("NSA_HAOE_WORK_STEALING", "1")
    )
    priority_aging: bool = field(
        default_factory=lambda: _env_bool("NSA_HAOE_PRIORITY_AGING", "1")
    )
    aging_interval_s: float = float(os.getenv("NSA_HAOE_AGING_INTERVAL", "0.5"))
    aging_step: float = float(os.getenv("NSA_HAOE_AGING_STEP", "0.1"))
    steal_attempts: int = int(os.getenv("NSA_HAOE_STEAL_ATTEMPTS", "3"))
    default_timeout_s: float = float(os.getenv("NSA_HAOE_DEFAULT_TIMEOUT", "120"))
    max_retries: int = int(os.getenv("NSA_HAOE_MAX_RETRIES", "3"))
    otel_endpoint: str = os.getenv("NSA_HAOE_OTEL_ENDPOINT", "")
    otel_enabled: bool = field(
        default_factory=lambda: _env_bool("NSA_HAOE_OTEL", "0")
    )
    performix_snapshot_path: Path | None = None
    pool_sizes: dict[str, int] = field(default_factory=_pool_sizes_from_env)
    fast_core_fraction: float = float(os.getenv("NSA_HAOE_FAST_CORE_FRACTION", "0.5"))
    inline_fallback: bool = field(
        default_factory=lambda: _env_bool("NSA_HAOE_INLINE_FALLBACK", "1")
    )
    process_pool_workers: int = int(os.getenv("NSA_HAOE_PROCESS_WORKERS", "0"))
    thread_pool_workers: int = int(os.getenv("NSA_HAOE_THREAD_WORKERS", "8"))

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        if self.checkpoint_dir is None:
            self.checkpoint_dir = self.root / "checkpoints"
        else:
            self.checkpoint_dir = Path(self.checkpoint_dir)
        if self.performix_snapshot_path is None:
            self.performix_snapshot_path = self.root / "performix_snapshot.json"
        else:
            self.performix_snapshot_path = Path(self.performix_snapshot_path)
        self.root.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def pool_size(self, pool: PoolKind | str) -> int:
        key = pool.value if isinstance(pool, PoolKind) else str(pool)
        return max(1, int(self.pool_sizes.get(key, 1)))


def load_haoe_config(root: Path | None = None) -> HAOERuntimeConfig:
    cfg = HAOERuntimeConfig()
    if root is not None:
        cfg.root = Path(root)
        cfg.checkpoint_dir = cfg.root / "checkpoints"
        cfg.performix_snapshot_path = cfg.root / "performix_snapshot.json"
        cfg.__post_init__()
    return cfg
