"""MetricsStore facade — dual-write bridge for legacy metrics_bridge callers."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .lifecycle import RuntimeMetricsFramework


@dataclass
class MetricsStore:
    """Drop-in replacement for the historical flat MetricsStore.

    All mutations go to the RMF registry. Local dicts remain for tests that
    inspect `.counters` directly.
    """

    lock: Lock = field(default_factory=Lock)
    counters: dict[str, float] = field(default_factory=dict)
    types: dict[str, str] = field(default_factory=dict)
    help_text: dict[str, str] = field(default_factory=dict)
    _rmf: RuntimeMetricsFramework | None = field(default=None, repr=False)

    def bind(self, rmf: RuntimeMetricsFramework) -> None:
        self._rmf = rmf

    def _framework(self) -> RuntimeMetricsFramework:
        if self._rmf is not None:
            return self._rmf
        from .lifecycle import get_rmf

        self._rmf = get_rmf()
        return self._rmf

    def _maybe_rmf(self) -> RuntimeMetricsFramework | None:
        if self._rmf is not None:
            return self._rmf
        try:
            from .lifecycle import peek_rmf

            existing = peek_rmf()
            if existing is not None:
                self._rmf = existing
                return self._rmf
        except Exception:
            return None
        return None

    def inc(self, name: str, value: float = 1.0) -> None:
        with self.lock:
            self.types.setdefault(name, "counter")
            self.counters[name] = self.counters.get(name, 0.0) + value
        rmf = self._maybe_rmf()
        if rmf is not None:
            try:
                rmf.inc(name, value)
            except Exception:
                pass

    def set(self, name: str, value: float) -> None:
        with self.lock:
            self.types.setdefault(name, "gauge")
            self.counters[name] = value
        rmf = self._maybe_rmf()
        if rmf is not None:
            try:
                rmf.set(name, value)
            except Exception:
                pass

    def describe(self, name: str, metric_type: str, help_text: str) -> None:
        with self.lock:
            self.types[name] = metric_type
            self.help_text[name] = help_text
        rmf = self._maybe_rmf()
        if rmf is None:
            return
        try:
            from .schemas import MetricDomain, MetricType

            mtype = (
                MetricType(metric_type)
                if metric_type in MetricType._value2member_map_
                else MetricType.GAUGE
            )
            rmf.registry.ensure(name, mtype, help_text, domain=MetricDomain.LEGACY)
        except Exception:
            pass

    def export_prometheus(self) -> str:
        """Local-only text export for ROF bridges (avoids RMF↔ROF scrape recursion)."""
        with self.lock:
            lines = []
            for key, value in sorted(self.counters.items()):
                metric_type = self.types.get(key, "gauge")
                help_text = self.help_text.get(key)
                if help_text:
                    lines.append(f"# HELP {key} {help_text}")
                lines.append(f"# TYPE {key} {metric_type}")
                lines.append(f"{key} {value}")
            return "\n".join(lines) + ("\n" if lines else "")

    def sync_local_into_rmf(self) -> None:
        """Flush locally buffered counter/gauge values into bound RMF."""
        rmf = self._maybe_rmf()
        if rmf is None:
            return
        with self.lock:
            items = list(self.counters.items())
            types = dict(self.types)
        for name, value in items:
            mtype = types.get(name, "gauge")
            if mtype == "counter":
                rmf.set(name, value)  # absolute mirror for scrape continuity
            else:
                rmf.set(name, value)


def build_default_store() -> MetricsStore:
    store = MetricsStore()
    builtins = (
        ("neuroswarm_requests_total", "counter", "Total chat requests processed by the gateway."),
        ("neuroswarm_cascade_tier_1_total", "counter", "Number of requests handled by tier 1."),
        ("neuroswarm_cascade_tier_2_total", "counter", "Number of requests escalated to tier 2."),
        ("neuroswarm_cascade_tier_3_total", "counter", "Number of requests escalated to tier 3."),
        ("neuroswarm_last_request_latency_ms", "gauge", "Latency in milliseconds for the last chat request."),
        ("neuroswarm_last_tier_used", "gauge", "Most recent cascade tier used."),
        ("neuroswarm_last_thinking_token_cap", "gauge", "Most recent reasoning-token cap."),
        ("neuroswarm_last_tool_schema_count", "gauge", "Tool schema count used by the last request."),
        ("rtg_admits_total", "counter", "RTG session admits."),
        ("rtg_decisions_total", "counter", "RTG control decisions."),
        ("rtg_early_exit_total", "counter", "RTG early exits / force closes."),
        ("rtg_completions_total", "counter", "RTG session completions."),
        ("rtg_budget_remaining", "gauge", "Last RTG remaining thinking budget."),
        ("rtg_thinking_tokens", "gauge", "Last RTG thinking tokens consumed."),
        ("rtg_last_initial_budget", "gauge", "Last RTG initial thinking budget."),
        ("rtg_last_confidence", "gauge", "Last RTG confidence EMA."),
        ("router_requests_total", "counter", "Total semantic router route() calls."),
        ("router_routing_latency_ms", "gauge", "Last end-to-end routing latency ms."),
        ("router_embedding_latency_ms", "gauge", "Last embedding latency ms."),
        ("router_ann_latency_ms", "gauge", "Last ANN search latency ms."),
        ("router_rerank_latency_ms", "gauge", "Last rerank latency ms."),
        ("router_cache_hit_ratio", "gauge", "Embedding cache hit ratio."),
        ("router_avg_confidence", "gauge", "Average routing confidence."),
        ("router_avg_token_reduction", "gauge", "Average token reduction ratio."),
        ("router_index_size", "gauge", "Vectors currently indexed."),
        ("router_tools_registered", "gauge", "Tools in registry."),
        ("neuroswarm_tool_cache_hits", "counter", "Speculative tool-cache hits."),
        ("neuroswarm_tool_cache_misses", "counter", "Speculative tool-cache misses."),
        ("neuroswarm_tool_cache_size", "gauge", "Current speculative tool-cache entry count."),
        ("neuroswarm_tool_cache_hit_rate", "gauge", "Speculative tool-cache hit rate."),
        ("neuroswarm_tool_spec_hit_total", "counter", "Speculative tool-call hits."),
        ("neuroswarm_tool_spec_miss_total", "counter", "Speculative tool-call misses."),
        (
            "neuroswarm_tool_spec_time_saved_ms_total",
            "counter",
            "Milliseconds saved by speculative tool-call overlap.",
        ),
        ("neuroswarm_tool_spec_inflight", "gauge", "In-flight speculative tool executions."),
    )
    for name, mtype, help_text in builtins:
        store.describe(name, mtype, help_text)
    # Materialize tool-spec series so /metrics always exposes the 4 names.
    for name in (
        "neuroswarm_tool_spec_hit_total",
        "neuroswarm_tool_spec_miss_total",
        "neuroswarm_tool_spec_time_saved_ms_total",
    ):
        store.inc(name, 0.0)
    store.set("neuroswarm_tool_spec_inflight", 0.0)
    return store
