from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    host: str = os.getenv("NSA_HOST", "0.0.0.0")
    port: int = int(os.getenv("NSA_PORT", "8000"))
    tier1_url: str = os.getenv("NSA_TIER1_URL", "http://127.0.0.1:8081")
    tier2_url: str = os.getenv("NSA_TIER2_URL", "http://127.0.0.1:8082")
    tier3_url: str = os.getenv("NSA_TIER3_URL", "http://127.0.0.1:8083")
    model_tier1: str = os.getenv("NSA_MODEL_TIER1", "/models/qwen2.5-0.5b-q4_k_m.gguf")
    model_tier2: str = os.getenv("NSA_MODEL_TIER2", "/models/llama-3.2-3b-q5_k_m.gguf")
    model_tier3: str = os.getenv("NSA_MODEL_TIER3", "/models/llama-3.1-8b-q5_k_m.gguf")
    okf_root: Path = Path(os.getenv("NSA_OKF_ROOT", "okf"))
    mem_store: Path = Path(os.getenv("NSA_MEM_STORE", "work/memory"))
    kv_store: Path = Path(os.getenv("NSA_KV_STORE", "work/kv"))
    benchmarks_dir: Path = Path(os.getenv("NSA_BENCH_DIR", "work/benchmarks"))


def get_config() -> AppConfig:
    cfg = AppConfig()
    cfg.mem_store.mkdir(parents=True, exist_ok=True)
    cfg.kv_store.mkdir(parents=True, exist_ok=True)
    cfg.benchmarks_dir.mkdir(parents=True, exist_ok=True)
    return cfg

