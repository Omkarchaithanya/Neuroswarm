"""Bridge adapters — preserve existing metric ABIs under ROF."""

from __future__ import annotations

from typing import Any, Mapping

from ..schemas import MetricSample


class MetricsStoreSource:
    """Wrap neuroswarm_arm.metrics.MetricsStore as IMetricSource."""

    name = "metrics_store"

    def __init__(self, store: Any) -> None:
        self.store = store

    def collect(self) -> list[MetricSample]:
        text = self.export_prometheus()
        samples: list[MetricSample] = []
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.rsplit(" ", 1)
            if len(parts) != 2:
                continue
            try:
                samples.append(MetricSample(name=parts[0], value=float(parts[1])))
            except ValueError:
                continue
        return samples

    def export_prometheus(self) -> str:
        if hasattr(self.store, "export_prometheus"):
            return self.store.export_prometheus()
        return ""


class BudgetTelemetrySource:
    """Expose budget_service.export_prometheus() via ROF registry."""

    name = "budget"

    def __init__(self, budget_service: Any) -> None:
        self.budget_service = budget_service

    def collect(self) -> list[MetricSample]:
        return []

    def export_prometheus(self) -> str:
        if hasattr(self.budget_service, "export_prometheus"):
            return self.budget_service.export_prometheus()
        return ""


class RCISTelemetrySource:
    name = "rcis"

    def __init__(self, rcis: Any) -> None:
        self.rcis = rcis

    def collect(self) -> list[MetricSample]:
        return []

    def export_prometheus(self) -> str:
        if hasattr(self.rcis, "export_prometheus"):
            return self.rcis.export_prometheus()
        return ""


class RPFTelemetrySource:
    name = "rpf"

    def __init__(self, rpf: Any) -> None:
        self.rpf = rpf

    def collect(self) -> list[MetricSample]:
        return []

    def export_prometheus(self) -> str:
        if hasattr(self.rpf, "export_prometheus"):
            return self.rpf.export_prometheus()
        return ""


class CallablePrometheusSource:
    """Generic adapter for any object with export_prometheus / prometheus_text."""

    def __init__(self, name: str, target: Any, method: str = "export_prometheus") -> None:
        self.name = name
        self.target = target
        self.method = method

    def collect(self) -> list[MetricSample]:
        return []

    def export_prometheus(self) -> str:
        fn = getattr(self.target, self.method, None)
        if callable(fn):
            try:
                return str(fn() or "")
            except Exception:
                return ""
        return ""


class ROFBudgetTelemetryBridge:
    """ITelemetryExporter-compatible wrapper that also emits ROF spans/events."""

    def __init__(self, inner: Any, rof: Any | None = None) -> None:
        self.inner = inner
        self.rof = rof

    def record_admit(self, *, accepted: bool, tenant: str = "", agent: str = "") -> None:
        self.inner.record_admit(accepted=accepted, tenant=tenant, agent=agent)
        if self.rof is not None:
            self.rof.counter(
                "nexus_requests_total",
                1.0,
                labels={"outcome": "accept" if accepted else "reject", "agent": agent or "default"},
            )
            if not accepted:
                from ..schemas import EventType

                self.rof.emit_builtin(EventType.BUDGET_EXCEEDED, payload={"tenant": tenant, "agent": agent})

    def record_remaining(self, dim: str, value: float, *, scope: str = "request") -> None:
        self.inner.record_remaining(dim, value, scope=scope)

    def record_violation(self, dim: str, hardness: str) -> None:
        self.inner.record_violation(dim, hardness)
        if self.rof is not None:
            from ..schemas import AttributeKeys, EventType

            self.rof.emit_builtin(
                EventType.BUDGET_EXCEEDED,
                payload={"dim": dim, "hardness": hardness},
            )
            # Force-sample marker for current span attributes via log
            self.rof.log("WARNING", "budget violation", dim=dim, hardness=hardness, **{AttributeKeys.FORCE_SAMPLE: True})

    def record_estimate_error(self, dim: str, error: float) -> None:
        self.inner.record_estimate_error(dim, error)

    def record_degrade(self, action: str) -> None:
        self.inner.record_degrade(action)

    def record_efficiency(self, *, tokens_per_usd: float, tokens_per_watt: float) -> None:
        self.inner.record_efficiency(tokens_per_usd=tokens_per_usd, tokens_per_watt=tokens_per_watt)

    def snapshot(self) -> Mapping[str, Any]:
        return self.inner.snapshot()

    def export_prometheus(self) -> str:
        return self.inner.export_prometheus()

    def span(self, name: str):
        if self.rof is not None:
            return self.rof.span(f"nexus.armora.budget.{name}")
        if hasattr(self.inner, "span"):
            return self.inner.span(name)
        from contextlib import nullcontext

        return nullcontext()


class ROFCostTelemetryBridge:
    """RCIS telemetry bridge that emits CostReportGenerated events."""

    def __init__(self, inner: Any, rof: Any | None = None) -> None:
        self.inner = inner
        self.rof = rof

    def record_report(self, report: Any) -> None:
        self.inner.record_report(report)
        if self.rof is not None:
            from ..schemas import EventType

            self.rof.emit_builtin(
                EventType.COST_REPORT_GENERATED,
                payload={
                    "execution_id": getattr(report, "execution_id", ""),
                    "estimated_dollars": float(getattr(report, "estimated_dollars", 0) or 0),
                    "backend": getattr(report, "backend", ""),
                },
            )
            if getattr(report, "prediction_errors", None) is not None:
                self.rof.emit_builtin(
                    EventType.PLANNER_LEARNED,
                    payload={"execution_id": getattr(report, "execution_id", "")},
                )
            self.rof.gauge("nexus_cost_estimate", float(getattr(report, "estimated_dollars", 0) or 0))
            self.rof.gauge("nexus_energy_estimate", float(getattr(report, "energy_estimate_joules", 0) or 0))
            self.rof.gauge("nexus_cpu_seconds", float(getattr(report, "cpu_seconds", 0) or 0))
            self.rof.gauge("nexus_peak_memory_bytes", float(getattr(report, "peak_memory_bytes", 0) or 0))
            self.rof.counter("nexus_prompt_tokens", float(getattr(report, "prompt_tokens", 0) or 0))
            self.rof.counter("nexus_completion_tokens", float(getattr(report, "completion_tokens", 0) or 0))
            self.rof.counter("nexus_reasoning_tokens", float(getattr(report, "reasoning_tokens", 0) or 0))

    def snapshot(self) -> Mapping[str, Any]:
        return self.inner.snapshot()

    def export_prometheus(self) -> str:
        return self.inner.export_prometheus()

    def __getattr__(self, item: str) -> Any:
        return getattr(self.inner, item)
