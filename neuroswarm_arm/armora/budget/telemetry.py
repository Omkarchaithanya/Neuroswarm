"""OpenTelemetry / Prometheus telemetry for Budget Envelope."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Mapping


class InMemoryTelemetry:
    """Prometheus-style counter/gauge store with bounded label cardinality."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: dict[str, float] = defaultdict(float)
        self.gauges: dict[str, float] = {}
        self._admit_total = 0.0
        self._admit_reject = 0.0

    def record_admit(self, *, accepted: bool, tenant: str = "", agent: str = "") -> None:
        del tenant, agent
        with self._lock:
            self._admit_total += 1
            key = "budget_admit_total{result=\"accept\"}" if accepted else "budget_admit_total{result=\"reject\"}"
            self.counters[key] += 1
            if not accepted:
                self._admit_reject += 1

    def record_remaining(self, dim: str, value: float, *, scope: str = "request") -> None:
        with self._lock:
            self.gauges[f'budget_remaining{{dim="{dim}",scope="{scope}"}}'] = float(value)

    def record_reserved(self, dim: str, value: float) -> None:
        with self._lock:
            self.gauges[f'budget_reserved{{dim="{dim}"}}'] = float(value)

    def record_violation(self, dim: str, hardness: str) -> None:
        with self._lock:
            self.counters[f'budget_violation_total{{dim="{dim}",hardness="{hardness}"}}'] += 1

    def record_estimate_error(self, dim: str, error: float) -> None:
        with self._lock:
            self.gauges[f'budget_estimate_error{{dim="{dim}"}}'] = float(error)

    def record_degrade(self, action: str) -> None:
        with self._lock:
            self.counters[f'budget_optimizer_degrades_total{{action="{action}"}}'] += 1

    def record_efficiency(self, *, tokens_per_usd: float, tokens_per_watt: float) -> None:
        with self._lock:
            self.gauges["budget_tokens_per_usd"] = float(tokens_per_usd)
            self.gauges["budget_tokens_per_watt"] = float(tokens_per_watt)

    def snapshot(self) -> Mapping[str, Any]:
        with self._lock:
            return {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "admit_total": self._admit_total,
                "admit_reject": self._admit_reject,
            }

    def export_prometheus(self) -> str:
        snap = self.snapshot()
        lines: list[str] = [
            "# HELP budget_admit_total Budget admission decisions",
            "# TYPE budget_admit_total counter",
        ]
        for k, v in sorted(snap["counters"].items()):
            lines.append(f"{k} {v}")
        lines.append("# TYPE budget_remaining gauge")
        for k, v in sorted(snap["gauges"].items()):
            lines.append(f"{k} {v}")
        return "\n".join(lines) + "\n"


class OpenTelemetryBudgetBridge:
    """Best-effort OTel bridge; no-ops if SDK absent."""

    def __init__(self, inner: InMemoryTelemetry | None = None) -> None:
        self.inner = inner or InMemoryTelemetry()
        self._tracer = None
        try:
            from opentelemetry import trace  # type: ignore

            self._tracer = trace.get_tracer("nexus.armora.budget")
        except Exception:
            self._tracer = None

    def span(self, name: str):
        if self._tracer is None:
            return _NullSpan()
        return self._tracer.start_as_current_span(name)

    def record_admit(self, *, accepted: bool, tenant: str = "", agent: str = "") -> None:
        self.inner.record_admit(accepted=accepted, tenant=tenant, agent=agent)

    def record_remaining(self, dim: str, value: float, *, scope: str = "request") -> None:
        self.inner.record_remaining(dim, value, scope=scope)

    def record_violation(self, dim: str, hardness: str) -> None:
        self.inner.record_violation(dim, hardness)

    def record_estimate_error(self, dim: str, error: float) -> None:
        self.inner.record_estimate_error(dim, error)

    def record_degrade(self, action: str) -> None:
        self.inner.record_degrade(action)

    def record_efficiency(self, *, tokens_per_usd: float, tokens_per_watt: float) -> None:
        self.inner.record_efficiency(
            tokens_per_usd=tokens_per_usd, tokens_per_watt=tokens_per_watt
        )

    def snapshot(self) -> Mapping[str, Any]:
        return self.inner.snapshot()

    def export_prometheus(self) -> str:
        return self.inner.export_prometheus()


class _NullSpan:
    def __enter__(self) -> "_NullSpan":
        return self

    def __exit__(self, *args: object) -> None:
        return None
