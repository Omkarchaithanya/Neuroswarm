"""Plugin registry for RPF extensions."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Mapping

from .config import RPFRuntimeConfig
from .exporters import build_exporter
from .telemetry import InMemoryProfileTelemetry, OpenTelemetryProfileBridge

logger = logging.getLogger(__name__)

_PROFILERS: dict[str, Callable[..., Any]] = {}
_EXPORTERS: dict[str, Callable[..., Any]] = {}
_REPORTS: dict[str, Callable[..., Any]] = {}
_METRIC_SOURCES: dict[str, Callable[..., Any]] = {}
_TELEMETRY: dict[str, Callable[..., Any]] = {}
_DASHBOARDS: dict[str, Callable[..., Any]] = {}


def register_profiler(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _PROFILERS[name] = fn
        return fn

    return deco


def register_exporter(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _EXPORTERS[name] = fn
        return fn

    return deco


def register_report_builder(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _REPORTS[name] = fn
        return fn

    return deco


def register_metric_source(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _METRIC_SOURCES[name] = fn
        return fn

    return deco


def register_telemetry(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _TELEMETRY[name] = fn
        return fn

    return deco


def register_dashboard(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _DASHBOARDS[name] = fn
        return fn

    return deco


def discover_plugins(module_paths: tuple[str, ...] | list[str]) -> None:
    for path in module_paths:
        try:
            importlib.import_module(path)
        except Exception as exc:
            logger.warning("rpf plugin import failed for %s: %s", path, exc)


class GrafanaDashboardProvider:
    def name(self) -> str:
        return "grafana"

    def panels(self) -> list[Mapping[str, Any]]:
        return [
            {"title": "IPC", "expr": "profile_ipc"},
            {"title": "CPU %", "expr": "profile_cpu_usage_percent"},
            {"title": "Peak RSS", "expr": "profile_memory_peak_bytes"},
            {"title": "Execution ms", "expr": "profile_execution_ms"},
            {"title": "Planner ms", "expr": "profile_planner_ms"},
            {"title": "Sessions", "expr": "profile_sessions_total"},
            {"title": "Failures", "expr": "profile_failures_total"},
            {"title": "Sample Hz", "expr": "profile_sample_hz"},
        ]


def _register_builtins() -> None:
    if "prometheus" not in _TELEMETRY:
        _TELEMETRY["prometheus"] = InMemoryProfileTelemetry
    if "otel" not in _TELEMETRY:
        _TELEMETRY["otel"] = OpenTelemetryProfileBridge
    if "grafana" not in _DASHBOARDS:
        _DASHBOARDS["grafana"] = GrafanaDashboardProvider
    for name in ("json", "sqlite", "duckdb", "parquet", "prometheus", "otlp"):
        if name not in _EXPORTERS:
            _EXPORTERS[name] = (
                lambda root, n=name, telemetry=None, otel=False, **kw: build_exporter(
                    n, root, telemetry=telemetry, otel=otel
                )
            )


_register_builtins()


class RPFPluginRegistry:
    def __init__(self, cfg: RPFRuntimeConfig) -> None:
        self.cfg = cfg
        discover_plugins(cfg.plugins)
        _register_builtins()

    def telemetry(self) -> Any:
        if self.cfg.otel_enabled or self.cfg.telemetry == "otel":
            factory = _TELEMETRY.get("otel") or OpenTelemetryProfileBridge
            return factory()
        factory = _TELEMETRY.get(self.cfg.telemetry) or _TELEMETRY["prometheus"]
        return factory()

    def exporter(self, *, telemetry: Any | None = None) -> Any:
        factory = _EXPORTERS.get(self.cfg.exporter)
        if factory is None:
            return build_exporter(
                self.cfg.exporter,
                self.cfg.work_dir,
                telemetry=telemetry,
                otel=self.cfg.otel_enabled,
            )
        try:
            return factory(
                self.cfg.work_dir,
                telemetry=telemetry,
                otel=self.cfg.otel_enabled,
            )
        except TypeError:
            return factory(self.cfg.work_dir)

    def dashboard(self) -> Any:
        factory = _DASHBOARDS.get(self.cfg.dashboard) or _DASHBOARDS["grafana"]
        return factory()

    def custom_profiler(self, name: str, **kwargs: Any) -> Any | None:
        factory = _PROFILERS.get(name)
        if factory is None:
            return None
        return factory(**kwargs)
