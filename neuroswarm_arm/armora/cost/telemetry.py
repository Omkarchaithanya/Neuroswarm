"""Prometheus / OpenTelemetry telemetry for RCIS."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Mapping

from .schemas import RuntimeCostReport


class InMemoryCostTelemetry:
    """Prometheus-style store for runtime_* metrics with bounded labels."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: dict[str, float] = defaultdict(float)
        self.gauges: dict[str, float] = {}
        self._report_total = 0.0

    def record_report(self, report: RuntimeCostReport) -> None:
        backend = _sanitize(report.backend or "unknown")
        model = _sanitize(report.model or "unknown")
        quant = _sanitize(report.quantization or "unknown")
        with self._lock:
            self._report_total += 1
            self.counters["runtime_cost_total"] += float(report.estimated_dollars)
            self.counters["runtime_prompt_tokens_total"] += float(report.prompt_tokens or 0)
            self.counters["runtime_completion_tokens_total"] += float(
                report.completion_tokens or 0
            )
            self.counters["runtime_reasoning_tokens_total"] += float(
                report.reasoning_tokens or 0
            )
            self.counters[f'runtime_backend_cost{{backend="{backend}"}}'] += float(
                report.estimated_dollars
            )
            self.counters[f'runtime_model_cost{{model="{model}"}}'] += float(
                report.estimated_dollars
            )
            self.counters[f'runtime_quant_cost{{quant="{quant}"}}'] += float(
                report.estimated_dollars
            )
            self.gauges["runtime_cpu_seconds"] = float(report.cpu_seconds)
            self.gauges["runtime_memory_bytes"] = float(report.peak_memory_bytes)
            self.gauges["runtime_energy_estimate"] = float(report.energy_estimate_joules)
            self.gauges["runtime_kv_reuse"] = float(report.kv_reuse_ratio)
            self.gauges["runtime_spec_acceptance"] = float(report.speculation_acceptance_ratio)
            per_tok = 0.0
            if report.total_tokens > 0:
                per_tok = float(report.estimated_dollars) / float(report.total_tokens)
            self.gauges["runtime_cost_per_token"] = per_tok
            self.gauges["runtime_tokens_per_dollar"] = float(report.tokens_per_dollar)
            self.gauges["runtime_tokens_per_watt"] = float(report.tokens_per_watt)
            if report.prediction_errors is not None:
                pe = report.prediction_errors
                self.gauges['runtime_planner_prediction_error{dim="cost"}'] = float(pe.cost_error)
                self.gauges['runtime_planner_prediction_error{dim="latency"}'] = float(
                    pe.latency_error
                )
                self.gauges['runtime_planner_prediction_error{dim="energy"}'] = float(
                    pe.energy_error
                )
                self.gauges['runtime_planner_prediction_error{dim="memory"}'] = float(
                    pe.memory_error
                )
                self.gauges["runtime_planner_accuracy"] = float(pe.planner_accuracy)

    def record_prediction_error(self, dim: str, error: float) -> None:
        with self._lock:
            self.gauges[f'runtime_planner_prediction_error{{dim="{_sanitize(dim)}"}}'] = float(
                error
            )

    def snapshot(self) -> Mapping[str, Any]:
        with self._lock:
            return {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "report_total": self._report_total,
            }

    def export_prometheus(self) -> str:
        snap = self.snapshot()
        lines: list[str] = [
            "# HELP runtime_cost_total Cumulative estimated runtime cost (optimization signal)",
            "# TYPE runtime_cost_total counter",
            f"runtime_cost_total {snap['counters'].get('runtime_cost_total', 0.0)}",
            "# HELP runtime_prompt_tokens_total Cumulative prompt tokens from RCIS reports",
            "# TYPE runtime_prompt_tokens_total counter",
            f"runtime_prompt_tokens_total {snap['counters'].get('runtime_prompt_tokens_total', 0.0)}",
            "# HELP runtime_completion_tokens_total Cumulative completion tokens from RCIS reports",
            "# TYPE runtime_completion_tokens_total counter",
            f"runtime_completion_tokens_total {snap['counters'].get('runtime_completion_tokens_total', 0.0)}",
            "# HELP runtime_reasoning_tokens_total Cumulative reasoning tokens from RCIS reports",
            "# TYPE runtime_reasoning_tokens_total counter",
            f"runtime_reasoning_tokens_total {snap['counters'].get('runtime_reasoning_tokens_total', 0.0)}",
            "# HELP runtime_cost_per_token Last observed cost per token",
            "# TYPE runtime_cost_per_token gauge",
            "# HELP runtime_cpu_seconds Last observed CPU seconds",
            "# TYPE runtime_cpu_seconds gauge",
            "# HELP runtime_memory_bytes Last observed peak memory bytes",
            "# TYPE runtime_memory_bytes gauge",
            "# HELP runtime_energy_estimate Last observed energy joules",
            "# TYPE runtime_energy_estimate gauge",
            "# HELP runtime_kv_reuse Last KV reuse ratio",
            "# TYPE runtime_kv_reuse gauge",
            "# HELP runtime_spec_acceptance Last speculative acceptance ratio",
            "# TYPE runtime_spec_acceptance gauge",
            "# HELP runtime_planner_prediction_error Prediction error by dimension",
            "# TYPE runtime_planner_prediction_error gauge",
        ]
        skip = {
            "runtime_cost_total",
            "runtime_prompt_tokens_total",
            "runtime_completion_tokens_total",
            "runtime_reasoning_tokens_total",
        }
        for k, v in sorted(snap["counters"].items()):
            if k in skip:
                continue
            lines.append(f"{k} {v}")
        for k, v in sorted(snap["gauges"].items()):
            lines.append(f"{k} {v}")
        return "\n".join(lines) + "\n"


class OpenTelemetryCostBridge:
    """Best-effort OTel bridge; no-ops if SDK absent."""

    def __init__(self, inner: InMemoryCostTelemetry | None = None) -> None:
        self.inner = inner or InMemoryCostTelemetry()
        self._tracer = None
        try:
            from opentelemetry import trace  # type: ignore

            self._tracer = trace.get_tracer("nexus.armora.rcis")
        except Exception:
            self._tracer = None

    def span(self, name: str):
        if self._tracer is None:
            return _NullSpan()
        return self._tracer.start_as_current_span(name)

    def record_report(self, report: RuntimeCostReport) -> None:
        self.inner.record_report(report)
        if self._tracer is not None:
            with self.span("rcis.report") as span:
                try:
                    span.set_attribute("runtime.cost.usd", float(report.estimated_dollars))
                    span.set_attribute("runtime.backend", report.backend)
                    span.set_attribute("runtime.quantization", report.quantization)
                    span.set_attribute("gen_ai.request.model", report.model)
                    span.set_attribute("gen_ai.usage.input_tokens", int(report.prompt_tokens))
                    span.set_attribute("gen_ai.usage.output_tokens", int(report.completion_tokens))
                except Exception:
                    pass

    def record_prediction_error(self, dim: str, error: float) -> None:
        self.inner.record_prediction_error(dim, error)

    def snapshot(self) -> Mapping[str, Any]:
        return self.inner.snapshot()

    def export_prometheus(self) -> str:
        return self.inner.export_prometheus()


class _NullSpan:
    def __enter__(self):
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def set_attribute(self, *args: Any, **kwargs: Any) -> None:
        return None


def _sanitize(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)[:64]
