"""Prometheus / OpenTelemetry telemetry for RPF — profile_* series."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Mapping

from .schemas import RuntimeProfile


def _sanitize(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)[:64] or "unknown"


class InMemoryProfileTelemetry:
    """Prometheus-style store for profile_* metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: dict[str, float] = defaultdict(float)
        self.gauges: dict[str, float] = {}
        self._profile_total = 0.0

    def record_profile(self, profile: RuntimeProfile) -> None:
        provider = _sanitize(profile.profiler_used or "unknown")
        backend = _sanitize(profile.backend.backend or "unknown")
        with self._lock:
            self._profile_total += 1.0
            self.counters["profile_sessions_total"] += 1.0
            self.counters[f'profile_sessions_total{{provider="{provider}"}}'] += 1.0
            self.counters[f'profile_backend_sessions_total{{backend="{backend}"}}'] += 1.0
            self.gauges["profile_cpu_usage_percent"] = float(profile.cpu.usage_percent)
            self.gauges["profile_cpu_time_seconds"] = float(profile.cpu.cpu_time_seconds)
            self.gauges["profile_wall_time_ms"] = float(profile.cpu.wall_time_ms)
            self.gauges["profile_memory_rss_bytes"] = float(profile.memory.rss_bytes)
            self.gauges["profile_memory_peak_bytes"] = float(profile.memory.peak_rss_bytes)
            self.gauges["profile_ipc"] = float(profile.hardware.ipc or profile.hardware.derived_ipc)
            self.gauges["profile_cache_misses"] = float(profile.hardware.cache_misses)
            self.gauges["profile_branch_misses"] = float(profile.hardware.branch_misses)
            self.gauges["profile_cycles"] = float(profile.hardware.cycles)
            self.gauges["profile_instructions"] = float(profile.hardware.instructions)
            self.gauges["profile_pmu_available"] = 1.0 if profile.hardware.pmu_available else 0.0
            ext = dict(profile.hardware.extensions or {})
            self.gauges["profile_sve_events_available"] = float(
                ext.get("sve_events_available") or (1.0 if profile.hardware.sve2_available else 0.0)
            )
            self.gauges["profile_sve_inst_retired"] = float(ext.get("sve_inst_retired") or 0.0)
            self.gauges["profile_perf_target_pid"] = float(ext.get("target_pid") or 0.0)
            self.gauges["profile_planner_ms"] = float(profile.planner.planner_time_ms)
            self.gauges["profile_routing_ms"] = float(profile.planner.routing_time_ms)
            self.gauges["profile_execution_ms"] = float(profile.execution.execution_time_ms)
            self.gauges["profile_streaming_ms"] = float(profile.execution.streaming_time_ms)
            self.gauges["profile_backend_ms"] = float(profile.backend.backend_time_ms)
            self.gauges["profile_queue_ms"] = float(profile.planner.queue_time_ms)
            self.gauges["profile_kv_memory_bytes"] = float(profile.execution.kv_memory_bytes)
            self.gauges["profile_sample_hz"] = float(profile.sampling_frequency_hz)
            self.gauges[f'profile_provider_active{{provider="{provider}"}}'] = 1.0

    def record_failure(self, provider: str, reason: str) -> None:
        with self._lock:
            self.counters["profile_failures_total"] += 1.0
            p = _sanitize(provider)
            self.counters[f'profile_failures_total{{provider="{p}"}}'] += 1.0
            self.gauges["profile_last_failure"] = 1.0
            del reason  # reason kept in logs only to avoid high-cardinality labels

    def snapshot(self) -> Mapping[str, Any]:
        with self._lock:
            return {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "profile_total": self._profile_total,
            }

    def export_prometheus(self) -> str:
        snap = self.snapshot()
        lines: list[str] = [
            "# HELP profile_sessions_total Total finalized profiling sessions",
            "# TYPE profile_sessions_total counter",
            f"profile_sessions_total {snap['counters'].get('profile_sessions_total', 0.0)}",
            "# HELP profile_failures_total Profiling failures (non-fatal)",
            "# TYPE profile_failures_total counter",
            f"profile_failures_total {snap['counters'].get('profile_failures_total', 0.0)}",
            "# HELP profile_cpu_usage_percent Last CPU usage percent",
            "# TYPE profile_cpu_usage_percent gauge",
            "# HELP profile_ipc Last observed IPC",
            "# TYPE profile_ipc gauge",
            "# HELP profile_memory_peak_bytes Last peak RSS bytes",
            "# TYPE profile_memory_peak_bytes gauge",
            "# HELP profile_execution_ms Last execution phase ms",
            "# TYPE profile_execution_ms gauge",
        ]
        for k, v in sorted(snap["counters"].items()):
            if k in {"profile_sessions_total", "profile_failures_total"}:
                continue
            lines.append(f"{k} {v}")
        for k, v in sorted(snap["gauges"].items()):
            lines.append(f"{k} {v}")
        return "\n".join(lines) + "\n"


class OpenTelemetryProfileBridge:
    """Best-effort OTel bridge wrapping in-memory Prometheus store."""

    def __init__(self, inner: InMemoryProfileTelemetry | None = None) -> None:
        self.inner = inner or InMemoryProfileTelemetry()
        self._tracer = None
        try:
            from opentelemetry import trace  # type: ignore

            self._tracer = trace.get_tracer("nexus.armora.rpf")
        except Exception:
            self._tracer = None

    def record_profile(self, profile: RuntimeProfile) -> None:
        self.inner.record_profile(profile)
        if self._tracer is None:
            return
        try:
            with self._tracer.start_as_current_span("rpf.profile") as span:
                span.set_attribute("profiler", profile.profiler_used)
                span.set_attribute("request_id", profile.request_id)
                span.set_attribute("execution_id", profile.execution_id)
                span.set_attribute("ipc", float(profile.hardware.ipc))
                span.set_attribute("cpu_percent", float(profile.cpu.usage_percent))
                span.set_attribute("peak_rss", float(profile.memory.peak_rss_bytes))
        except Exception:
            pass

    def record_failure(self, provider: str, reason: str) -> None:
        self.inner.record_failure(provider, reason)

    def export_prometheus(self) -> str:
        return self.inner.export_prometheus()

    def snapshot(self) -> Mapping[str, Any]:
        return self.inner.snapshot()
