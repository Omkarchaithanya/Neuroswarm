"""Exporter protocol and factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..registry import MetricRegistry


@runtime_checkable
class MetricExporter(Protocol):
    def export(self) -> str: ...

    def content_type(self) -> str: ...


def build_exporter(name: str, registry: MetricRegistry, **kwargs: object) -> MetricExporter:
    from ..plugins import plugin_registry, _register_builtins

    _register_builtins()
    factory = plugin_registry.exporter(name)
    if factory is None:
        raise KeyError(f"unknown RMF exporter: {name}")
    return factory(registry, **kwargs)  # type: ignore[call-arg]
