"""Plugin registry for ROF extensions."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

from .config import ROFRuntimeConfig

logger = logging.getLogger(__name__)

_EXPORTERS: dict[str, Callable[..., Any]] = {}
_SAMPLERS: dict[str, Callable[..., Any]] = {}
_METRIC_SOURCES: dict[str, Callable[..., Any]] = {}
_LOG_SINKS: dict[str, Callable[..., Any]] = {}
_TRACE_PROCESSORS: dict[str, Callable[..., Any]] = {}
_DASHBOARD_PROVIDERS: dict[str, Callable[..., Any]] = {}
_EVENT_TYPES: dict[str, str] = {}


def register_exporter(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _EXPORTERS[name] = fn
        return fn

    return deco


def register_sampler(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _SAMPLERS[name] = fn
        return fn

    return deco


def register_metric_source(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _METRIC_SOURCES[name] = fn
        return fn

    return deco


def register_log_sink(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _LOG_SINKS[name] = fn
        return fn

    return deco


def register_trace_processor(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _TRACE_PROCESSORS[name] = fn
        return fn

    return deco


def register_dashboard_provider(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _DASHBOARD_PROVIDERS[name] = fn
        return fn

    return deco


def register_event_type(name: str, canonical: str | None = None) -> str:
    key = name.strip()
    _EVENT_TYPES[key] = canonical or key
    return _EVENT_TYPES[key]


def discover_plugins(module_paths: tuple[str, ...] | list[str]) -> None:
    for path in module_paths:
        try:
            importlib.import_module(path)
        except Exception as exc:
            logger.warning("rof plugin import failed for %s: %s", path, exc)


def _register_builtins() -> None:
    if "always_on" not in _SAMPLERS:
        from .sampling import (
            AdaptiveSampler,
            AlwaysOffSampler,
            AlwaysOnSampler,
            DynamicSampler,
            HeadRatioSampler,
            TailSampler,
        )

        @register_sampler("always_on")
        def _always_on(**_kw: Any) -> AlwaysOnSampler:
            return AlwaysOnSampler()

        @register_sampler("always_off")
        def _always_off(**_kw: Any) -> AlwaysOffSampler:
            return AlwaysOffSampler()

        @register_sampler("head")
        def _head(config: ROFRuntimeConfig | None = None, **_kw: Any) -> HeadRatioSampler:
            ratio = config.head_ratio if config else 0.1
            return HeadRatioSampler(ratio)

        @register_sampler("tail")
        def _tail(config: ROFRuntimeConfig | None = None, **_kw: Any) -> TailSampler:
            thr = config.tail_latency_ms_threshold if config else 1500.0
            return TailSampler(thr)

        @register_sampler("adaptive")
        def _adaptive(config: ROFRuntimeConfig | None = None, **_kw: Any) -> AdaptiveSampler:
            if config is None:
                return AdaptiveSampler()
            return AdaptiveSampler(
                base_ratio=config.head_ratio,
                error_rate_threshold=config.adaptive_error_rate_threshold,
                latency_ms_threshold=config.adaptive_latency_ms_threshold,
            )

        @register_sampler("dynamic")
        def _dynamic(config: ROFRuntimeConfig | None = None, **_kw: Any) -> DynamicSampler:
            from .config import load_rof_config

            return DynamicSampler(config or load_rof_config())

    # Exporters registered lazily from exporters package
    from .exporters import register_builtin_exporters

    register_builtin_exporters()


class ROFPluginRegistry:
    """Resolve plugin factories by config string."""

    def __init__(self, config: ROFRuntimeConfig) -> None:
        self.config = config
        _register_builtins()
        if config.plugins:
            discover_plugins(config.plugins)

    def build_sampler(self) -> Any:
        factory = _SAMPLERS.get(self.config.sampler) or _SAMPLERS.get("always_on")
        assert factory is not None
        return factory(config=self.config)

    def build_exporters(self) -> list[Any]:
        out: list[Any] = []
        for name in self.config.exporters:
            factory = _EXPORTERS.get(name)
            if factory is None:
                logger.warning("unknown ROF exporter %s", name)
                continue
            try:
                out.append(factory(config=self.config))
            except Exception as exc:
                logger.warning("ROF exporter %s failed to build: %s", name, exc)
        return out

    def metric_source_factories(self) -> dict[str, Callable[..., Any]]:
        return dict(_METRIC_SOURCES)

    def dashboard_providers(self) -> dict[str, Callable[..., Any]]:
        return dict(_DASHBOARD_PROVIDERS)

    def known_event_types(self) -> dict[str, str]:
        return dict(_EVENT_TYPES)
