"""AWPP runtime configuration (NSA_AWPP_* env vars)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: str = "1") -> bool:
    return os.getenv(name, default) not in {"0", "false", "False", "no", "NO"}


@dataclass(slots=True)
class AWPPRuntimeConfig:
    root: Path = field(
        default_factory=lambda: Path(os.getenv("NSA_AWPP_ROOT", "work/awpp"))
    )
    history_dir: Path | None = None
    replay_dir: Path | None = None
    policy_dir: Path | None = None
    horizon_s: float = float(os.getenv("NSA_AWPP_HORIZON_S", "5"))
    history_window: int = int(os.getenv("NSA_AWPP_HISTORY_WINDOW", "20"))
    feature_dim: int = int(os.getenv("NSA_AWPP_FEATURE_DIM", "64"))
    embedding_dim: int = int(os.getenv("NSA_AWPP_EMBED_DIM", "32"))
    confidence_threshold: float = float(os.getenv("NSA_AWPP_CONFIDENCE_THRESHOLD", "0.35"))
    max_concurrent_warms: int = int(os.getenv("NSA_AWPP_MAX_CONCURRENT", "4"))
    max_memory_bytes: int = int(os.getenv("NSA_AWPP_MAX_MEMORY_BYTES", str(2 * 1024**3)))
    max_cpu_fraction: float = float(os.getenv("NSA_AWPP_MAX_CPU_FRACTION", "0.01"))
    warm_timeout_s: float = float(os.getenv("NSA_AWPP_WARM_TIMEOUT_S", "5"))
    rate_limit_per_s: float = float(os.getenv("NSA_AWPP_RATE_LIMIT", "20"))
    policy_path: str = os.getenv("NSA_AWPP_POLICY_PATH", "")
    active_policy: str = os.getenv("NSA_AWPP_ACTIVE_POLICY", "markov")
    shadow_policy: str = os.getenv("NSA_AWPP_SHADOW_POLICY", "")
    shadow_mode: bool = field(default_factory=lambda: _env_bool("NSA_AWPP_SHADOW", "0"))
    ab_split: float = float(os.getenv("NSA_AWPP_AB_SPLIT", "0.0"))
    always_warm_tier1: bool = field(
        default_factory=lambda: _env_bool("NSA_AWPP_ALWAYS_WARM_TIER1", "1")
    )
    affinity_enabled: bool = field(
        default_factory=lambda: _env_bool("NSA_AWPP_AFFINITY", "1")
    )
    otel_enabled: bool = field(default_factory=lambda: _env_bool("NSA_AWPP_OTEL", "0"))
    otel_endpoint: str = os.getenv("NSA_AWPP_OTEL_ENDPOINT", "")
    latency_slo_ms: float = float(os.getenv("NSA_AWPP_LATENCY_SLO_MS", "150"))
    cold_start_baseline_ms: float = float(
        os.getenv("NSA_AWPP_COLD_START_BASELINE_MS", "600")
    )
    predictor_worker_poll_s: float = float(
        os.getenv("NSA_AWPP_WORKER_POLL_S", "0.25")
    )
    warmup_urls: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        if self.history_dir is None:
            self.history_dir = self.root / "history"
        else:
            self.history_dir = Path(self.history_dir)
        if self.replay_dir is None:
            self.replay_dir = self.root / "replay"
        else:
            self.replay_dir = Path(self.replay_dir)
        if self.policy_dir is None:
            self.policy_dir = self.root / "policies"
        else:
            self.policy_dir = Path(self.policy_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        self.policy_dir.mkdir(parents=True, exist_ok=True)
        if not self.warmup_urls:
            self.warmup_urls = {
                "tier1": os.getenv("NSA_TIER1_URL", "http://127.0.0.1:8081"),
                "tier2": os.getenv("NSA_TIER2_URL", "http://127.0.0.1:8082"),
                "tier3": os.getenv("NSA_TIER3_URL", "http://127.0.0.1:8083"),
            }


def load_awpp_config(root: Path | None = None) -> AWPPRuntimeConfig:
    cfg = AWPPRuntimeConfig()
    if root is not None:
        cfg.root = Path(root)
        cfg.__post_init__()
    return cfg
