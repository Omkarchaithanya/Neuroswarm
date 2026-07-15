"""RCIS runtime configuration — all rates from env/config, never hardcoded in estimators."""

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
class RCISRuntimeConfig:
    """Configurable rates and backends for Runtime Cost Intelligence System."""

    work_dir: Path = field(default_factory=lambda: Path("work/rcis"))
    persistence: str = "sqlite"
    cost_model: str = "default"
    energy_model: str = "default"
    predictor: str = "default"
    accounting: str = "default"
    telemetry: str = "prometheus"
    dashboard: str = "grafana"
    plugins: tuple[str, ...] = ()
    enabled: bool = True
    ewma_alpha: float = 0.3
    history_window: int = 200
    feedback_min_samples: int = 3

    # Token signal rates ($ per 1k tokens)
    usd_per_1k_prompt: float = 0.0001
    usd_per_1k_completion: float = 0.0003
    usd_per_1k_reasoning: float = 0.0004
    usd_per_1k_cache_read: float = 0.000025
    usd_per_1k_cache_write: float = 0.000125
    usd_per_1k_accepted_draft: float = 0.000075
    usd_per_1k_rejected_draft: float = 0.00005

    # Compute / memory / energy / KV opportunity costs
    usd_per_cpu_second: float = 0.00001
    usd_per_gb_memory_second: float = 0.000001
    usd_per_joule: float = 0.0000001
    kv_usd_per_gb_s: float = 0.000001
    tool_call_usd: float = 0.0005
    retry_usd: float = 0.00025
    streaming_usd_per_second: float = 0.00001
    planner_usd_per_ms: float = 0.00000001
    queue_usd_per_ms: float = 0.000000005

    # Energy fallback (psutil / TDP amortization)
    base_watts: float = 15.0
    watts_per_thread: float = 2.5
    numa_efficiency: float = 1.0
    carbon_kg_per_joule: float = 1.2e-7

    # Prediction priors (used when no history)
    default_latency_ms: float = 800.0
    default_tokens_completion: float = 256.0
    default_tokens_reasoning: float = 64.0
    default_cpu_seconds: float = 2.0
    default_memory_bytes: float = 2 * 1024**3
    default_kv_growth_bytes: float = 64 * 1024**2
    default_energy_joules: float = 30.0
    latency_per_prompt_token_ms: float = 0.02
    latency_per_completion_token_ms: float = 8.0
    prediction_p90_factor: float = 1.25

    # Speculation heuristics
    draft_cost_factor: float = 0.25
    verify_cost_factor: float = 0.15
    saved_decode_factor: float = 0.5


def load_rcis_config(*, work_dir: Path | None = None) -> RCISRuntimeConfig:
    plugins_raw = os.getenv("NSA_RCIS_PLUGINS", "").strip()
    plugins = tuple(p.strip() for p in plugins_raw.split(",") if p.strip())
    # Explicit work_dir wins over env so tests/composition roots stay isolated.
    resolved_work = Path(work_dir) if work_dir is not None else Path(
        os.getenv("NSA_RCIS_WORK", "work/rcis")
    )
    cfg = RCISRuntimeConfig(
        work_dir=resolved_work,
        persistence=os.getenv("NSA_RCIS_PERSISTENCE", "sqlite"),
        cost_model=os.getenv("NSA_RCIS_COST_MODEL", "default"),
        energy_model=os.getenv("NSA_RCIS_ENERGY_MODEL", "default"),
        predictor=os.getenv("NSA_RCIS_PREDICTOR", "default"),
        accounting=os.getenv("NSA_RCIS_ACCOUNTING", "default"),
        telemetry=os.getenv("NSA_RCIS_TELEMETRY", "prometheus"),
        dashboard=os.getenv("NSA_RCIS_DASHBOARD", "grafana"),
        plugins=plugins,
        enabled=_bool("NSA_RCIS_ENABLED", "1"),
        ewma_alpha=_float("NSA_RCIS_EWMA_ALPHA", "0.3"),
        history_window=_int("NSA_RCIS_HISTORY_WINDOW", "200"),
        feedback_min_samples=_int("NSA_RCIS_FEEDBACK_MIN_SAMPLES", "3"),
        usd_per_1k_prompt=_float("NSA_RCIS_USD_PER_1K_PROMPT", "0.0001"),
        usd_per_1k_completion=_float("NSA_RCIS_USD_PER_1K_COMPLETION", "0.0003"),
        usd_per_1k_reasoning=_float("NSA_RCIS_USD_PER_1K_REASONING", "0.0004"),
        usd_per_1k_cache_read=_float("NSA_RCIS_USD_PER_1K_CACHE_READ", "0.000025"),
        usd_per_1k_cache_write=_float("NSA_RCIS_USD_PER_1K_CACHE_WRITE", "0.000125"),
        usd_per_1k_accepted_draft=_float("NSA_RCIS_USD_PER_1K_ACCEPTED_DRAFT", "0.000075"),
        usd_per_1k_rejected_draft=_float("NSA_RCIS_USD_PER_1K_REJECTED_DRAFT", "0.00005"),
        usd_per_cpu_second=_float("NSA_RCIS_USD_PER_CPU_SECOND", "0.00001"),
        usd_per_gb_memory_second=_float("NSA_RCIS_USD_PER_GB_MEMORY_SECOND", "0.000001"),
        usd_per_joule=_float("NSA_RCIS_USD_PER_JOULE", "0.0000001"),
        kv_usd_per_gb_s=_float("NSA_RCIS_KV_USD_PER_GB_S", "0.000001"),
        tool_call_usd=_float("NSA_RCIS_TOOL_CALL_USD", "0.0005"),
        retry_usd=_float("NSA_RCIS_RETRY_USD", "0.00025"),
        streaming_usd_per_second=_float("NSA_RCIS_STREAMING_USD_PER_SECOND", "0.00001"),
        planner_usd_per_ms=_float("NSA_RCIS_PLANNER_USD_PER_MS", "0.00000001"),
        queue_usd_per_ms=_float("NSA_RCIS_QUEUE_USD_PER_MS", "0.000000005"),
        base_watts=_float("NSA_RCIS_BASE_WATTS", "15"),
        watts_per_thread=_float("NSA_RCIS_WATTS_PER_THREAD", "2.5"),
        numa_efficiency=_float("NSA_RCIS_NUMA_EFFICIENCY", "1.0"),
        carbon_kg_per_joule=_float("NSA_RCIS_CARBON_KG_PER_JOULE", "0.00000012"),
        default_latency_ms=_float("NSA_RCIS_DEFAULT_LATENCY_MS", "800"),
        default_tokens_completion=_float("NSA_RCIS_DEFAULT_COMPLETION_TOKENS", "256"),
        default_tokens_reasoning=_float("NSA_RCIS_DEFAULT_REASONING_TOKENS", "64"),
        default_cpu_seconds=_float("NSA_RCIS_DEFAULT_CPU_SECONDS", "2"),
        default_memory_bytes=_float("NSA_RCIS_DEFAULT_MEMORY_BYTES", str(2 * 1024**3)),
        default_kv_growth_bytes=_float("NSA_RCIS_DEFAULT_KV_GROWTH_BYTES", str(64 * 1024**2)),
        default_energy_joules=_float("NSA_RCIS_DEFAULT_ENERGY_JOULES", "30"),
        latency_per_prompt_token_ms=_float("NSA_RCIS_LATENCY_PER_PROMPT_TOKEN_MS", "0.02"),
        latency_per_completion_token_ms=_float(
            "NSA_RCIS_LATENCY_PER_COMPLETION_TOKEN_MS", "8"
        ),
        prediction_p90_factor=_float("NSA_RCIS_PREDICTION_P90_FACTOR", "1.25"),
        draft_cost_factor=_float("NSA_RCIS_DRAFT_COST_FACTOR", "0.25"),
        verify_cost_factor=_float("NSA_RCIS_VERIFY_COST_FACTOR", "0.15"),
        saved_decode_factor=_float("NSA_RCIS_SAVED_DECODE_FACTOR", "0.5"),
    )
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    return cfg
