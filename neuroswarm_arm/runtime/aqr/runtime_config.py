"""AQR config loader — YAML + env."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return os.getenv(match.group(1), "")

    return _ENV_PATTERN.sub(repl, value)


def _walk_expand(obj: Any) -> Any:
    if isinstance(obj, str):
        return _expand_env(obj)
    if isinstance(obj, list):
        return [_walk_expand(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _walk_expand(v) for k, v in obj.items()}
    return obj


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return {}
    return _walk_expand(raw)


@dataclass(slots=True)
class AQRRuntimeConfig:
    root: Path
    scoring: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)
    quants: dict[str, Any] = field(default_factory=dict)
    cascade_profiles: dict[str, Any] = field(default_factory=dict)
    discovery: dict[str, Any] = field(default_factory=dict)
    model_dir: str = ""
    hourly_cost_usd: float = 0.05
    otel_enabled: bool = False


def default_config_root() -> Path:
    return Path(__file__).resolve().parent / "config"


def load_aqr_config(root: Path | None = None) -> AQRRuntimeConfig:
    cfg_root = root or default_config_root()
    return AQRRuntimeConfig(
        root=cfg_root,
        scoring=_load_yaml(cfg_root / "scoring.yaml"),
        policy=_load_yaml(cfg_root / "policy.yaml"),
        quants=_load_yaml(cfg_root / "quants.yaml"),
        cascade_profiles=_load_yaml(cfg_root / "cascade_profiles.yaml"),
        discovery=_load_yaml(cfg_root / "discovery.yaml"),
        model_dir=os.getenv("NSA_MODEL_DIR", ""),
        hourly_cost_usd=float(os.getenv("NSA_VM_HOURLY_COST_USD", "0.05")),
        otel_enabled=os.getenv("NSA_AQR_OTEL", "0") not in {"0", "false", "False"},
    )
