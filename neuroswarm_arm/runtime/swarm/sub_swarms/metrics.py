"""Local metrics collector for Sub Swarms (OTel-ready names)."""

from __future__ import annotations

import threading
from typing import Any, Mapping


class SwarmMetrics:
    """Thread-safe counters / gauges for template operations.

    Labels are bounded: workflow_type, category, status only.
    Never attach workflow_id / request_id / trace_id.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._labeled: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._usage: dict[str, float] = {}
        self._selection_freq: dict[str, float] = {}
        self._success: dict[str, tuple[float, float]] = {}  # id -> (ok, total)

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

    def record_registration(self, *, category: str = "") -> None:
        labels = {"category": category} if category else None
        self.inc("nexus_sub_swarm_registrations_total", labels=labels)

    def record_selection(self, *, template_id: str, workflow_type: str = "") -> None:
        self.inc("nexus_sub_swarm_selections_total")
        with self._lock:
            self._selection_freq[template_id] = self._selection_freq.get(template_id, 0.0) + 1.0
        if workflow_type:
            self.inc(
                "nexus_sub_swarm_selections_by_type_total",
                labels={"workflow_type": workflow_type},
            )

    def record_usage(self, template_id: str) -> None:
        self.inc("nexus_sub_swarm_usage_total")
        with self._lock:
            self._usage[template_id] = self._usage.get(template_id, 0.0) + 1.0

    def record_execution(
        self,
        template_id: str,
        *,
        success: bool,
        latency_ms: float | None = None,
        cost_usd: float | None = None,
    ) -> None:
        self.inc("nexus_sub_swarm_executions_total")
        with self._lock:
            ok, total = self._success.get(template_id, (0.0, 0.0))
            total += 1.0
            if success:
                ok += 1.0
            self._success[template_id] = (ok, total)
        if latency_ms is not None:
            self.observe("nexus_sub_swarm_latency_ms", latency_ms)
        if cost_usd is not None:
            self.observe("nexus_sub_swarm_cost_usd", cost_usd)

    def success_rate(self, template_id: str) -> float:
        with self._lock:
            ok, total = self._success.get(template_id, (0.0, 0.0))
            return float(ok / total) if total else 0.0

    def selection_frequency(self, template_id: str) -> float:
        with self._lock:
            return float(self._selection_freq.get(template_id, 0.0))

    def usage_count(self, template_id: str) -> float:
        with self._lock:
            return float(self._usage.get(template_id, 0.0))

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
                "usage": dict(self._usage),
                "selection_frequency": dict(self._selection_freq),
                "avg_latency_ms": self.average("nexus_sub_swarm_latency_ms"),
                "avg_cost_usd": self.average("nexus_sub_swarm_cost_usd"),
                "success": {
                    tid: {"ok": ok, "total": total, "rate": (ok / total if total else 0.0)}
                    for tid, (ok, total) in self._success.items()
                },
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._labeled.clear()
            self._usage.clear()
            self._selection_freq.clear()
            self._success.clear()
