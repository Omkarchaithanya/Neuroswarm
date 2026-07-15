"""RMF runtime configuration from NSA_RMF_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(slots=True)
class RMFRuntimeConfig:
    enabled: bool = True
    exporters: tuple[str, ...] = ("prometheus", "openmetrics")
    scrape_host: str = "0.0.0.0"
    scrape_port: int = 0
    metrics_token: str = ""
    buffer_max: int = 65536
    flush_ms: int = 25
    flush_batch: int = 2048
    cardinality_max: int = 2048
    performix_enabled: bool = False
    performix_path: str = "work/haoe/performix_snapshot.json"
    collector_interval_s: float = 5.0
    otlp_endpoint: str = ""
    otlp_insecure: bool = True
    plugins: tuple[str, ...] = ()
    work_dir: Path = field(default_factory=lambda: Path("work/rmf"))
    dual_write_legacy: bool = True
    standalone_scrape: bool = False


def load_rmf_config() -> RMFRuntimeConfig:
    work = Path(os.getenv("NSA_RMF_WORK_DIR", "work/rmf"))
    return RMFRuntimeConfig(
        enabled=_env_bool("NSA_RMF_ENABLED", True),
        exporters=_env_csv("NSA_RMF_EXPORTERS", ("prometheus", "openmetrics")),
        scrape_host=os.getenv("NSA_RMF_SCRAPE_HOST", "0.0.0.0"),
        scrape_port=_env_int("NSA_RMF_SCRAPE_PORT", 0),
        metrics_token=os.getenv("NSA_RMF_METRICS_TOKEN", ""),
        buffer_max=_env_int("NSA_RMF_BUFFER_MAX", 65536),
        flush_ms=_env_int("NSA_RMF_FLUSH_MS", 25),
        flush_batch=_env_int("NSA_RMF_FLUSH_BATCH", 2048),
        cardinality_max=_env_int("NSA_RMF_CARDINALITY_MAX", 2048),
        performix_enabled=_env_bool("NSA_RMF_PERFORMIX", False),
        performix_path=os.getenv("NSA_RMF_PERFORMIX_PATH", "work/haoe/performix_snapshot.json"),
        collector_interval_s=_env_float("NSA_RMF_COLLECTOR_INTERVAL_S", 5.0),
        otlp_endpoint=os.getenv("NSA_RMF_OTLP_ENDPOINT", ""),
        otlp_insecure=_env_bool("NSA_RMF_OTLP_INSECURE", True),
        plugins=_env_csv("NSA_RMF_PLUGINS", ()),
        work_dir=work,
        dual_write_legacy=_env_bool("NSA_RMF_DUAL_WRITE_LEGACY", True),
        standalone_scrape=_env_bool("NSA_RMF_STANDALONE_SCRAPE", False),
    )
