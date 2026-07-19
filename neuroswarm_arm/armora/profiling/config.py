"""RPF runtime configuration — NSA_RPF_* env knobs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .schemas import ProfilingMode


def _bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default) not in {"0", "false", "False", "no", "NO"}


def _float(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def _int(name: str, default: str) -> int:
    return int(os.getenv(name, default))


_MODE_ALIASES: dict[str, ProfilingMode] = {m.value: m for m in ProfilingMode}


@dataclass(slots=True)
class RPFRuntimeConfig:
    """Configurable Runtime Profiling Framework settings."""

    work_dir: Path = field(default_factory=lambda: Path("work/profiling"))
    enabled: bool = True
    mode: ProfilingMode = ProfilingMode.PRODUCTION
    provider: str = "auto"
    allow_performix: bool = True
    sample_hz: float = 1.0
    telemetry: str = "prometheus"
    exporter: str = "json"
    persistence: str = "json"
    dashboard: str = "grafana"
    plugins: tuple[str, ...] = ()
    otel_enabled: bool = False
    history_window: int = 200
    feedback_min_samples: int = 3
    max_provider_failures: int = 3
    parca_url: str = ""
    pyroscope_url: str = ""
    performix_recipe: str = "code_hotspots"
    performix_binary: str = "apx"


def load_rpf_config(*, work_dir: Path | None = None) -> RPFRuntimeConfig:
    plugins_raw = os.getenv("NSA_RPF_PLUGINS", "").strip()
    plugins = tuple(p.strip() for p in plugins_raw.split(",") if p.strip())
    mode_raw = os.getenv("NSA_RPF_MODE", "production").strip().lower()
    mode = _MODE_ALIASES.get(mode_raw, ProfilingMode.PRODUCTION)
    enabled = _bool("NSA_RPF_ENABLED", "1")
    if not enabled:
        mode = ProfilingMode.DISABLED
    resolved_work = Path(work_dir) if work_dir is not None else Path(
        os.getenv("NSA_RPF_WORK", "work/profiling")
    )
    cfg = RPFRuntimeConfig(
        work_dir=resolved_work,
        enabled=enabled,
        mode=mode,
        provider=os.getenv("NSA_RPF_PROVIDER", "auto").strip().lower() or "auto",
        allow_performix=_bool("NSA_RPF_ALLOW_PERFORMIX", "1"),
        sample_hz=_float("NSA_RPF_SAMPLE_HZ", "1"),
        telemetry=os.getenv("NSA_RPF_TELEMETRY", "prometheus"),
        exporter=os.getenv("NSA_RPF_EXPORTER", "json"),
        persistence=os.getenv("NSA_RPF_PERSISTENCE", "json"),
        dashboard=os.getenv("NSA_RPF_DASHBOARD", "grafana"),
        plugins=plugins,
        otel_enabled=_bool("NSA_RPF_OTEL", "0"),
        history_window=_int("NSA_RPF_HISTORY_WINDOW", "200"),
        feedback_min_samples=_int("NSA_RPF_FEEDBACK_MIN_SAMPLES", "3"),
        max_provider_failures=_int("NSA_RPF_MAX_PROVIDER_FAILURES", "3"),
        parca_url=os.getenv("NSA_RPF_PARCA_URL", "").strip(),
        pyroscope_url=os.getenv("NSA_RPF_PYROSCOPE_URL", "").strip(),
        performix_recipe=os.getenv("NSA_RPF_PERFORMIX_RECIPE", "code_hotspots"),
        performix_binary=os.getenv("NSA_RPF_PERFORMIX_BINARY", "apx"),
    )
    try:
        cfg.work_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return cfg
