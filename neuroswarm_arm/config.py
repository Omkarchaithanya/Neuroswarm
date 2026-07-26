from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    host: str = os.getenv("NSA_HOST", "0.0.0.0")
    port: int = int(os.getenv("NSA_PORT", "8000"))
    tier1_url: str = os.getenv("NSA_TIER1_URL", "http://tier1:8080")
    tier2_url: str = os.getenv("NSA_TIER2_URL", "http://tier2:8080")
    tier3_url: str = os.getenv("NSA_TIER3_URL", "http://tier3:8080")
    model_tier1: str = os.getenv("NSA_MODEL_TIER1", "/models/qwen2.5-0.5b-Instruct-q4_0.gguf")
    model_tier2: str = os.getenv("NSA_MODEL_TIER2", "/models/Qwen2.5-3B-Instruct-Q4_0.gguf")
    model_tier3: str = os.getenv("NSA_MODEL_TIER3", "/models/DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf")
    okf_root: Path = Path(os.getenv("NSA_OKF_ROOT", "okf"))
    okf_artifacts: Path = Path(os.getenv("NSA_OKF_ARTIFACTS", "okf/.okf/artifacts"))
    okf_enabled: bool = os.getenv("NSA_OKF_ENABLED", "1") not in {"0", "false", "False"}
    okf_token_budget: int = int(os.getenv("NSA_OKF_TOKEN_BUDGET", "1200"))
    tool_metadata_root: Path = Path(os.getenv("NSA_TOOL_METADATA_ROOT", "templates/mcp-servers"))
    mem_store: Path = Path(os.getenv("NSA_MEM_STORE", "work/memory"))
    kv_store: Path = Path(os.getenv("NSA_KV_STORE", "work/kv"))
    benchmarks_dir: Path = Path(os.getenv("NSA_BENCH_DIR", "work/benchmarks"))
    router_top_k: int = int(os.getenv("NSA_ROUTER_TOP_K", "3"))
    cascade_confidence_threshold: float = float(os.getenv("NSA_CASCADE_CONFIDENCE_THRESHOLD", "0.85"))
    # KV Memory Runtime (Plane 2)
    kv_block_size: int = int(os.getenv("NSA_KV_BLOCK_SIZE", "256"))
    kv_ram_budget: int = int(os.getenv("NSA_KV_RAM_BUDGET", str(512 * 1024 * 1024)))
    kv_pressure_threshold: float = float(os.getenv("NSA_KV_PRESSURE_THRESHOLD", "0.70"))
    kv_compression: str = os.getenv("NSA_KV_COMPRESSION", "zstd")
    kv_redis_url: str = os.getenv("NSA_KV_REDIS_URL", "redis://localhost:6379/0")
    kv_sharing_backend: str = os.getenv("NSA_KV_SHARING_BACKEND", "mmap")
    kv_bg_migration: bool = os.getenv("NSA_KV_BG_MIGRATION", "1") not in {"0", "false", "False"}
    kv_session_header: str = os.getenv("NSA_KV_SESSION_HEADER", "x-session-id")


def get_config() -> AppConfig:
    cfg = AppConfig()
    cfg.mem_store.mkdir(parents=True, exist_ok=True)
    cfg.kv_store.mkdir(parents=True, exist_ok=True)
    cfg.benchmarks_dir.mkdir(parents=True, exist_ok=True)
    return cfg
