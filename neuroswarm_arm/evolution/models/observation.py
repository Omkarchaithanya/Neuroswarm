"""Observation / episode / reward models for AROP."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: datetime
    end: datetime

    @classmethod
    def last_seconds(cls, seconds: float) -> TimeWindow:
        end = _utcnow()
        from datetime import timedelta

        return cls(start=end - timedelta(seconds=seconds), end=end)


@dataclass(frozen=True, slots=True)
class HealthStatus:
    healthy: bool
    provider: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RawObservation:
    source: str
    collected_at: datetime
    metrics: Mapping[str, float]
    labels: Mapping[str, str] = field(default_factory=dict)
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizedObservation:
    """Canonical observation after provider-agnostic normalization."""

    event_id: str
    source: str
    collected_at: datetime
    metrics: Mapping[str, float]
    labels: Mapping[str, str] = field(default_factory=dict)
    layer_hints: frozenset[str] = field(default_factory=frozenset)
    raw_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ObservationSnapshot:
    collected_at: datetime
    providers: Mapping[str, Mapping[str, float]]
    aggregate: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ObservationSummary:
    window: TimeWindow
    n_events: int
    means: Mapping[str, float]
    highlights: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Reward:
    """Multi-objective reward; scalar used by bandits."""

    latency_ms: float = 0.0
    ttft_ms: float = 0.0
    tps: float = 0.0
    cost_usd: float = 0.0
    accept_rate: float = 0.0
    quality: float = 0.0
    tool_success: float = 0.0
    energy_joules: float = 0.0
    kv_pressure: float = 0.0
    cpu_util: float = 0.0
    scalar: float = 0.0

    @staticmethod
    def scalarize(
        *,
        latency_ms: float = 0.0,
        ttft_ms: float = 0.0,
        tps: float = 0.0,
        cost_usd: float = 0.0,
        accept_rate: float = 0.0,
        quality: float = 0.0,
        tool_success: float = 0.0,
        energy_joules: float = 0.0,
        kv_pressure: float = 0.0,
        cpu_util: float = 0.0,
    ) -> Reward:
        # Higher is better. Penalize latency/cost/pressure/energy.
        scalar = (
            0.25 * accept_rate
            + 0.20 * quality
            + 0.15 * tool_success
            + 0.10 * min(tps / 100.0, 1.0)
            - 0.15 * min(latency_ms / 5000.0, 1.0)
            - 0.05 * min(ttft_ms / 2000.0, 1.0)
            - 0.10 * min(cost_usd / 0.05, 1.0)
            - 0.05 * kv_pressure
            - 0.03 * cpu_util
            - 0.02 * min(energy_joules / 100.0, 1.0)
        )
        return Reward(
            latency_ms=latency_ms,
            ttft_ms=ttft_ms,
            tps=tps,
            cost_usd=cost_usd,
            accept_rate=accept_rate,
            quality=quality,
            tool_success=tool_success,
            energy_joules=energy_joules,
            kv_pressure=kv_pressure,
            cpu_util=cpu_util,
            scalar=float(scalar),
        )


@dataclass(frozen=True, slots=True)
class Outcome:
    success: bool
    reward: Reward
    metrics: Mapping[str, float] = field(default_factory=dict)
    notes: str = ""


@dataclass(frozen=True, slots=True)
class Episode:
    episode_id: str
    started_at: datetime
    ended_at: datetime | None
    policy_id: str | None
    policy_version: str | None
    observations: tuple[NormalizedObservation, ...]
    outcome: Outcome | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
