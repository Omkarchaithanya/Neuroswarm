"""ROF metrics — Prometheus-compatible store with cardinality guards."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Mapping

from .schemas import ALLOWED_METRIC_LABELS, FORBIDDEN_METRIC_LABELS, MetricSample


def _sanitize_label_value(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "_-." else "_" for ch in str(value))[:64]


def _format_labels(labels: Mapping[str, str] | None) -> str:
    if not labels:
        return ""
    parts = [f'{k}="{_sanitize_label_value(v)}"' for k, v in sorted(labels.items())]
    return "{" + ",".join(parts) + "}"


class ROFMeter:
    """In-process counter/gauge/histogram bridge with cardinality protection."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: dict[str, float] = defaultdict(float)
        self.gauges: dict[str, float] = {}
        self.histograms: dict[str, list[float]] = defaultdict(list)
        self.types: dict[str, str] = {}
        self.help_text: dict[str, str] = {}
        self._dropped_labels = 0
        self._describe_builtins()

    def _describe_builtins(self) -> None:
        self.describe("rof_spans_exported_total", "counter", "Spans successfully exported")
        self.describe("rof_spans_dropped_total", "counter", "Spans dropped due to backpressure or sampling")
        self.describe("rof_export_failures_total", "counter", "Exporter failures")
        self.describe("rof_export_latency_seconds", "gauge", "Last export batch latency seconds")
        self.describe("rof_events_emitted_total", "counter", "Runtime events emitted")
        self.describe("rof_logs_emitted_total", "counter", "Structured log records emitted")
        self.describe("rof_metric_label_drops_total", "counter", "Forbidden/high-cardinality labels dropped")
        self.describe("nexus_requests_total", "counter", "Total runtime requests observed by ROF")
        self.describe("nexus_request_latency_seconds", "histogram", "End-to-end request latency seconds")
        self.describe("nexus_planner_duration_seconds", "histogram", "Planner stage duration seconds")
        self.describe("nexus_planner_prediction_error", "gauge", "Planner prediction absolute error")
        self.describe("nexus_routing_duration_seconds", "histogram", "Routing stage duration seconds")
        self.describe("nexus_backend_selected_total", "counter", "Backend selection counts")
        self.describe("nexus_inference_duration_seconds", "histogram", "Inference duration seconds")
        self.describe("nexus_prompt_tokens", "counter", "Prompt tokens processed")
        self.describe("nexus_completion_tokens", "counter", "Completion tokens generated")
        self.describe("nexus_reasoning_tokens", "counter", "Reasoning tokens consumed")
        self.describe("nexus_streaming_ttft_seconds", "histogram", "Time to first token seconds")
        self.describe("nexus_streaming_duration_seconds", "histogram", "Streaming duration seconds")
        self.describe("nexus_queue_wait_seconds", "histogram", "Queue wait seconds")
        self.describe("nexus_cpu_seconds", "gauge", "CPU seconds last request")
        self.describe("nexus_memory_bytes", "gauge", "Memory bytes last request")
        self.describe("nexus_peak_memory_bytes", "gauge", "Peak memory bytes last request")
        self.describe("nexus_energy_estimate", "gauge", "Energy estimate joules")
        self.describe("nexus_cost_estimate", "gauge", "Cost estimate dollars")

    def describe(self, name: str, metric_type: str, help_text: str) -> None:
        with self._lock:
            self.types[name] = metric_type
            self.help_text[name] = help_text

    def _filter_labels(self, labels: Mapping[str, str] | None) -> dict[str, str]:
        if not labels:
            return {}
        out: dict[str, str] = {}
        for k, v in labels.items():
            key = str(k)
            if key in FORBIDDEN_METRIC_LABELS or key not in ALLOWED_METRIC_LABELS:
                self._dropped_labels += 1
                self.counters["rof_metric_label_drops_total"] += 1
                continue
            out[key] = _sanitize_label_value(v)
        return out

    def counter(self, name: str, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        safe = self._filter_labels(labels)
        key = f"{name}{_format_labels(safe)}"
        with self._lock:
            self.types.setdefault(name, "counter")
            self.counters[key] += float(value)

    def gauge(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        safe = self._filter_labels(labels)
        key = f"{name}{_format_labels(safe)}"
        with self._lock:
            self.types.setdefault(name, "gauge")
            self.gauges[key] = float(value)

    def histogram(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        safe = self._filter_labels(labels)
        key = f"{name}{_format_labels(safe)}"
        with self._lock:
            self.types.setdefault(name, "histogram")
            bucket = self.histograms[key]
            bucket.append(float(value))
            if len(bucket) > 1024:
                del bucket[:512]
            # Also expose last value as gauge for scrape simplicity
            self.gauges[f"{name}_last{_format_labels(safe)}"] = float(value)
            self.counters[f"{name}_count{_format_labels(safe)}"] += 1.0
            self.counters[f"{name}_sum{_format_labels(safe)}"] += float(value)

    def record_sample(self, sample: MetricSample) -> None:
        if sample.metric_type == "counter":
            self.counter(sample.name, sample.value, labels=sample.labels)
        elif sample.metric_type == "histogram":
            self.histogram(sample.name, sample.value, labels=sample.labels)
        else:
            self.gauge(sample.name, sample.value, labels=sample.labels)
        if sample.help_text:
            self.describe(sample.name, sample.metric_type, sample.help_text)

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            out = dict(self.counters)
            out.update(self.gauges)
            return out

    def export_prometheus(self) -> str:
        with self._lock:
            lines: list[str] = []
            seen_help: set[str] = set()
            items: list[tuple[str, float]] = []
            items.extend(self.counters.items())
            items.extend(self.gauges.items())
            # Ensure described series appear even before first write
            for name in sorted(self.types):
                if name not in {k.split("{", 1)[0] for k, _ in items}:
                    items.append((name, 0.0))
            for key, value in sorted(items):
                base = key.split("{", 1)[0]
                if base not in seen_help:
                    help_text = self.help_text.get(base)
                    metric_type = self.types.get(base, "gauge")
                    if help_text:
                        lines.append(f"# HELP {base} {help_text}")
                    lines.append(f"# TYPE {base} {metric_type}")
                    seen_help.add(base)
                lines.append(f"{key} {value}")
            return "\n".join(lines) + ("\n" if lines else "")
