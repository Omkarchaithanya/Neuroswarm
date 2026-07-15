"""Local metrics collector for Meta Orchestrator (OTel-ready names)."""

from __future__ import annotations

import threading
from typing import Any, Mapping


class OrchestratorMetrics:
    """Thread-safe counters / gauges for coordination operations."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._labeled: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    def inc(self, name: str, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        with self._lock:
            if labels:
                key = (name, tuple(sorted(labels.items())))
                self._labeled[key] = self._labeled.get(key, 0.0) + value
            else:
                self._counters[name] = self._counters.get(name, 0.0) + value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def observe(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        self.inc(f"{name}_sum", value, labels=labels)
        self.inc(f"{name}_count", 1.0, labels=labels)

    def get(self, name: str) -> float:
        with self._lock:
            return float(self._counters.get(name, self._gauges.get(name, 0.0)))

    def average(self, name: str) -> float:
        with self._lock:
            total = self._counters.get(f"{name}_sum", 0.0)
            count = self._counters.get(f"{name}_count", 0.0)
            return float(total / count) if count else 0.0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            labeled = {
                f"{n}|{','.join(f'{k}={v}' for k, v in labs)}": val
                for (n, labs), val in self._labeled.items()
            }
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "labeled": labeled,
                "avg_workflow_latency_ms": self.average("nexus_meta_orchestrator_workflow_latency_ms"),
                "avg_coordination_latency_ms": self.average(
                    "nexus_meta_orchestrator_coordination_latency_ms"
                ),
                "avg_aggregation_ms": self.average("nexus_meta_orchestrator_aggregation_ms"),
                "avg_barrier_wait_ms": self.average("nexus_meta_orchestrator_barrier_wait_ms"),
            }

    def record_workflow_started(self) -> None:
        self.inc("nexus_meta_orchestrator_workflows_started_total")

    def record_workflow_completed(self) -> None:
        self.inc("nexus_meta_orchestrator_workflows_completed_total")

    def record_workflow_failed(self) -> None:
        self.inc("nexus_meta_orchestrator_workflows_failed_total")

    def record_assignment(self) -> None:
        self.inc("nexus_meta_orchestrator_assignments_total")

    def record_retry(self) -> None:
        self.inc("nexus_meta_orchestrator_retry_requests_total")

    def record_checkpoint(self) -> None:
        self.inc("nexus_meta_orchestrator_checkpoints_total")

    def record_failure(self) -> None:
        self.inc("nexus_meta_orchestrator_node_failures_total")

    def set_parallelism(self, value: float) -> None:
        self.set_gauge("nexus_meta_orchestrator_parallelism", value)

    def set_agent_utilization(self, value: float) -> None:
        self.set_gauge("nexus_meta_orchestrator_agent_utilization", value)

    def observe_workflow_latency(self, ms: float) -> None:
        self.observe("nexus_meta_orchestrator_workflow_latency_ms", ms)

    def observe_coordination_latency(self, ms: float) -> None:
        self.observe("nexus_meta_orchestrator_coordination_latency_ms", ms)

    def observe_aggregation(self, ms: float) -> None:
        self.observe("nexus_meta_orchestrator_aggregation_ms", ms)

    def observe_barrier_wait(self, ms: float) -> None:
        self.observe("nexus_meta_orchestrator_barrier_wait_ms", ms)
