"""Plugin registry for Budget Envelope extensions."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

from .config import BudgetRuntimeConfig
from .estimator import DefaultCostModel, DefaultEnergyModel, DefaultEstimator
from .persistence import build_persistence
from .policy import DefaultPolicyCompiler
from .telemetry import InMemoryTelemetry, OpenTelemetryBudgetBridge

logger = logging.getLogger(__name__)

_COST_MODELS: dict[str, Callable[..., Any]] = {}
_ENERGY_MODELS: dict[str, Callable[..., Any]] = {}
_ESTIMATORS: dict[str, Callable[..., Any]] = {}
_PERSISTENCE: dict[str, Callable[..., Any]] = {}
_POLICY: dict[str, Callable[..., Any]] = {}
_TELEMETRY: dict[str, Callable[..., Any]] = {}
_DIMENSIONS: dict[str, Any] = {}
_ACCOUNTING: dict[str, Callable[..., Any]] = {}


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


def register_estimator(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _ESTIMATORS[name] = fn
        return fn

    return deco


def register_persistence(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _PERSISTENCE[name] = fn
        return fn

    return deco


def register_policy_compiler(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _POLICY[name] = fn
        return fn

    return deco


def register_telemetry(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _TELEMETRY[name] = fn
        return fn

    return deco


def register_dimension(name: str) -> Callable[[Any], Any]:
    def deco(obj: Any) -> Any:
        _DIMENSIONS[name] = obj
        return obj

    return deco


def register_accounting(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _ACCOUNTING[name] = fn
        return fn

    return deco


def discover_plugins(module_paths: tuple[str, ...] | list[str]) -> None:
    for path in module_paths:
        try:
            importlib.import_module(path)
        except Exception as exc:
            logger.warning("budget plugin import failed for %s: %s", path, exc)


def _register_builtins() -> None:
    if "default" not in _COST_MODELS:
        _COST_MODELS["default"] = DefaultCostModel
    if "default" not in _ENERGY_MODELS:
        _ENERGY_MODELS["default"] = DefaultEnergyModel
    if "default" not in _ESTIMATORS:
        _ESTIMATORS["default"] = DefaultEstimator
    if "default" not in _POLICY:
        _POLICY["default"] = DefaultPolicyCompiler
    if "prometheus" not in _TELEMETRY:
        _TELEMETRY["prometheus"] = InMemoryTelemetry
    if "otel" not in _TELEMETRY:
        _TELEMETRY["otel"] = OpenTelemetryBudgetBridge
    for name in ("sqlite", "json", "jsonl", "duckdb", "postgres", "parquet"):
        if name not in _PERSISTENCE:
            _PERSISTENCE[name] = lambda root, n=name, **kw: build_persistence(n, root, **kw)


_register_builtins()


class BudgetPluginRegistry:
    def __init__(self, cfg: BudgetRuntimeConfig) -> None:
        self.cfg = cfg
        discover_plugins(cfg.plugins)
        _register_builtins()

    def cost_model(self) -> Any:
        factory = _COST_MODELS.get(self.cfg.cost_model) or _COST_MODELS["default"]
        return factory(self.cfg)

    def energy_model(self) -> Any:
        factory = _ENERGY_MODELS.get(self.cfg.energy_model) or _ENERGY_MODELS["default"]
        return factory(self.cfg)

    def estimator(self, *, cost_model: Any | None = None, energy_model: Any | None = None) -> Any:
        factory = _ESTIMATORS.get(self.cfg.estimator) or _ESTIMATORS["default"]
        return factory(self.cfg, cost_model=cost_model, energy_model=energy_model)

    def persistence(self) -> Any:
        factory = _PERSISTENCE.get(self.cfg.persistence)
        if factory is None:
            return build_persistence(self.cfg.persistence, self.cfg.work_dir)
        try:
            return factory(self.cfg.work_dir)
        except TypeError:
            return factory(root=self.cfg.work_dir)

    def policy_compiler(self, *, okf_root: Any = None) -> Any:
        factory = _POLICY.get(self.cfg.policy_compiler) or _POLICY["default"]
        try:
            return factory(self.cfg, okf_root=okf_root)
        except TypeError:
            return factory(self.cfg)

    def telemetry(self) -> Any:
        factory = _TELEMETRY.get(self.cfg.telemetry) or _TELEMETRY["prometheus"]
        return factory()

    def dimensions(self) -> dict[str, Any]:
        return dict(_DIMENSIONS)
