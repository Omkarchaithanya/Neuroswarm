"""HAOE Prometheus / MetricsStore bridge."""

from __future__ import annotations

from typing import Any

from ..interfaces import IMetricsExporter
from ..runtime.runtime_metrics import RuntimeMetrics

METRIC_HELP = {
    "haoe_tasks_total": ("counter", "Total tasks executed by HAOE."),
    "haoe_tasks_failed_total": ("counter", "Total failed HAOE tasks."),
    "haoe_tasks_cancelled_total": ("counter", "Total cancelled HAOE tasks."),
    "haoe_retries_total": ("counter", "Total HAOE task retries."),
    "haoe_workflows_total": ("counter", "Total workflows executed."),
    "haoe_queue_depth": ("gauge", "Current HAOE queue depth."),
    "haoe_steal_total": ("counter", "Work-steal operations."),
    "haoe_affinity_success_total": ("counter", "Successful affinity binds."),
    "haoe_affinity_failure_total": ("counter", "Failed affinity binds."),
    "haoe_task_latency_ms": ("gauge", "Last task latency in milliseconds."),
    "haoe_scheduling_latency_ms": ("gauge", "Last scheduling latency in milliseconds."),
    "haoe_workflow_latency_ms": ("gauge", "Last workflow latency in milliseconds."),
    "haoe_worker_utilization": ("gauge", "Average worker pool utilization 0..1."),
    "haoe_throughput_tasks_per_s": ("gauge", "Recent task throughput."),
}


class HAOEMetrics(IMetricsExporter):
    def __init__(
        self,
        bridge: Any | None = None,
        local: RuntimeMetrics | None = None,
    ) -> None:
        self._bridge = bridge
        self.local = local or RuntimeMetrics()
        self._describe_all()

    def _describe_all(self) -> None:
        if self._bridge is None or not hasattr(self._bridge, "describe"):
            return
        for name, (mtype, help_text) in METRIC_HELP.items():
            try:
                self._bridge.describe(name, mtype, help_text)
            except Exception:
                continue

    def inc(self, name: str, value: float = 1.0) -> None:
        self.local.inc(name, value)
        if self._bridge is not None and hasattr(self._bridge, "inc"):
            try:
                self._bridge.inc(name, value)
            except Exception:
                pass

    def set(self, name: str, value: float) -> None:
        self.local.set(name, value)
        if self._bridge is not None and hasattr(self._bridge, "set"):
            try:
                self._bridge.set(name, value)
            except Exception:
                pass

    def observe(self, name: str, value: float) -> None:
        self.local.observe(name, value)
        # Bridge stores last value as gauge for simplicity.
        self.set(name, value)
