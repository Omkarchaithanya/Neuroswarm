"""Plugin registry for RCIS extensions."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Mapping

from .accounting import DefaultAccountingEngine
from .analyzer import DefaultCostAnalyzer
from .config import RCISRuntimeConfig
from .estimator import DefaultLiveCostEstimator
from .persistence import build_persistence
from .predictor import DefaultCostPredictor
from .telemetry import InMemoryCostTelemetry, OpenTelemetryCostBridge

logger = logging.getLogger(__name__)

_COST_MODELS: dict[str, Callable[..., Any]] = {}
_ENERGY_MODELS: dict[str, Callable[..., Any]] = {}
_PREDICTORS: dict[str, Callable[..., Any]] = {}
_ACCOUNTING: dict[str, Callable[..., Any]] = {}
_STORAGE: dict[str, Callable[..., Any]] = {}
_TELEMETRY: dict[str, Callable[..., Any]] = {}
_DASHBOARDS: dict[str, Callable[..., Any]] = {}


def register_cost_model(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _COST_MODELS[name] = fn
        return fn

    return deco


def register_energy_model(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _ENERGY_MODELS[name] = fn
        return fn

    return deco


def register_predictor(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _PREDICTORS[name] = fn
        return fn

    return deco


def register_accounting(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _ACCOUNTING[name] = fn
        return fn

    return deco


def register_storage(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _STORAGE[name] = fn
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
            logger.warning("rcis plugin import failed for %s: %s", path, exc)


class GrafanaDashboardProvider:
    def name(self) -> str:
        return "grafana"

    def panels(self) -> list[Mapping[str, Any]]:
        return [
            {"title": "Live Cost", "expr": "runtime_cost_total"},
            {"title": "Cost per Token", "expr": "runtime_cost_per_token"},
            {"title": "CPU Seconds", "expr": "runtime_cpu_seconds"},
            {"title": "Memory Bytes", "expr": "runtime_memory_bytes"},
            {"title": "Energy Estimate", "expr": "runtime_energy_estimate"},
            {"title": "KV Reuse", "expr": "runtime_kv_reuse"},
            {"title": "Spec Acceptance", "expr": "runtime_spec_acceptance"},
            {"title": "Planner Prediction Error", "expr": "runtime_planner_prediction_error"},
            {"title": "Tokens per Dollar", "expr": "runtime_tokens_per_dollar"},
            {"title": "Tokens per Watt", "expr": "runtime_tokens_per_watt"},
        ]


def _register_builtins() -> None:
    if "default" not in _COST_MODELS:
        _COST_MODELS["default"] = DefaultLiveCostEstimator
    if "default" not in _ENERGY_MODELS:
        # Energy is folded into DefaultLiveCostEstimator; keep alias for plugins
        _ENERGY_MODELS["default"] = DefaultLiveCostEstimator
    if "default" not in _PREDICTORS:
        _PREDICTORS["default"] = DefaultCostPredictor
    if "default" not in _ACCOUNTING:
        _ACCOUNTING["default"] = DefaultAccountingEngine
    if "prometheus" not in _TELEMETRY:
        _TELEMETRY["prometheus"] = InMemoryCostTelemetry
    if "otel" not in _TELEMETRY:
        _TELEMETRY["otel"] = OpenTelemetryCostBridge
    if "grafana" not in _DASHBOARDS:
        _DASHBOARDS["grafana"] = GrafanaDashboardProvider
    for name in ("sqlite", "json", "jsonl", "duckdb", "postgres", "parquet"):
        if name not in _STORAGE:
            _STORAGE[name] = lambda root, n=name, **kw: build_persistence(n, root, **kw)


_register_builtins()


class RCISPluginRegistry:
    def __init__(self, cfg: RCISRuntimeConfig) -> None:
        self.cfg = cfg
        discover_plugins(cfg.plugins)
        _register_builtins()

    def cost_model(self) -> Any:
        factory = _COST_MODELS.get(self.cfg.cost_model) or _COST_MODELS["default"]
        return factory(self.cfg)

    def energy_model(self) -> Any:
        factory = _ENERGY_MODELS.get(self.cfg.energy_model) or _ENERGY_MODELS["default"]
        return factory(self.cfg)

    def predictor(self, *, history_provider: Any | None = None) -> Any:
        factory = _PREDICTORS.get(self.cfg.predictor) or _PREDICTORS["default"]
        try:
            return factory(self.cfg, history_provider=history_provider)
        except TypeError:
            return factory(self.cfg)

    def accounting(self) -> Any:
        factory = _ACCOUNTING.get(self.cfg.accounting) or _ACCOUNTING["default"]
        return factory()

    def persistence(self) -> Any:
        factory = _STORAGE.get(self.cfg.persistence)
        if factory is None:
            return build_persistence(self.cfg.persistence, self.cfg.work_dir)
        try:
            return factory(self.cfg.work_dir)
        except TypeError:
            return factory(root=self.cfg.work_dir)

    def telemetry(self) -> Any:
        factory = _TELEMETRY.get(self.cfg.telemetry) or _TELEMETRY["prometheus"]
        return factory()

    def dashboard(self) -> Any:
        factory = _DASHBOARDS.get(self.cfg.dashboard) or _DASHBOARDS["grafana"]
        return factory()

    def analyzer(self) -> DefaultCostAnalyzer:
        return DefaultCostAnalyzer()
