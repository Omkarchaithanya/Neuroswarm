"""Rollback Manager operational metrics (RMF / OTel ready)."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class RollbackMetrics:
    """Counters for rollback-manager operations — not execution telemetry."""

    rollback_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    cancelled_count: int = 0
    validation_failures: int = 0
    consistency_violations: int = 0
    policy_evaluations: int = 0
    policy_triggers: int = 0
    duration_ms_total: float = 0.0
    recovery_latency_ms_total: float = 0.0
    strategy_usage: dict[str, int] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def incr(self, name: str, amount: int | float = 1) -> None:
        with self._lock:
            if name == "strategy_usage":
                raise AttributeError("use record_strategy()")
            if not hasattr(self, name):
                raise AttributeError(name)
            setattr(self, name, getattr(self, name) + amount)

    def record_strategy(self, strategy: str) -> None:
        with self._lock:
            self.strategy_usage[strategy] = self.strategy_usage.get(strategy, 0) + 1

    def record_duration(self, duration_ms: float) -> None:
        with self._lock:
            self.duration_ms_total += max(0.0, duration_ms)

    def record_recovery_latency(self, latency_ms: float) -> None:
        with self._lock:
            self.recovery_latency_ms_total += max(0.0, latency_ms)

    def success_rate(self) -> float:
        with self._lock:
            total = self.success_count + self.failure_count
            if total == 0:
                return 0.0
            return self.success_count / total

    def failure_rate(self) -> float:
        with self._lock:
            total = self.success_count + self.failure_count
            if total == 0:
                return 0.0
            return self.failure_count / total

    def snapshot(self) -> dict[str, int | float | dict[str, int]]:
        with self._lock:
            return {
                "rollback_count": self.rollback_count,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "cancelled_count": self.cancelled_count,
                "validation_failures": self.validation_failures,
                "consistency_violations": self.consistency_violations,
                "policy_evaluations": self.policy_evaluations,
                "policy_triggers": self.policy_triggers,
                "duration_ms_total": self.duration_ms_total,
                "recovery_latency_ms_total": self.recovery_latency_ms_total,
                "success_rate": (
                    self.success_count / (self.success_count + self.failure_count)
                    if (self.success_count + self.failure_count)
                    else 0.0
                ),
                "failure_rate": (
                    self.failure_count / (self.success_count + self.failure_count)
                    if (self.success_count + self.failure_count)
                    else 0.0
                ),
                "strategy_usage": dict(self.strategy_usage),
            }

    def to_otel_attributes(self) -> dict[str, Any]:
        snap = self.snapshot()
        attrs: dict[str, Any] = {}
        for k, v in snap.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    attrs[f"nexus.swarm.rollback.metric.{k}.{sk}"] = sv
            else:
                attrs[f"nexus.swarm.rollback.metric.{k}"] = v
        return attrs

    def reset(self) -> None:
        with self._lock:
            self.rollback_count = 0
            self.success_count = 0
            self.failure_count = 0
            self.cancelled_count = 0
            self.validation_failures = 0
            self.consistency_violations = 0
            self.policy_evaluations = 0
            self.policy_triggers = 0
            self.duration_ms_total = 0.0
            self.recovery_latency_ms_total = 0.0
            self.strategy_usage.clear()
