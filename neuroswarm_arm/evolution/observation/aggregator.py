"""Normalize and aggregate observations from multiple providers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterable

from neuroswarm_arm.evolution.interfaces.observation import ObservationProvider
from neuroswarm_arm.evolution.models.observation import (
    NormalizedObservation,
    ObservationSnapshot,
    RawObservation,
    TimeWindow,
)


def normalize(raw: RawObservation) -> NormalizedObservation:
    layer_hints: set[str] = set()
    src = raw.source.lower()
    if "ascr" in src or "cascade" in src:
        layer_hints.add("ascr")
    if "haoe" in src or "performix" in src or "pmu" in src:
        layer_hints.add("haoe")
    if "rtg" in src or "governor" in src:
        layer_hints.add("rtg")
    if "router" in src or "mcp" in src:
        layer_hints.add("router")
    if "maks" in src or "kv" in src:
        layer_hints.add("maks")
    for label_key, label_val in raw.labels.items():
        if label_key == "layer":
            layer_hints.add(label_val)
    return NormalizedObservation(
        event_id=str(uuid.uuid4()),
        source=raw.source,
        collected_at=raw.collected_at,
        metrics={k: float(v) for k, v in raw.metrics.items()},
        labels=dict(raw.labels),
        layer_hints=frozenset(layer_hints),
        raw_refs=(raw.source,),
    )


class MetricsAggregator:
    def __init__(self, providers: Iterable[ObservationProvider] | None = None) -> None:
        self.providers: list[ObservationProvider] = list(providers or [])

    def add(self, provider: ObservationProvider) -> None:
        self.providers.append(provider)

    def collect(self, window: TimeWindow | None = None) -> list[NormalizedObservation]:
        w = window or TimeWindow.last_seconds(300)
        out: list[NormalizedObservation] = []
        for provider in self.providers:
            try:
                for raw in provider.collect(w):
                    out.append(normalize(raw))
            except Exception:
                continue
        return out

    def snapshot(self) -> ObservationSnapshot:
        providers: dict[str, dict[str, float]] = {}
        aggregate: dict[str, float] = {}
        counts: dict[str, int] = {}
        for provider in self.providers:
            try:
                m = provider.metrics()
                providers[provider.name] = dict(m)
                for k, v in m.items():
                    aggregate[k] = aggregate.get(k, 0.0) + float(v)
                    counts[k] = counts.get(k, 0) + 1
            except Exception:
                providers[provider.name] = {}
        for k in list(aggregate):
            aggregate[k] = aggregate[k] / max(counts.get(k, 1), 1)
        return ObservationSnapshot(
            collected_at=datetime.now(timezone.utc),
            providers=providers,
            aggregate=aggregate,
        )

    def health(self) -> dict[str, object]:
        return {
            name: p.health()
            for p in self.providers
            for name in [p.name]
        }
