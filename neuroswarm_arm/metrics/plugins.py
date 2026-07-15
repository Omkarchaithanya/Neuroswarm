"""Plugin registry for RMF providers, exporters, collectors, aggregators, alerts, dashboards."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, Callable[..., Any]] = {}
_EXPORTERS: dict[str, Callable[..., Any]] = {}
_COLLECTORS: dict[str, Callable[..., Any]] = {}
_AGGREGATORS: dict[str, Callable[..., Any]] = {}
_ALERT_RULES: dict[str, Callable[..., Any]] = {}
_DASHBOARDS: dict[str, Callable[..., Any]] = {}


def register_provider(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _PROVIDERS[name] = fn
        return fn

    return deco


def register_exporter(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _EXPORTERS[name] = fn
        return fn

    return deco


def register_collector(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _COLLECTORS[name] = fn
        return fn

    return deco


def register_aggregator(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _AGGREGATORS[name] = fn
        return fn

    return deco


def register_alert_rules(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _ALERT_RULES[name] = fn
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
            logger.warning("rmf plugin import failed for %s: %s", path, exc)


class RMFPluginRegistry:
    def provider(self, name: str) -> Callable[..., Any] | None:
        return _PROVIDERS.get(name)

    def exporter(self, name: str) -> Callable[..., Any] | None:
        return _EXPORTERS.get(name)

    def collector(self, name: str) -> Callable[..., Any] | None:
        return _COLLECTORS.get(name)

    def aggregator(self, name: str) -> Callable[..., Any] | None:
        return _AGGREGATORS.get(name)

    def alert_rules(self, name: str) -> Callable[..., Any] | None:
        return _ALERT_RULES.get(name)

    def dashboard(self, name: str) -> Callable[..., Any] | None:
        return _DASHBOARDS.get(name)

    def list_exporters(self) -> tuple[str, ...]:
        return tuple(sorted(_EXPORTERS))

    def list_collectors(self) -> tuple[str, ...]:
        return tuple(sorted(_COLLECTORS))

    def list_dashboards(self) -> tuple[str, ...]:
        return tuple(sorted(_DASHBOARDS))


def _register_builtins() -> None:
    if "prometheus" not in _EXPORTERS:
        from .exporters.prometheus import PrometheusExporter

        _EXPORTERS["prometheus"] = PrometheusExporter
    if "openmetrics" not in _EXPORTERS:
        from .exporters.openmetrics import OpenMetricsExporter

        _EXPORTERS["openmetrics"] = OpenMetricsExporter
    if "otlp" not in _EXPORTERS:
        from .exporters.otlp import OTLPMetricsExporter

        _EXPORTERS["otlp"] = OTLPMetricsExporter
    if "psutil" not in _COLLECTORS:
        from .collectors import PsutilCollector

        _COLLECTORS["psutil"] = PsutilCollector
    if "performix" not in _COLLECTORS:
        from .collectors import PerformixCollector

        _COLLECTORS["performix"] = PerformixCollector
    if "window" not in _AGGREGATORS:
        from .aggregators import WindowAggregator

        _AGGREGATORS["window"] = WindowAggregator
    if "default" not in _ALERT_RULES:
        from .alerts import default_alert_groups

        _ALERT_RULES["default"] = default_alert_groups
    if "default" not in _DASHBOARDS:
        from .dashboards import default_dashboards

        _DASHBOARDS["default"] = default_dashboards


plugin_registry = RMFPluginRegistry()
