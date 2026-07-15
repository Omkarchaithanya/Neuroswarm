"""Budget runtime configuration — all limits from env/config, never hardcoded peers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default) not in {"0", "false", "False", "no", "NO"}


def _float(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def _int(name: str, default: str) -> int:
    return int(os.getenv(name, default))


@dataclass(slots=True)
class BudgetRuntimeConfig:
    """Configurable ceilings and model rates for ARMORA Budget Envelope."""

    work_dir: Path = field(default_factory=lambda: Path("work/budget"))
    persistence: str = "sqlite"
    cost_model: str = "default"
    energy_model: str = "default"
    estimator: str = "default"
    policy_compiler: str = "default"
    telemetry: str = "prometheus"
    plugins: tuple[str, ...] = ()

    # Per-request template defaults (overridden by PolicyEngine)
    default_cost_usd: float = 0.05
    default_latency_ms: float = 4000.0
    default_memory_bytes: int = 8 * 1024 * 1024 * 1024
    default_energy_joules: float = 50.0
    default_prompt_tokens: int = 8192
    default_completion_tokens: int = 2048
    default_reasoning_tokens: int = 512
    default_kv_bytes: int = 2 * 1024 * 1024 * 1024
    default_tool_calls: int = 8
    default_cpu_seconds: float = 120.0
    default_streaming_ms: float = 60_000.0
    default_retries: int = 2
    default_concurrency: int = 4
    default_max_context_length: int = 32_768
    default_max_batch_size: int = 8
    default_max_worker_time_ms: float = 120_000.0
    default_max_queue_time_ms: float = 5_000.0
    default_max_backend_cost_usd: float = 0.05
    default_max_planner_cost_usd: float = 0.005
    default_max_cache_allocation_bytes: int = 1 * 1024 * 1024 * 1024
    default_max_memory_pages: int = 65_536
    default_min_confidence: float = 0.0
    default_priority: int = 0

    # Cost rates ($ per 1k tokens unless noted)
    usd_per_1k_prompt: float = 0.0001
    usd_per_1k_completion: float = 0.0003
    usd_per_1k_reasoning: float = 0.0004
    usd_per_1k_cache_read: float = 0.000025
    usd_per_1k_cache_write: float = 0.000125
    kv_usd_per_gb_s: float = 0.000001
    tool_call_usd: float = 0.0005
    planner_overhead_usd: float = 0.00005

    # Energy model
    base_watts: float = 15.0
    watts_per_thread: float = 2.5
    numa_efficiency: float = 1.0

    # KV estimation
    kv_paging_overhead: float = 1.06
    default_layers: int = 32
    default_kv_heads: int = 8
    default_head_dim: int = 128
    default_elem_size: int = 2

    # Hardness defaults
    cost_hard: bool = True
    latency_hard: bool = True
    memory_hard: bool = True
    energy_hard: bool = False
    token_hard: bool = True
    kv_hard: bool = True
    tool_hard: bool = True
    compute_hard: bool = False
    streaming_hard: bool = False
    retry_hard: bool = True

    # Optimizer ladder (ordered action names)
    degrade_ladder: tuple[str, ...] = (
        "lower_tier",
        "lower_quant",
        "cut_reasoning",
        "trim_context",
        "disable_speculation",
        "drop_tools",
        "cut_retries",
        "abort",
    )

    # Tenant aggregate (ResourceQuota-style)
    tenant_max_cost_usd: float = 100.0
    tenant_max_memory_bytes: int = 64 * 1024 * 1024 * 1024
    tenant_max_concurrent: int = 128

    reserve_percentile: str = "p90"


def load_budget_config(*, work_dir: Path | None = None) -> BudgetRuntimeConfig:
    plugins_raw = os.getenv("NSA_BUDGET_PLUGINS", "").strip()
    plugins = tuple(p.strip() for p in plugins_raw.split(",") if p.strip())
    ladder_raw = os.getenv("NSA_BUDGET_DEGRADE_LADDER", "").strip()
    ladder = (
        tuple(x.strip() for x in ladder_raw.split(",") if x.strip())
        if ladder_raw
        else (
            "lower_tier",
            "lower_quant",
            "cut_reasoning",
            "trim_context",
            "disable_speculation",
            "drop_tools",
            "cut_retries",
            "abort",
        )
    )
    cfg = BudgetRuntimeConfig(
        work_dir=Path(os.getenv("NSA_BUDGET_WORK", str(work_dir or "work/budget"))),
        persistence=os.getenv("NSA_BUDGET_PERSISTENCE", "sqlite"),
        cost_model=os.getenv("NSA_BUDGET_COST_MODEL", "default"),
        energy_model=os.getenv("NSA_BUDGET_ENERGY_MODEL", "default"),
        estimator=os.getenv("NSA_BUDGET_ESTIMATOR", "default"),
        policy_compiler=os.getenv("NSA_BUDGET_POLICY_COMPILER", "default"),
        telemetry=os.getenv("NSA_BUDGET_TELEMETRY", "prometheus"),
        plugins=plugins,
        default_cost_usd=_float("NSA_BUDGET_DEFAULT_COST_USD", "0.05"),
        default_latency_ms=_float("NSA_BUDGET_DEFAULT_LATENCY_MS", "4000"),
        default_memory_bytes=_int("NSA_BUDGET_DEFAULT_MEMORY_BYTES", str(8 * 1024**3)),
        default_energy_joules=_float("NSA_BUDGET_DEFAULT_ENERGY_J", "50"),
        default_prompt_tokens=_int("NSA_BUDGET_DEFAULT_PROMPT_TOKENS", "8192"),
        default_completion_tokens=_int("NSA_BUDGET_DEFAULT_COMPLETION_TOKENS", "2048"),
        default_reasoning_tokens=_int("NSA_BUDGET_DEFAULT_REASONING_TOKENS", "512"),
        default_kv_bytes=_int("NSA_BUDGET_DEFAULT_KV_BYTES", str(2 * 1024**3)),
        default_tool_calls=_int("NSA_BUDGET_DEFAULT_TOOL_CALLS", "8"),
        default_cpu_seconds=_float("NSA_BUDGET_DEFAULT_CPU_SECONDS", "120"),
        default_streaming_ms=_float("NSA_BUDGET_DEFAULT_STREAMING_MS", "60000"),
        default_retries=_int("NSA_BUDGET_DEFAULT_RETRIES", "2"),
        default_concurrency=_int("NSA_BUDGET_DEFAULT_CONCURRENCY", "4"),
        default_max_context_length=_int("NSA_BUDGET_MAX_CONTEXT", "32768"),
        default_max_batch_size=_int("NSA_BUDGET_MAX_BATCH", "8"),
        default_max_worker_time_ms=_float("NSA_BUDGET_MAX_WORKER_MS", "120000"),
        default_max_queue_time_ms=_float("NSA_BUDGET_MAX_QUEUE_MS", "5000"),
        default_max_backend_cost_usd=_float("NSA_BUDGET_MAX_BACKEND_USD", "0.05"),
        default_max_planner_cost_usd=_float("NSA_BUDGET_MAX_PLANNER_USD", "0.005"),
        default_max_cache_allocation_bytes=_int(
            "NSA_BUDGET_MAX_CACHE_BYTES", str(1 * 1024**3)
        ),
        default_max_memory_pages=_int("NSA_BUDGET_MAX_MEMORY_PAGES", "65536"),
        default_min_confidence=_float("NSA_BUDGET_MIN_CONFIDENCE", "0.0"),
        default_priority=_int("NSA_BUDGET_DEFAULT_PRIORITY", "0"),
        usd_per_1k_prompt=_float("NSA_BUDGET_USD_PER_1K_PROMPT", "0.0001"),
        usd_per_1k_completion=_float("NSA_BUDGET_USD_PER_1K_COMPLETION", "0.0003"),
        usd_per_1k_reasoning=_float("NSA_BUDGET_USD_PER_1K_REASONING", "0.0004"),
        usd_per_1k_cache_read=_float("NSA_BUDGET_USD_PER_1K_CACHE_READ", "0.000025"),
        usd_per_1k_cache_write=_float("NSA_BUDGET_USD_PER_1K_CACHE_WRITE", "0.000125"),
        kv_usd_per_gb_s=_float("NSA_BUDGET_KV_USD_PER_GB_S", "0.000001"),
        tool_call_usd=_float("NSA_BUDGET_TOOL_CALL_USD", "0.0005"),
        planner_overhead_usd=_float("NSA_BUDGET_PLANNER_OVERHEAD_USD", "0.00005"),
        base_watts=_float("NSA_BUDGET_BASE_WATTS", "15"),
        watts_per_thread=_float("NSA_BUDGET_WATTS_PER_THREAD", "2.5"),
        numa_efficiency=_float("NSA_BUDGET_NUMA_EFFICIENCY", "1.0"),
        kv_paging_overhead=_float("NSA_BUDGET_KV_PAGING_OVERHEAD", "1.06"),
        default_layers=_int("NSA_BUDGET_KV_LAYERS", "32"),
        default_kv_heads=_int("NSA_BUDGET_KV_HEADS", "8"),
        default_head_dim=_int("NSA_BUDGET_KV_HEAD_DIM", "128"),
        default_elem_size=_int("NSA_BUDGET_KV_ELEM_SIZE", "2"),
        cost_hard=_bool("NSA_BUDGET_COST_HARD", "1"),
        latency_hard=_bool("NSA_BUDGET_LATENCY_HARD", "1"),
        memory_hard=_bool("NSA_BUDGET_MEMORY_HARD", "1"),
        energy_hard=_bool("NSA_BUDGET_ENERGY_HARD", "0"),
        token_hard=_bool("NSA_BUDGET_TOKEN_HARD", "1"),
        kv_hard=_bool("NSA_BUDGET_KV_HARD", "1"),
        tool_hard=_bool("NSA_BUDGET_TOOL_HARD", "1"),
        compute_hard=_bool("NSA_BUDGET_COMPUTE_HARD", "0"),
        streaming_hard=_bool("NSA_BUDGET_STREAMING_HARD", "0"),
        retry_hard=_bool("NSA_BUDGET_RETRY_HARD", "1"),
        degrade_ladder=ladder,
        tenant_max_cost_usd=_float("NSA_BUDGET_TENANT_MAX_COST_USD", "100"),
        tenant_max_memory_bytes=_int(
            "NSA_BUDGET_TENANT_MAX_MEMORY_BYTES", str(64 * 1024**3)
        ),
        tenant_max_concurrent=_int("NSA_BUDGET_TENANT_MAX_CONCURRENT", "128"),
        reserve_percentile=os.getenv("NSA_BUDGET_RESERVE_PERCENTILE", "p90"),
    )
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    return cfg
