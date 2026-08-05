"""DIPA runtime configuration — YAML + NSA_DIPA_* env overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _env_bool(name: str, default: str = "1") -> bool:
    return os.getenv(name, default) not in {"0", "false", "False", "no", "NO"}


def _load_yaml(name: str) -> dict[str, Any]:
    path = _CONFIG_DIR / name
    if not path.exists():
        return {}
    if yaml is None:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


@dataclass
class DIPARuntimeConfig:
    root: Path = field(
        default_factory=lambda: Path(os.getenv("NSA_DIPA_ROOT", "work/dipa"))
    )
    affinity_enabled: bool = field(
        default_factory=lambda: _env_bool("NSA_DIPA_AFFINITY", "1")
    )
    otel_enabled: bool = field(
        default_factory=lambda: _env_bool("NSA_DIPA_OTEL", "0")
    )
    otel_endpoint: str = field(
        default_factory=lambda: os.getenv("NSA_DIPA_OTEL_ENDPOINT", "")
    )
    default_timeout_s: float = field(
        default_factory=lambda: float(os.getenv("NSA_DIPA_TIMEOUT", "120"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("NSA_DIPA_MAX_RETRIES", "2"))
    )
    prefill_pool_size: int = field(
        default_factory=lambda: int(os.getenv("NSA_DIPA_PREFILL_POOL", "2"))
    )
    decode_pool_size: int = field(
        default_factory=lambda: int(os.getenv("NSA_DIPA_DECODE_POOL", "4"))
    )
    cascade_confidence: float = field(
        default_factory=lambda: float(os.getenv("NSA_DIPA_CASCADE_CONF", "0.85"))
    )
    stream_default: bool = field(
        default_factory=lambda: _env_bool("NSA_DIPA_STREAM", "0")
    )
    circuit_failure_threshold: int = field(
        default_factory=lambda: int(os.getenv("NSA_DIPA_CIRCUIT_FAILS", "5"))
    )
    circuit_reset_s: float = field(
        default_factory=lambda: float(os.getenv("NSA_DIPA_CIRCUIT_RESET", "30"))
    )
    policy: dict[str, Any] = field(default_factory=dict)
    cascade: dict[str, Any] = field(default_factory=dict)
    routing: dict[str, Any] = field(default_factory=dict)
    hardware: dict[str, Any] = field(default_factory=dict)
    streaming: dict[str, Any] = field(default_factory=dict)
    batching: dict[str, Any] = field(default_factory=dict)
    draft_models: dict[str, Any] = field(default_factory=dict)
    pd_mode: str = field(
        default_factory=lambda: os.getenv("NSA_DIPA_PD_MODE", "off").strip().lower()
        or "off"
    )
    prefill_backend: str = field(
        default_factory=lambda: os.getenv("NSA_DIPA_PREFILL_BACKEND", "").strip()
    )
    decode_backend: str = field(
        default_factory=lambda: os.getenv("NSA_DIPA_DECODE_BACKEND", "llama_cpp").strip()
        or "llama_cpp"
    )
    sglang_url: str = field(
        default_factory=lambda: os.getenv("NSA_DIPA_SGLANG_URL", "").strip()
    )
    sglang_router_url: str = field(
        default_factory=lambda: os.getenv("NSA_DIPA_SGLANG_ROUTER_URL", "").strip()
    )
    chunk_size: int = field(
        default_factory=lambda: int(os.getenv("NSA_DIPA_CHUNK_SIZE", "2048"))
    )
    pd_min_prompt_tokens: int = field(
        default_factory=lambda: int(os.getenv("NSA_DIPA_PD_MIN_PROMPT_TOKENS", "64"))
    )
    llama_slot_dir: str = field(
        default_factory=lambda: os.getenv(
            "NSA_LLAMA_SLOT_DIR", "/tmp/neuroswarm-slots"
        )
    )
    llama_slot_kv_reuse: bool = field(
        default_factory=lambda: _env_bool("NSA_LLAMA_SLOT_KV_REUSE", "1")
    )

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.policy:
            self.policy = _load_yaml("policy.yaml")
        if not self.cascade:
            self.cascade = _load_yaml("cascade.yaml")
        if not self.routing:
            self.routing = _load_yaml("routing.yaml")
        if not self.hardware:
            self.hardware = _load_yaml("hardware.yaml")
        if not self.streaming:
            self.streaming = _load_yaml("streaming.yaml")
        if not self.batching:
            self.batching = _load_yaml("batching.yaml")
        hw = self.hardware
        if "prefill_pool_size" in hw and os.getenv("NSA_DIPA_PREFILL_POOL") is None:
            self.prefill_pool_size = int(hw["prefill_pool_size"])
        if "decode_pool_size" in hw and os.getenv("NSA_DIPA_DECODE_POOL") is None:
            self.decode_pool_size = int(hw["decode_pool_size"])
        if "affinity_enabled" in hw and os.getenv("NSA_DIPA_AFFINITY") is None:
            self.affinity_enabled = bool(hw["affinity_enabled"])
        if self.pd_mode in {"soft", "native"} and not self.prefill_backend:
            self.prefill_backend = "sglang"

    @property
    def pd_enabled(self) -> bool:
        return self.pd_mode in {"soft", "native"}


def load_dipa_config(root: Path | None = None) -> DIPARuntimeConfig:
    cfg = DIPARuntimeConfig()
    if root is not None:
        cfg.root = Path(root)
        cfg.__post_init__()
    return cfg
