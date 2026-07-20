"""NSA_AROP_* configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: str = "1") -> bool:
    return os.getenv(name, default) not in {"0", "false", "False", "no", "NO"}


@dataclass(slots=True)
class AROPConfig:
    enabled: bool = True
    work_dir: Path = field(default_factory=lambda: Path("work/arop"))
    okf_root: Path = field(default_factory=lambda: Path("okf"))
    performix_enabled: bool = False
    performix_binary: str = "apx"
    performix_recipe: str = "code-hotspots"
    haoe_snapshot: Path = field(default_factory=lambda: Path("work/haoe/performix_snapshot.json"))
    interval_seconds: int = 3600
    canary_percent: float = 10.0
    reflection_strategy: str = "hybrid"  # rule|gepa|hybrid|offline_llm
    primary_metric: str = "reward_scalar"
    min_improvement: float = 0.01
    significance_alpha: float = 0.1
    auto_promote: bool = False
    safety_max_latency_ms: float = 5000.0
    safety_min_accept_rate: float = 0.5
    safety_max_cost_usd: float = 0.05
    safety_max_kv_pressure: float = 0.9
    default_accept_threshold: float = 0.7
    default_draft_len: int = 8
    default_escalate_threshold: float = 0.4
    default_reasoning_cap: int = 512
    default_router_top_k: int = 3
    replay_max_episodes: int = 50
    bandit_enabled: bool = True
    mcp_performix_url: str = ""
    gepa_lm: str = "mock"  # mock | http://tier2:8080/v1


def load_arop_config(*, work_dir: Path | None = None, okf_root: Path | None = None) -> AROPConfig:
    cfg = AROPConfig(
        enabled=_bool("NSA_AROP_ENABLED", "1"),
        work_dir=Path(os.getenv("NSA_AROP_WORK", str(work_dir or "work/arop"))),
        okf_root=Path(os.getenv("NSA_OKF_ROOT", str(okf_root or "okf"))),
        performix_enabled=_bool("NSA_AROP_PERFORMIX", "0"),
        performix_binary=os.getenv("NSA_AROP_PERFORMIX_BIN", "apx"),
        performix_recipe=os.getenv("NSA_AROP_PERFORMIX_RECIPE", "code-hotspots"),
        haoe_snapshot=Path(os.getenv("NSA_AROP_HAOE_SNAPSHOT", "work/haoe/performix_snapshot.json")),
        interval_seconds=int(os.getenv("NSA_AROP_INTERVAL", "3600")),
        canary_percent=float(os.getenv("NSA_AROP_CANARY_PCT", "10")),
        reflection_strategy=os.getenv("NSA_AROP_REFLECTION", "hybrid"),
        primary_metric=os.getenv("NSA_AROP_PRIMARY_METRIC", "reward_scalar"),
        min_improvement=float(os.getenv("NSA_AROP_MIN_IMPROVEMENT", "0.01")),
        significance_alpha=float(os.getenv("NSA_AROP_ALPHA", "0.1")),
        auto_promote=_bool("NSA_AROP_AUTO_PROMOTE", "0"),
        safety_max_latency_ms=float(os.getenv("NSA_AROP_MAX_LATENCY_MS", "5000")),
        safety_min_accept_rate=float(os.getenv("NSA_AROP_MIN_ACCEPT", "0.5")),
        safety_max_cost_usd=float(os.getenv("NSA_AROP_MAX_COST", "0.05")),
        safety_max_kv_pressure=float(os.getenv("NSA_AROP_MAX_KV_PRESSURE", "0.9")),
        default_accept_threshold=float(os.getenv("NSA_CASCADE_CONFIDENCE_THRESHOLD", "0.85")),
        default_draft_len=int(os.getenv("NSA_AROP_DRAFT_LEN", "8")),
        default_escalate_threshold=float(os.getenv("NSA_AROP_ESCALATE", "0.4")),
        default_reasoning_cap=int(os.getenv("NSA_AROP_REASONING_CAP", "512")),
        default_router_top_k=int(os.getenv("NSA_ROUTER_TOP_K", "3")),
        replay_max_episodes=int(os.getenv("NSA_AROP_REPLAY_EPISODES", "50")),
        bandit_enabled=_bool("NSA_AROP_BANDIT", "1"),
        mcp_performix_url=os.getenv("NSA_AROP_PERFORMIX_MCP", ""),
        gepa_lm=os.getenv("NSA_AROP_GEPA_LM", "mock"),
    )
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    return cfg
