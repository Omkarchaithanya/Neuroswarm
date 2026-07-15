"""ACR configuration — NSA_ACR_* env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw not in {"0", "false", "False", "no", "NO"}


@dataclass
class ACRConfig:
    enabled: bool = True
    token_budget: int = 2000
    latency_budget_ms: float = 200.0
    cost_budget: float = 0.01
    cache_enabled: bool = True
    cache_ttl_s: float = 60.0
    cache_max_entries: int = 256
    progressive: bool = True
    parallel_retrieve: bool = True
    work_dir: Path = field(default_factory=lambda: Path("work/acr"))
    min_importance: float = 0.2
    # Prompt-cache friendly stable section order
    stable_prefix: bool = True


def load_acr_config(work_dir: Path | str | None = None) -> ACRConfig:
    wd = Path(work_dir or os.getenv("NSA_ACR_WORK", "work/acr"))
    return ACRConfig(
        enabled=_env_bool("NSA_ACR_ENABLED", True),
        token_budget=int(os.getenv("NSA_ACR_TOKEN_BUDGET", "2000")),
        latency_budget_ms=float(os.getenv("NSA_ACR_LATENCY_BUDGET_MS", "200")),
        cost_budget=float(os.getenv("NSA_ACR_COST_BUDGET", "0.01")),
        cache_enabled=_env_bool("NSA_ACR_CACHE", True),
        cache_ttl_s=float(os.getenv("NSA_ACR_CACHE_TTL_S", "60")),
        cache_max_entries=int(os.getenv("NSA_ACR_CACHE_MAX", "256")),
        progressive=_env_bool("NSA_ACR_PROGRESSIVE", True),
        parallel_retrieve=_env_bool("NSA_ACR_PARALLEL_RETRIEVE", True),
        work_dir=wd,
        min_importance=float(os.getenv("NSA_ACR_MIN_IMPORTANCE", "0.2")),
        stable_prefix=_env_bool("NSA_ACR_STABLE_PREFIX", True),
    )
