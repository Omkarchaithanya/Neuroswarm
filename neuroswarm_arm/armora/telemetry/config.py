"""ROF runtime configuration — all knobs from NSA_ROF_* env vars."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default) not in {"0", "false", "False", "no", "NO"}


def _int(name: str, default: str) -> int:
    return int(os.getenv(name, default))


def _float(name: str, default: str) -> float:
    return float(os.getenv(name, default))


@dataclass(slots=True)
class ROFRuntimeConfig:
    """Configurable Runtime Observability Framework settings."""

    enabled: bool = True
    service_name: str = "nexus-arm"
    service_version: str = "0.1.0"
    otlp_endpoint: str = ""
    otlp_insecure: bool = True
    sampler: str = "always_on"
    exporters: tuple[str, ...] = ("prometheus", "json")
    plugins: tuple[str, ...] = ()
    work_dir: Path = field(default_factory=lambda: Path("work/rof"))
    json_path: Path = field(default_factory=lambda: Path("work/rof/telemetry.jsonl"))
    sqlite_path: Path = field(default_factory=lambda: Path("work/rof/telemetry.sqlite"))
    duckdb_path: Path = field(default_factory=lambda: Path("work/rof/telemetry.duckdb"))
    batch_size: int = 512
    export_timeout_ms: int = 5000
    export_interval_ms: int = 1000
    max_queue_size: int = 2048
    log_level: str = "INFO"
    prometheus_multiproc: bool = False
    force_sample_errors: bool = True
    force_sample_budget_violations: bool = True
    head_ratio: float = 0.1
    adaptive_error_rate_threshold: float = 0.05
    adaptive_latency_ms_threshold: float = 2000.0
    tail_latency_ms_threshold: float = 1500.0

    @classmethod
    def from_env(cls) -> ROFRuntimeConfig:
        exporters_raw = os.getenv("NSA_ROF_EXPORTERS", "prometheus,json")
        exporters = tuple(x.strip() for x in exporters_raw.split(",") if x.strip())
        plugins_raw = os.getenv("NSA_ROF_PLUGINS", "")
        plugins = tuple(x.strip() for x in plugins_raw.split(",") if x.strip())
        work = Path(os.getenv("NSA_ROF_WORK_DIR", "work/rof"))
        sampler = os.getenv("NSA_ROF_SAMPLER", "always_on")
        head_ratio = 0.1
        if sampler.startswith("head:"):
            try:
                head_ratio = float(sampler.split(":", 1)[1])
            except ValueError:
                head_ratio = 0.1
            sampler = "head"
        return cls(
            enabled=_bool("NSA_ROF_ENABLED", "1"),
            service_name=os.getenv("NSA_ROF_SERVICE_NAME", "nexus-arm"),
            service_version=os.getenv("NSA_ROF_SERVICE_VERSION", "0.1.0"),
            otlp_endpoint=os.getenv("NSA_ROF_OTLP_ENDPOINT", ""),
            otlp_insecure=_bool("NSA_ROF_OTLP_INSECURE", "1"),
            sampler=sampler,
            exporters=exporters or ("prometheus", "json"),
            plugins=plugins,
            work_dir=work,
            json_path=Path(os.getenv("NSA_ROF_JSON_PATH", str(work / "telemetry.jsonl"))),
            sqlite_path=Path(os.getenv("NSA_ROF_SQLITE_PATH", str(work / "telemetry.sqlite"))),
            duckdb_path=Path(os.getenv("NSA_ROF_DUCKDB_PATH", str(work / "telemetry.duckdb"))),
            batch_size=_int("NSA_ROF_BATCH_SIZE", "512"),
            export_timeout_ms=_int("NSA_ROF_EXPORT_TIMEOUT_MS", "5000"),
            export_interval_ms=_int("NSA_ROF_EXPORT_INTERVAL_MS", "1000"),
            max_queue_size=_int("NSA_ROF_MAX_QUEUE_SIZE", "2048"),
            log_level=os.getenv("NSA_ROF_LOG_LEVEL", "INFO"),
            prometheus_multiproc=_bool("NSA_ROF_PROM_MULTIPROC", "0"),
            force_sample_errors=_bool("NSA_ROF_FORCE_SAMPLE_ERRORS", "1"),
            force_sample_budget_violations=_bool("NSA_ROF_FORCE_SAMPLE_BUDGET", "1"),
            head_ratio=head_ratio,
            adaptive_error_rate_threshold=_float("NSA_ROF_ADAPTIVE_ERROR_RATE", "0.05"),
            adaptive_latency_ms_threshold=_float("NSA_ROF_ADAPTIVE_LATENCY_MS", "2000"),
            tail_latency_ms_threshold=_float("NSA_ROF_TAIL_LATENCY_MS", "1500"),
        )


def load_rof_config() -> ROFRuntimeConfig:
    return ROFRuntimeConfig.from_env()
