"""ASCR Prometheus metrics (+ dipa_cascade aliases)."""

from __future__ import annotations

from typing import Any, Mapping

ASCR_METRIC_HELP: dict[str, tuple[str, str]] = {
    "ascr_acceptance_rate": ("gauge", "Token/prefix acceptance rate."),
    "ascr_rejection_rate": ("gauge", "Rejection rate."),
    "ascr_rollback_rate": ("gauge", "Partial rollback / reject rate."),
    "ascr_draft_tps": ("gauge", "Draft tokens per second."),
    "ascr_verifier_tps": ("gauge", "Verifier tokens per second."),
    "ascr_effective_tps": ("gauge", "Effective accepted tokens per second."),
    "ascr_speculation_gain": ("gauge", "Estimated target forwards saved (0 in text-agree)."),
    "ascr_text_agreement": ("gauge", "Text-agreement score when logits unavailable."),
    "ascr_saved_forward_passes": ("counter", "Saved target forward passes."),
    "ascr_saved_verifier_calls": ("counter", "Saved verifier calls via early accept."),
    "ascr_cpu_utilization": ("gauge", "CPU utilization snapshot."),
    "ascr_numa_locality": ("gauge", "NUMA locality score."),
    "ascr_cache_hit": ("gauge", "Cache hit ratio."),
    "ascr_kv_reuse": ("gauge", "KV reuse ratio."),
    "ascr_memory_bytes": ("gauge", "ASCR-attributed memory bytes."),
    "ascr_cost_per_token": ("gauge", "Estimated cost per token."),
    "ascr_energy_per_token": ("gauge", "Estimated energy per token (placeholder)."),
    "ascr_rounds_total": ("counter", "ASCR propose/verify rounds."),
    "ascr_escalations_total": ("counter", "Escalation edge traversals."),
    "ascr_quality_cascade_total": ("counter", "Requests in quality-cascade mode."),
    "ascr_skip_spec_total": (
        "counter",
        "Speculation skipped by cost model (use ascr_skip_spec_total{reason=...} keys).",
    ),
    "kleidiai_kernel_in_use": ("gauge", "1 if a specific KleidiAI kernel is identified."),
    "kleidiai_sme2_available": ("gauge", "1 if SME2 is available on the host."),
}


class ASCRMetrics:
    def __init__(self, bridge: Any | None = None, *, alias_dipa: bool = True) -> None:
        self.bridge = bridge
        self.alias_dipa = alias_dipa
        self._local: dict[str, float] = {}
        self._accepted = 0.0
        self._rejected = 0.0
        self._tier1 = 0
        self._tier_n = 0
        if bridge is not None:
            describe = getattr(bridge, "describe", None)
            if callable(describe):
                for name, (mtype, help_text) in ASCR_METRIC_HELP.items():
                    describe(name, mtype, help_text)

    def inc(self, name: str, value: float = 1.0) -> None:
        self._local[name] = self._local.get(name, 0.0) + value
        if self.bridge is not None and hasattr(self.bridge, "inc"):
            self.bridge.inc(name, value)

    def set(self, name: str, value: float) -> None:
        self._local[name] = value
        if self.bridge is not None and hasattr(self.bridge, "set"):
            self.bridge.set(name, value)

    def snapshot(self) -> dict[str, float]:
        return dict(self._local)

    def record_round(
        self,
        *,
        accepted_tokens: int,
        rejected_tokens: int,
        draft_tokens: int,
        latency_ms: float,
        tier_used: int,
        mode: str,
        numa_locality: float = 1.0,
        cpu: float = 0.5,
        cache_hit: float = 0.0,
        kv_reuse: float = 0.0,
        logits_available: bool = True,
        text_agreement: float | None = None,
    ) -> None:
        self.inc("ascr_rounds_total")
        self._accepted += accepted_tokens
        self._rejected += rejected_tokens
        total = self._accepted + self._rejected
        if total:
            self.set("ascr_acceptance_rate", self._accepted / total)
            self.set("ascr_rejection_rate", self._rejected / total)
            self.set("ascr_rollback_rate", self._rejected / total)

        elapsed_s = max(latency_ms / 1000.0, 1e-6)
        if draft_tokens:
            self.set("ascr_draft_tps", draft_tokens / elapsed_s)
        if accepted_tokens:
            self.set("ascr_effective_tps", accepted_tokens / elapsed_s)
            self.set("ascr_verifier_tps", accepted_tokens / elapsed_s)

        interim = mode in {"quality_cascade", "text_agree"} or not logits_available
        if text_agreement is not None:
            self.set("ascr_text_agreement", float(text_agreement))
        # Honesty: do not inflate speculative gain without logits / true speculation.
        if interim:
            self.set("ascr_speculation_gain", 0.0)
        else:
            gain = accepted_tokens / max(1, draft_tokens) if draft_tokens else 0.0
            self.set("ascr_speculation_gain", gain)
            if accepted_tokens > 0 and draft_tokens > accepted_tokens:
                self.inc("ascr_saved_forward_passes", 0.5)
            elif accepted_tokens == draft_tokens and draft_tokens > 0:
                self.inc("ascr_saved_forward_passes", 1.0)

        self.set("ascr_cpu_utilization", cpu)
        self.set("ascr_numa_locality", numa_locality)
        self.set("ascr_cache_hit", cache_hit)
        self.set("ascr_kv_reuse", kv_reuse)

        if mode == "quality_cascade":
            self.inc("ascr_quality_cascade_total")

        if tier_used <= 1:
            self._tier1 += 1
        else:
            self._tier_n += 1
            self.inc("ascr_escalations_total")

        if self.alias_dipa:
            total_req = self._tier1 + self._tier_n
            if total_req and self.bridge is not None:
                if hasattr(self.bridge, "set"):
                    self.bridge.set("dipa_cascade_hit_rate", self._tier1 / total_req)
                if tier_used > 1 and hasattr(self.bridge, "inc"):
                    self.bridge.inc("dipa_cascade_tier_transitions_total")

    def emit_event(self, event: str, fields: Mapping[str, float]) -> None:
        # Optional callback-style bridge used by legacy CascadeEngine metrics.
        if callable(self.bridge):
            self.bridge(event, fields)

    def record_kleidiai_kernel(self, kernel_name: str, sme2: bool) -> None:
        """Record KleidiAI kernel identity and SME2 availability."""
        self.set("kleidiai_kernel_in_use", 1.0 if kernel_name else 0.0)
        self.set("kleidiai_sme2_available", 1.0 if sme2 else 0.0)
