"""Checkpoint Manager operational metrics (RMF / OTel ready)."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class CheckpointMetrics:
    """Counters for checkpoint-manager operations — not execution telemetry."""

    checkpoint_count: int = 0
    checkpoint_size_bytes: int = 0
    snapshot_count: int = 0
    recovery_count: int = 0
    rollback_count: int = 0
    retention_operations: int = 0
    policy_evaluations: int = 0
    policy_triggers: int = 0
    validation_failures: int = 0
    restores_total: int = 0
    recovery_latency_ms_total: float = 0.0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def incr(self, name: str, amount: int | float = 1) -> None:
        with self._lock:
            if not hasattr(self, name):
                raise AttributeError(name)
            setattr(self, name, getattr(self, name) + amount)

    def record_recovery_latency(self, latency_ms: float) -> None:
        with self._lock:
            self.recovery_count += 1
            self.recovery_latency_ms_total += max(0.0, latency_ms)

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "checkpoint_count": self.checkpoint_count,
                "checkpoint_size_bytes": self.checkpoint_size_bytes,
                "snapshot_count": self.snapshot_count,
                "recovery_count": self.recovery_count,
                "rollback_count": self.rollback_count,
                "retention_operations": self.retention_operations,
                "policy_evaluations": self.policy_evaluations,
                "policy_triggers": self.policy_triggers,
                "validation_failures": self.validation_failures,
                "restores_total": self.restores_total,
                "recovery_latency_ms_total": self.recovery_latency_ms_total,
            }

    def to_otel_attributes(self) -> dict[str, Any]:
        return {
            f"nexus.swarm.checkpoint.metric.{k}": v for k, v in self.snapshot().items()
        }

    def reset(self) -> None:
        with self._lock:
            self.checkpoint_count = 0
            self.checkpoint_size_bytes = 0
            self.snapshot_count = 0
            self.recovery_count = 0
            self.rollback_count = 0
            self.retention_operations = 0
            self.policy_evaluations = 0
            self.policy_triggers = 0
            self.validation_failures = 0
            self.restores_total = 0
            self.recovery_latency_ms_total = 0.0
