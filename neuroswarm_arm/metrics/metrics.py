"""Typed metric handles — subsystems use these, never prometheus_client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping

from .schemas import Exemplar, MetricDef, MetricType

if TYPE_CHECKING:
    from .registry import MetricRegistry


class CounterHandle:
    __slots__ = ("_registry", "definition")

    def __init__(self, registry: MetricRegistry, definition: MetricDef) -> None:
        self._registry = registry
        self.definition = definition

    def inc(self, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        self._registry.inc(self.definition.name, value, labels=labels)


class GaugeHandle:
    __slots__ = ("_registry", "definition")

    def __init__(self, registry: MetricRegistry, definition: MetricDef) -> None:
        self._registry = registry
        self.definition = definition

    def set(self, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        self._registry.set(self.definition.name, value, labels=labels)

    def inc(self, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        self._registry.inc(self.definition.name, value, labels=labels)


class HistogramHandle:
    __slots__ = ("_registry", "definition")

    def __init__(self, registry: MetricRegistry, definition: MetricDef) -> None:
        self._registry = registry
        self.definition = definition

    def observe(
        self,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
        exemplar: Exemplar | None = None,
    ) -> None:
        self._registry.observe(self.definition.name, value, labels=labels, exemplar=exemplar)


class SummaryHandle:
    __slots__ = ("_registry", "definition")

    def __init__(self, registry: MetricRegistry, definition: MetricDef) -> None:
        self._registry = registry
        self.definition = definition

    def observe(self, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        self._registry.observe(self.definition.name, value, labels=labels)


class InfoHandle:
    __slots__ = ("_registry", "definition")

    def __init__(self, registry: MetricRegistry, definition: MetricDef) -> None:
        self._registry = registry
        self.definition = definition

    def info(self, labels: Mapping[str, str]) -> None:
        self._registry.info(self.definition.name, labels)


class NativeHistogramHandle(HistogramHandle):
    """Native histogram handle — falls back to classic buckets in registry."""


class MetricPublisher:
    """Facade for domain code to publish without touching exporters."""

    def __init__(self, registry: MetricRegistry) -> None:
        self.registry = registry

    def counter(self, name: str) -> CounterHandle:
        definition = self.registry.get_def(name)
        if definition is None:
            definition = self.registry.ensure(name, MetricType.COUNTER, f"Counter {name}")
        return CounterHandle(self.registry, definition)

    def gauge(self, name: str) -> GaugeHandle:
        definition = self.registry.get_def(name)
        if definition is None:
            definition = self.registry.ensure(name, MetricType.GAUGE, f"Gauge {name}")
        return GaugeHandle(self.registry, definition)

    def histogram(self, name: str) -> HistogramHandle:
        definition = self.registry.get_def(name)
        if definition is None:
            definition = self.registry.ensure(name, MetricType.HISTOGRAM, f"Histogram {name}")
        return HistogramHandle(self.registry, definition)

    def summary(self, name: str) -> SummaryHandle:
        definition = self.registry.get_def(name)
        if definition is None:
            definition = self.registry.ensure(name, MetricType.SUMMARY, f"Summary {name}")
        return SummaryHandle(self.registry, definition)

    def info_metric(self, name: str) -> InfoHandle:
        definition = self.registry.get_def(name)
        if definition is None:
            definition = self.registry.ensure(name, MetricType.INFO, f"Info {name}")
        return InfoHandle(self.registry, definition)

    def inc(self, name: str, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        self.registry.inc(name, value, labels=labels)

    def set(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        self.registry.set(name, value, labels=labels)

    def observe(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
        exemplar: Exemplar | None = None,
    ) -> None:
        self.registry.observe(name, value, labels=labels, exemplar=exemplar)
