"""Cognitive Memory Runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw not in {"0", "false", "False", "no", "NO"}


@dataclass(slots=True)
class MemoryRuntimeConfig:
    """Env-driven config for the Cognitive Memory Runtime."""

    store_root: Path = field(default_factory=lambda: Path(os.getenv("NSA_MEM_STORE", "work/memory")))
    provider: str = field(default_factory=lambda: os.getenv("NSA_MEM_PROVIDER", "mem0").lower())
    llm_mode: str = field(default_factory=lambda: os.getenv("NSA_MEM_LLM", "local").lower())
    # local → OpenAI-compatible llama.cpp; openai → cloud; none → direct ingest only
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("NSA_MEM_LLM_BASE_URL", os.getenv("NSA_TIER1_URL", "http://127.0.0.1:8080"))
    )
    llm_api_key: str = field(default_factory=lambda: os.getenv("NSA_MEM_LLM_API_KEY", os.getenv("OPENAI_API_KEY", "local")))
    llm_model: str = field(default_factory=lambda: os.getenv("NSA_MEM_LLM_MODEL", "gpt-4o-mini"))
    embedder_model: str = field(
        default_factory=lambda: os.getenv("NSA_MEM_EMBEDDER_MODEL", "text-embedding-3-small")
    )
    qdrant_path: Path = field(
        default_factory=lambda: Path(os.getenv("NSA_MEM_QDRANT_PATH", "work/memory/qdrant"))
    )
    collection_name: str = field(default_factory=lambda: os.getenv("NSA_MEM_COLLECTION", "neuroswarm_memory"))
    default_ttl_seconds: int | None = field(
        default_factory=lambda: (
            int(os.getenv("NSA_MEM_TTL_SECONDS")) if os.getenv("NSA_MEM_TTL_SECONDS") else None
        )
    )
    cache_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("NSA_MEM_CACHE_TTL", "60")))
    cache_max_entries: int = field(default_factory=lambda: int(os.getenv("NSA_MEM_CACHE_MAX", "2048")))
    search_top_k: int = field(default_factory=lambda: int(os.getenv("NSA_MEM_TOP_K", "5")))
    search_threshold: float = field(default_factory=lambda: float(os.getenv("NSA_MEM_THRESHOLD", "0.1")))
    rerank: bool = field(default_factory=lambda: _env_bool("NSA_MEM_RERANK", False))
    circuit_fail_threshold: int = field(default_factory=lambda: int(os.getenv("NSA_MEM_CIRCUIT_FAILS", "5")))
    circuit_reset_seconds: float = field(default_factory=lambda: float(os.getenv("NSA_MEM_CIRCUIT_RESET", "30")))
    retry_attempts: int = field(default_factory=lambda: int(os.getenv("NSA_MEM_RETRIES", "2")))
    sample_performance: float = field(default_factory=lambda: float(os.getenv("NSA_MEM_SAMPLE_PERF", "1.0")))
    enable_reflection: bool = field(default_factory=lambda: _env_bool("NSA_MEM_REFLECTION", True))
    enable_prediction: bool = field(default_factory=lambda: _env_bool("NSA_MEM_PREDICTION", True))
    importance_recency_weight: float = 0.25
    importance_frequency_weight: float = 0.2
    importance_success_weight: float = 0.2
    importance_cost_weight: float = 0.1
    importance_reflection_weight: float = 0.15
    importance_workflow_weight: float = 0.1
    metadata_index_path: Path | None = None

    def __post_init__(self) -> None:
        # Keep derived paths under store_root for isolated tests / custom roots.
        if self.metadata_index_path is None or not str(self.metadata_index_path).startswith(str(self.store_root)):
            self.metadata_index_path = self.store_root / "index" / "metadata.json"
        if not str(self.qdrant_path).startswith(str(self.store_root)):
            self.qdrant_path = self.store_root / "qdrant"
        self.store_root.mkdir(parents=True, exist_ok=True)
        self.qdrant_path.mkdir(parents=True, exist_ok=True)
        (self.store_root / "index").mkdir(parents=True, exist_ok=True)
        (self.store_root / "json").mkdir(parents=True, exist_ok=True)


def load_memory_config(store_root: Path | None = None) -> MemoryRuntimeConfig:
    cfg = MemoryRuntimeConfig()
    if store_root is not None:
        cfg.store_root = Path(store_root)
        cfg.qdrant_path = cfg.store_root / "qdrant"
        cfg.metadata_index_path = cfg.store_root / "index" / "metadata.json"
        cfg.__post_init__()
    return cfg
