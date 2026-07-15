"""RMRE operational metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class ResilienceMetrics:
    """Counters / gauges for resilience decisions — not inference telemetry."""

    fallback_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    continue_count: int = 0
    degrade_notify_count: int = 0
    candidate_count: int = 0
    policy_match_count: int = 0
    health_evaluations: int = 0
    quality_delta_total: float = 0.0
    latency_delta_total: float = 0.0
    cost_delta_total: float = 0.0
    backend_transitions: int = 0
    quantization_transitions: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def incr(self, name: str, amount: int | float = 1) -> None:
        with self._lock:
            if not hasattr(self, name):
                raise AttributeError(name)
            setattr(self, name, getattr(self, name) + amount)

    def record_fallback(
        self,
        *,
        success: bool,
        quality_delta: float = 0.0,
        latency_delta: float = 0.0,
        cost_delta: float = 0.0,
        backend_changed: bool = False,
        quant_changed: bool = False,
    ) -> None:
        with self._lock:
            self.fallback_count += 1
            if success:
                self.success_count += 1
            else:
                self.failure_count += 1
            self.quality_delta_total += quality_delta
            self.latency_delta_total += latency_delta
            self.cost_delta_total += cost_delta
            if backend_changed:
                self.backend_transitions += 1
            if quant_changed:
                self.quantization_transitions += 1

    @property
    def success_rate(self) -> float:
        snap = self.snapshot()
        total = int(snap["success_count"]) + int(snap["failure_count"])
        if total == 0:
            return 0.0
        return float(snap["success_count"]) / total

    @property
    def average_degradation(self) -> float:
        snap = self.snapshot()
        n = int(snap["fallback_count"])
        if n == 0:
            return 0.0
        return float(snap["quality_delta_total"]) / n

    @property
    def latency_improvement(self) -> float:
        """Negative latency_delta means faster — report as positive improvement."""
        snap = self.snapshot()
        n = int(snap["fallback_count"])
        if n == 0:
            return 0.0
        return -float(snap["latency_delta_total"]) / n

    @property
    def cost_reduction(self) -> float:
        snap = self.snapshot()
        n = int(snap["fallback_count"])
        if n == 0:
            return 0.0
        return -float(snap["cost_delta_total"]) / n

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "fallback_count": self.fallback_count,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "continue_count": self.continue_count,
                "degrade_notify_count": self.degrade_notify_count,
                "candidate_count": self.candidate_count,
                "policy_match_count": self.policy_match_count,
                "health_evaluations": self.health_evaluations,
                "quality_delta_total": self.quality_delta_total,
                "latency_delta_total": self.latency_delta_total,
                "cost_delta_total": self.cost_delta_total,
                "backend_transitions": self.backend_transitions,
                "quantization_transitions": self.quantization_transitions,
                "success_rate": (
                    self.success_count / (self.success_count + self.failure_count)
                    if (self.success_count + self.failure_count)
                    else 0.0
                ),
                "average_degradation": (
                    self.quality_delta_total / self.fallback_count
                    if self.fallback_count
                    else 0.0
                ),
                "latency_improvement": (
                    -self.latency_delta_total / self.fallback_count
                    if self.fallback_count
                    else 0.0
                ),
                "cost_reduction": (
                    -self.cost_delta_total / self.fallback_count
                    if self.fallback_count
                    else 0.0
                ),
            }

    def to_otel_attributes(self) -> dict[str, Any]:
        return {
            f"nexus.runtime.resilience.metric.{k}": v for k, v in self.snapshot().items()
        }

    def reset(self) -> None:
        with self._lock:
            self.fallback_count = 0
            self.success_count = 0
            self.failure_count = 0
            self.continue_count = 0
            self.degrade_notify_count = 0
            self.candidate_count = 0
            self.policy_match_count = 0
            self.health_evaluations = 0
            self.quality_delta_total = 0.0
            self.latency_delta_total = 0.0
            self.cost_delta_total = 0.0
            self.backend_transitions = 0
            self.quantization_transitions = 0
