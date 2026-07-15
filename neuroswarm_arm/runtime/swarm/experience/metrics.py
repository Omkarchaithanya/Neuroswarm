"""Experience Store operational metrics (RMF / OTel ready)."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class ExperienceMetrics:
    """Counters for store operations — not execution telemetry."""

    records_stored: int = 0
    workflows_stored: int = 0
    snapshots_stored: int = 0
    dataset_exports: int = 0
    queries: int = 0
    analytics_runs: int = 0
    retention_operations: int = 0
    import_operations: int = 0
    validation_failures: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def incr(self, name: str, amount: int = 1) -> None:
        with self._lock:
            if not hasattr(self, name):
                raise AttributeError(name)
            setattr(self, name, getattr(self, name) + amount)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "records_stored": self.records_stored,
                "workflows_stored": self.workflows_stored,
                "snapshots_stored": self.snapshots_stored,
                "dataset_exports": self.dataset_exports,
                "queries": self.queries,
                "analytics_runs": self.analytics_runs,
                "retention_operations": self.retention_operations,
                "import_operations": self.import_operations,
                "validation_failures": self.validation_failures,
            }

    def to_otel_attributes(self) -> dict[str, Any]:
        return {
            f"nexus.swarm.experience.metric.{k}": v for k, v in self.snapshot().items()
        }

    def reset(self) -> None:
        with self._lock:
            self.records_stored = 0
            self.workflows_stored = 0
            self.snapshots_stored = 0
            self.dataset_exports = 0
            self.queries = 0
            self.analytics_runs = 0
            self.retention_operations = 0
            self.import_operations = 0
            self.validation_failures = 0
