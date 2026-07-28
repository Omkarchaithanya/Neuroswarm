"""DIPA Prometheus / MetricsStore bridge."""

from __future__ import annotations

from typing import Any

METRIC_HELP: dict[str, tuple[str, str]] = {
    "dipa_requests_total": ("counter", "Total DIPA inference requests."),
    "dipa_requests_failed_total": ("counter", "Failed DIPA inference requests."),
    "dipa_ttft_ms": ("gauge", "Time to first token (ms)."),
    "dipa_latency_ms": ("gauge", "End-to-end inference latency (ms)."),
    "dipa_prefill_tps": ("gauge", "Prefill tokens per second."),
    "dipa_decode_tps": ("gauge", "Decode tokens per second."),
    "dipa_tokens_per_sec": ("gauge", "Overall tokens per second."),
    "dipa_cascade_hit_rate": ("gauge", "Fraction of requests finishing at tier1."),
    "dipa_cascade_tier_transitions_total": ("counter", "Cascade tier escalations."),
    "dipa_quant_usage_total": ("counter", "Quantization selections."),
    "dipa_retries_total": ("counter", "Retry attempts."),
    "dipa_timeouts_total": ("counter", "Timeouts."),
    "dipa_fallbacks_total": ("counter", "Fallback activations."),
    "dipa_streaming_latency_ms": ("gauge", "Streaming delivery latency."),
    "dipa_backend_utilization": ("gauge", "Backend utilization estimate."),
    "dipa_cpu_utilization": ("gauge", "Process CPU utilization."),
    "dipa_memory_bytes": ("gauge", "Process RSS bytes."),
    "dipa_numa_locality": ("gauge", "NUMA locality score (1.0 = local)."),
    "dipa_affinity_bind_total": ("counter", "Successful affinity binds."),
    "dipa_prefix_hit_ratio": ("gauge", "Prefix cache hit ratio."),
    "dipa_prefix_hit_tokens": ("gauge", "Prefix cache hit tokens."),
    "dipa_batch_size": ("gauge", "Last PD / batch size."),
    "dipa_chunk_count": ("gauge", "Prefill chunk count."),
    "dipa_prefill_ms": ("gauge", "Prefill latency (ms)."),
    "dipa_kv_transfer_mode": ("gauge", "KV transfer mode code (1=native,2=recompute,3=unavailable)."),
    "dipa_recompute_tokens": ("gauge", "Tokens recomputed on decode after heterogeneous handoff."),
}


class DIPAMetrics:
    def __init__(self, bridge: Any | None = None) -> None:
        self.bridge = bridge
        self._local: dict[str, float] = {}
        self._tier1 = 0
        self._tier_n = 0
        if bridge is not None:
            for name, (mtype, help_text) in METRIC_HELP.items():
                describe = getattr(bridge, "describe", None)
                if callable(describe):
                    describe(name, mtype, help_text)

    def inc(self, name: str, value: float = 1.0) -> None:
        self._local[name] = self._local.get(name, 0.0) + value
        if self.bridge is not None:
            self.bridge.inc(name, value)

    def set(self, name: str, value: float) -> None:
        self._local[name] = value
        if self.bridge is not None:
            self.bridge.set(name, value)

    def observe(self, name: str, value: float) -> None:
        self.set(name, value)

    def describe(self, name: str, metric_type: str, help_text: str) -> None:
        """Forward ASCR/DIPA metric descriptions to the root MetricsStore/RMF."""
        if self.bridge is not None and hasattr(self.bridge, "describe"):
            try:
                self.bridge.describe(name, metric_type, help_text)
            except Exception:
                pass

    def record_inference(
        self,
        *,
        latency_ms: float,
        ttft_ms: float,
        tier: int,
        quant: str,
        backend: str,
        workload: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        self.inc("dipa_requests_total")
        self.set("dipa_latency_ms", latency_ms)
        self.set("dipa_ttft_ms", ttft_ms)
        self.inc("dipa_quant_usage_total")
        if tier <= 1:
            self._tier1 += 1
        else:
            self._tier_n += 1
            self.inc("dipa_cascade_tier_transitions_total")
        total = self._tier1 + self._tier_n
        if total:
            self.set("dipa_cascade_hit_rate", self._tier1 / total)
        elapsed_s = max(latency_ms / 1000.0, 1e-6)
        self.set("dipa_tokens_per_sec", completion_tokens / elapsed_s)
        if prompt_tokens:
            self.set("dipa_prefill_tps", prompt_tokens / elapsed_s)
        if completion_tokens:
            self.set("dipa_decode_tps", completion_tokens / elapsed_s)
        self.set("dipa_backend_utilization", 0.0)
        self.set(f"dipa_last_tier", float(tier))
        # 1.0 on single-UMA Axion is trivial locality, not NUMA-split proof.
        # See neuroswarm_cross_numa_applicable / nexus_hw_numa_nodes gauges.
        self.set("dipa_numa_locality", 1.0)

    def record_prefill(
        self,
        *,
        latency_ms: float,
        prefix_tokens: int,
        hit_tokens: int,
        backend: str,
    ) -> None:
        self.set("dipa_prefill_ms", float(latency_ms))
        if latency_ms > 0 and prefix_tokens:
            self.set("dipa_prefill_tps", prefix_tokens / max(latency_ms / 1000.0, 1e-6))
        self.set("dipa_prefix_hit_tokens", float(hit_tokens))
        _ = backend

    def record_decode(
        self,
        *,
        latency_ms: float,
        completion_tokens: int,
        recompute_tokens: int,
        transfer_mode: str,
        backend: str,
    ) -> None:
        if latency_ms > 0 and completion_tokens:
            self.set("dipa_decode_tps", completion_tokens / max(latency_ms / 1000.0, 1e-6))
        self.set("dipa_recompute_tokens", float(recompute_tokens))
        self.set(
            "dipa_kv_transfer_mode",
            {"native_sglang": 1.0, "recompute": 2.0, "unavailable": 3.0}.get(
                transfer_mode, 0.0
            ),
        )
        _ = backend

    def record_prefix(
        self, *, hit_tokens: int, total_tokens: int, hit_ratio: float
    ) -> None:
        self.set("dipa_prefix_hit_tokens", float(hit_tokens))
        self.set("dipa_prefix_hit_ratio", float(hit_ratio))
        _ = total_tokens

    def snapshot(self) -> dict[str, float]:
        return dict(self._local)
