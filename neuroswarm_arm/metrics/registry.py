"""Central MetricRegistry — sole registration authority for RMF."""

from __future__ import annotations

import math
import threading
from collections import defaultdict
from typing import Mapping

from .labels import LabelPolicy
from .schemas import (
    Exemplar,
    MetricDef,
    MetricDomain,
    MetricType,
    RegistrySnapshot,
    SeriesSnapshot,
)


class _CounterSeries:
    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = 0.0

    def inc(self, amount: float) -> None:
        self.value += float(amount)


class _GaugeSeries:
    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = 0.0

    def set(self, amount: float) -> None:
        self.value = float(amount)

    def inc(self, amount: float) -> None:
        self.value += float(amount)


class _HistogramSeries:
    __slots__ = ("buckets", "counts", "sum", "count", "exemplar")

    def __init__(self, buckets: tuple[float, ...]) -> None:
        self.buckets = buckets
        self.counts = [0.0] * len(buckets)
        self.sum = 0.0
        self.count = 0.0
        self.exemplar: Exemplar | None = None

    def observe(self, value: float, exemplar: Exemplar | None = None) -> None:
        v = float(value)
        self.sum += v
        self.count += 1.0
        for i, bound in enumerate(self.buckets):
            if v <= bound:
                self.counts[i] += 1.0
        if exemplar is not None:
            self.exemplar = exemplar


class _SummarySeries:
    __slots__ = ("values", "sum", "count", "max_samples")

    def __init__(self, max_samples: int = 512) -> None:
        self.values: list[float] = []
        self.sum = 0.0
        self.count = 0.0
        self.max_samples = max_samples

    def observe(self, value: float) -> None:
        v = float(value)
        self.sum += v
        self.count += 1.0
        self.values.append(v)
        if len(self.values) > self.max_samples:
            del self.values[: self.max_samples // 2]

    def quantiles(self, objectives: Mapping[float, float]) -> dict[str, float]:
        if not self.values:
            return {str(q): 0.0 for q in objectives}
        ordered = sorted(self.values)
        out: dict[str, float] = {}
        n = len(ordered)
        for q in objectives:
            idx = min(n - 1, max(0, int(math.ceil(q * n) - 1)))
            out[str(q)] = ordered[idx]
        return out


class _InfoSeries:
    __slots__ = ("labels",)

    def __init__(self) -> None:
        self.labels: dict[str, str] = {}

    def set_info(self, labels: Mapping[str, str]) -> None:
        self.labels = {str(k): str(v) for k, v in labels.items()}


class MetricRegistry:
    """Thread-safe registry of metric definitions and series samples."""

    def __init__(self, *, cardinality_max: int = 2048) -> None:
        self._lock = threading.RLock()
        self.policy = LabelPolicy(max_series_per_metric=cardinality_max)
        self._defs: dict[str, MetricDef] = {}
        self._aliases: dict[str, str] = {}
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], _CounterSeries]] = {}
        self._gauges: dict[str, dict[tuple[tuple[str, str], ...], _GaugeSeries]] = {}
        self._histograms: dict[str, dict[tuple[tuple[str, str], ...], _HistogramSeries]] = {}
        self._summaries: dict[str, dict[tuple[tuple[str, str], ...], _SummarySeries]] = {}
        self._infos: dict[str, _InfoSeries] = {}
        self._buffer_drops = 0
        self._shard_locks = [threading.Lock() for _ in range(16)]

    def _shard(self, name: str) -> threading.Lock:
        return self._shard_locks[hash(name) & 15]

    def register(self, definition: MetricDef) -> MetricDef:
        with self._lock:
            existing = self._defs.get(definition.name)
            if existing is not None:
                if existing.metric_type != definition.metric_type:
                    raise ValueError(
                        f"metric {definition.name} already registered as {existing.metric_type}"
                    )
                return existing
            self._defs[definition.name] = definition
            for alias in definition.aliases:
                self._aliases[alias] = definition.name
            if definition.metric_type == MetricType.COUNTER:
                self._counters[definition.name] = {}
            elif definition.metric_type == MetricType.GAUGE:
                self._gauges[definition.name] = {}
            elif definition.metric_type in (MetricType.HISTOGRAM, MetricType.NATIVE_HISTOGRAM):
                self._histograms[definition.name] = {}
            elif definition.metric_type == MetricType.SUMMARY:
                self._summaries[definition.name] = {}
            elif definition.metric_type == MetricType.INFO:
                self._infos[definition.name] = _InfoSeries()
            return definition

    def resolve_name(self, name: str) -> str:
        return self._aliases.get(name, name)

    def get_def(self, name: str) -> MetricDef | None:
        canonical = self.resolve_name(name)
        return self._defs.get(canonical)

    def ensure(
        self,
        name: str,
        metric_type: MetricType | str,
        help_text: str,
        *,
        domain: MetricDomain = MetricDomain.LEGACY,
        label_keys: tuple[str, ...] = (),
        buckets: tuple[float, ...] = (),
        aliases: tuple[str, ...] = (),
    ) -> MetricDef:
        mtype = MetricType(metric_type) if isinstance(metric_type, str) else metric_type
        return self.register(
            MetricDef(
                name=name,
                metric_type=mtype,
                help=help_text,
                domain=domain,
                label_keys=label_keys,
                buckets=buckets,
                aliases=aliases,
            )
        )

    def _normalize(
        self, name: str, labels: Mapping[str, str] | None
    ) -> tuple[str, dict[str, str], MetricDef | None]:
        canonical = self.resolve_name(name)
        definition = self._defs.get(canonical)
        allowed = definition.label_keys if definition is not None else None
        safe = self.policy.normalize(labels, allowed_keys=allowed)
        if not self.policy.admit_series(canonical, safe):
            return canonical, {}, None
        return canonical, safe, definition

    def inc(self, name: str, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        canonical, safe, definition = self._normalize(name, labels)
        if definition is None and canonical not in self._defs:
            self.ensure(canonical, MetricType.COUNTER, f"Auto-registered counter {canonical}")
            definition = self._defs[canonical]
        if definition is None:
            return
        key = tuple(sorted(safe.items()))
        with self._shard(canonical):
            if definition.metric_type == MetricType.GAUGE:
                series_map = self._gauges.setdefault(canonical, {})
                series = series_map.get(key)
                if series is None:
                    series = _GaugeSeries()
                    series_map[key] = series
                series.inc(value)
            else:
                series_map = self._counters.setdefault(canonical, {})
                series = series_map.get(key)
                if series is None:
                    series = _CounterSeries()
                    series_map[key] = series
                series.inc(value)

    def set(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        canonical, safe, definition = self._normalize(name, labels)
        if definition is None and canonical not in self._defs:
            self.ensure(canonical, MetricType.GAUGE, f"Auto-registered gauge {canonical}")
            definition = self._defs[canonical]
        if definition is None:
            return
        key = tuple(sorted(safe.items()))
        with self._shard(canonical):
            series_map = self._gauges.setdefault(canonical, {})
            series = series_map.get(key)
            if series is None:
                series = _GaugeSeries()
                series_map[key] = series
            series.set(value)

    def observe(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
        exemplar: Exemplar | None = None,
    ) -> None:
        canonical, safe, definition = self._normalize(name, labels)
        if definition is None and canonical not in self._defs:
            self.ensure(
                canonical,
                MetricType.HISTOGRAM,
                f"Auto-registered histogram {canonical}",
                buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            )
            definition = self._defs[canonical]
        if definition is None:
            return
        key = tuple(sorted(safe.items()))
        with self._shard(canonical):
            if definition.metric_type == MetricType.SUMMARY:
                series_map = self._summaries.setdefault(canonical, {})
                series = series_map.get(key)
                if series is None:
                    series = _SummarySeries()
                    series_map[key] = series
                series.observe(value)
            else:
                buckets = definition.buckets or (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
                series_map = self._histograms.setdefault(canonical, {})
                series = series_map.get(key)
                if series is None:
                    series = _HistogramSeries(buckets)
                    series_map[key] = series
                series.observe(value, exemplar=exemplar)

    def info(self, name: str, labels: Mapping[str, str]) -> None:
        canonical = self.resolve_name(name)
        with self._lock:
            if canonical not in self._defs:
                self.ensure(canonical, MetricType.INFO, f"Info metric {canonical}")
            series = self._infos.setdefault(canonical, _InfoSeries())
            series.set_info(self.policy.normalize(labels))

    def record_drop(self) -> None:
        self._buffer_drops += 1
        self.inc("nexus_rmf_buffer_drops_total", 1.0)

    def definitions(self) -> tuple[MetricDef, ...]:
        with self._lock:
            return tuple(self._defs[name] for name in sorted(self._defs))

    def definitions_by_domain(self, domain: MetricDomain) -> tuple[MetricDef, ...]:
        return tuple(d for d in self.definitions() if d.domain == domain)

    def snapshot(self) -> RegistrySnapshot:
        series: list[SeriesSnapshot] = []
        with self._lock:
            for name, by_labels in self._counters.items():
                definition = self._defs[name]
                for key, sample in by_labels.items():
                    series.append(
                        SeriesSnapshot(
                            name=name,
                            metric_type=MetricType.COUNTER,
                            help=definition.help,
                            labels=dict(key),
                            value=sample.value,
                        )
                    )
            for name, by_labels in self._gauges.items():
                definition = self._defs[name]
                for key, sample in by_labels.items():
                    series.append(
                        SeriesSnapshot(
                            name=name,
                            metric_type=MetricType.GAUGE,
                            help=definition.help,
                            labels=dict(key),
                            value=sample.value,
                        )
                    )
            for name, by_labels in self._histograms.items():
                definition = self._defs[name]
                for key, sample in by_labels.items():
                    bucket_counts = {
                        str(bound): count for bound, count in zip(sample.buckets, sample.counts, strict=False)
                    }
                    # cumulative for Prometheus
                    cumulative = 0.0
                    cum_map: dict[str, float] = {}
                    for bound, count in zip(sample.buckets, sample.counts, strict=False):
                        cumulative += count
                        cum_map[str(bound)] = cumulative
                    series.append(
                        SeriesSnapshot(
                            name=name,
                            metric_type=definition.metric_type,
                            help=definition.help,
                            labels=dict(key),
                            value=sample.sum,
                            bucket_counts=cum_map,
                            sum=sample.sum,
                            count=sample.count,
                            exemplar=sample.exemplar,
                        )
                    )
            for name, by_labels in self._summaries.items():
                definition = self._defs[name]
                for key, sample in by_labels.items():
                    series.append(
                        SeriesSnapshot(
                            name=name,
                            metric_type=MetricType.SUMMARY,
                            help=definition.help,
                            labels=dict(key),
                            value=sample.sum,
                            sum=sample.sum,
                            count=sample.count,
                            quantiles=sample.quantiles(definition.objectives or {0.5: 0.05, 0.9: 0.01, 0.99: 0.001}),
                        )
                    )
            for name, sample in self._infos.items():
                definition = self._defs[name]
                series.append(
                    SeriesSnapshot(
                        name=name,
                        metric_type=MetricType.INFO,
                        help=definition.help,
                        labels=dict(sample.labels),
                        value=1.0,
                        info=dict(sample.labels),
                    )
                )
        return RegistrySnapshot(
            series=tuple(series),
            dropped_labels=self.policy.dropped_labels,
            cardinality_rejects=self.policy.cardinality_rejects,
            buffer_drops=self._buffer_drops,
        )

    def aggregate_values(self) -> dict[str, float]:
        """Flat name→value map for AROP / feedback consumers."""
        out: dict[str, float] = defaultdict(float)
        snap = self.snapshot()
        for item in snap.series:
            if item.metric_type in (MetricType.HISTOGRAM, MetricType.NATIVE_HISTOGRAM, MetricType.SUMMARY):
                out[f"{item.name}_sum"] += item.sum
                out[f"{item.name}_count"] += item.count
            else:
                label_suffix = ""
                if item.labels:
                    parts = [f'{k}="{v}"' for k, v in sorted(item.labels.items())]
                    label_suffix = "{" + ",".join(parts) + "}"
                out[f"{item.name}{label_suffix}"] = item.value
        out["nexus_rmf_label_drops_total"] = float(snap.dropped_labels)
        out["nexus_rmf_cardinality_rejects_total"] = float(snap.cardinality_rejects)
        return dict(out)
