"""RTG runtime configuration (NSA_RTG_* env vars + YAML)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml


def _env_bool(name: str, default: str = "1") -> bool:
    return os.getenv(name, default) not in {"0", "false", "False", "no", "NO"}


def _pkg_config_dir() -> Path:
    return Path(__file__).resolve().parent / "config"


@dataclass(slots=True)
class RTGRuntimeConfig:
    root: Path = field(
        default_factory=lambda: Path(os.getenv("NSA_RTG_ROOT", "work/rtg"))
    )
    enabled: bool = field(default_factory=lambda: _env_bool("NSA_RTG_ENABLED", "1"))
    base_budget: int = int(os.getenv("NSA_RTG_BASE_BUDGET", "4096"))
    min_budget: int = int(os.getenv("NSA_RTG_MIN_BUDGET", "64"))
    max_budget: int = int(os.getenv("NSA_RTG_MAX_BUDGET", "8192"))
    chunk_size: int = int(os.getenv("NSA_RTG_CHUNK_SIZE", "64"))
    tool_confidence_commit: float = float(
        os.getenv("NSA_RTG_TOOL_CONF_COMMIT", "0.85")
    )
    self_consistency_commit: float = float(
        os.getenv("NSA_RTG_SELF_CONSISTENCY_COMMIT", "0.90")
    )
    kv_pressure_soft: float = float(os.getenv("NSA_RTG_KV_PRESSURE_SOFT", "0.70"))
    kv_pressure_hard: float = float(os.getenv("NSA_RTG_KV_PRESSURE_HARD", "0.90"))
    memory_pressure_hard: float = float(
        os.getenv("NSA_RTG_MEMORY_PRESSURE_HARD", "0.85")
    )
    slo_soft_ms: float = float(os.getenv("NSA_RTG_SLO_SOFT_MS", "4000"))
    entropy_stop: float = float(os.getenv("NSA_RTG_ENTROPY_STOP", "0.35"))
    plateau_epsilon: float = float(os.getenv("NSA_RTG_PLATEAU_EPS", "0.02"))
    plateau_windows: int = int(os.getenv("NSA_RTG_PLATEAU_WINDOWS", "3"))
    roi_stop: float = float(os.getenv("NSA_RTG_ROI_STOP", "0.05"))
    cost_per_1k_tokens: float = float(os.getenv("NSA_RTG_COST_PER_1K", "0.0006"))
    energy_joules_budget: float = float(os.getenv("NSA_RTG_ENERGY_JOULES", "50"))
    watts_per_token: float = float(os.getenv("NSA_RTG_WATTS_PER_TOKEN", "0.002"))
    bandit_enabled: bool = field(
        default_factory=lambda: _env_bool("NSA_RTG_BANDIT", "1")
    )
    bandit_beta: float = float(os.getenv("NSA_RTG_BANDIT_BETA", "0.5"))
    bandit_window: int = int(os.getenv("NSA_RTG_BANDIT_WINDOW", "50"))
    swarm_enabled: bool = field(
        default_factory=lambda: _env_bool("NSA_RTG_SWARM", "1")
    )
    swarm_global_tokens: int = int(os.getenv("NSA_RTG_SWARM_TOKENS", "65536"))
    ppo_enabled: bool = field(default_factory=lambda: _env_bool("NSA_RTG_PPO", "0"))
    otel_enabled: bool = field(default_factory=lambda: _env_bool("NSA_RTG_OTEL", "0"))
    otel_endpoint: str = os.getenv("NSA_RTG_OTEL_ENDPOINT", "")
    force_close_message: str = os.getenv(
        "NSA_RTG_FORCE_CLOSE",
        "Due to time constraints, I need to give my answer now.",
    )
    thinking_close_token: str = os.getenv(
        "NSA_RTG_THINKING_CLOSE_TOKEN",
        "</think>",
    )
    policy: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    hardware: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def load_rtg_config(root: Path | None = None) -> RTGRuntimeConfig:
    cfg = RTGRuntimeConfig()
    if root is not None:
        cfg.root = Path(root)
        cfg.root.mkdir(parents=True, exist_ok=True)
    pkg = _pkg_config_dir()
    policy = _load_yaml(pkg / "policy.yaml")
    thresholds = _load_yaml(pkg / "thresholds.yaml")
    hardware = _load_yaml(pkg / "hardware.yaml")
    budgets = _load_yaml(pkg / "budgets.yaml")
    if budgets:
        cfg.base_budget = int(budgets.get("base_budget", cfg.base_budget))
        cfg.min_budget = int(budgets.get("min_budget", cfg.min_budget))
        cfg.max_budget = int(budgets.get("max_budget", cfg.max_budget))
        cfg.chunk_size = int(budgets.get("chunk_size", cfg.chunk_size))
        cfg.energy_joules_budget = float(
            budgets.get("energy_joules_budget", cfg.energy_joules_budget)
        )
        cfg.cost_per_1k_tokens = float(
            budgets.get("cost_per_1k_tokens", cfg.cost_per_1k_tokens)
        )
    if thresholds:
        cfg.tool_confidence_commit = float(
            thresholds.get("tool_confidence_commit", cfg.tool_confidence_commit)
        )
        cfg.self_consistency_commit = float(
            thresholds.get("self_consistency_commit", cfg.self_consistency_commit)
        )
        cfg.kv_pressure_soft = float(
            thresholds.get("kv_pressure_soft", cfg.kv_pressure_soft)
        )
        cfg.kv_pressure_hard = float(
            thresholds.get("kv_pressure_hard", cfg.kv_pressure_hard)
        )
        cfg.entropy_stop = float(thresholds.get("entropy_stop", cfg.entropy_stop))
        cfg.plateau_epsilon = float(
            thresholds.get("plateau_epsilon", cfg.plateau_epsilon)
        )
        cfg.plateau_windows = int(thresholds.get("plateau_windows", cfg.plateau_windows))
        cfg.roi_stop = float(thresholds.get("roi_stop", cfg.roi_stop))
    cfg.policy = policy
    cfg.thresholds = thresholds
    cfg.hardware = hardware
    if policy.get("force_close_message"):
        cfg.force_close_message = str(policy["force_close_message"])
    if policy.get("thinking_close_token"):
        cfg.thinking_close_token = str(policy["thinking_close_token"])
    return cfg
