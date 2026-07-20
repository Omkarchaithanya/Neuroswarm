"""AWPP Prometheus / MetricsStore bridge."""

from __future__ import annotations

from typing import Any

METRIC_HELP: dict[str, tuple[str, str]] = {
    "awpp_predictions_total": ("counter", "Total AWPP predictions."),
    "awpp_prediction_skips_total": ("counter", "Predictions skipped (low confidence)."),
    "awpp_prediction_accuracy": ("gauge", "Rolling prediction accuracy."),
    "awpp_false_positives_total": ("counter", "Warm without subsequent use."),
    "awpp_false_negatives_total": ("counter", "Cold start when prediction missed."),
    "awpp_cold_start_reduction_ms": ("gauge", "Estimated cold-start reduction (ms)."),
    "awpp_warm_success_total": ("counter", "Successful warm operations."),
    "awpp_warm_failures_total": ("counter", "Failed warm operations."),
    "awpp_warm_latency_ms": ("gauge", "Last warm operation latency (ms)."),
    "awpp_confidence": ("gauge", "Last prediction confidence."),
    "awpp_entropy": ("gauge", "Last prediction entropy."),
    "awpp_uncertainty": ("gauge", "Last prediction uncertainty."),
    "awpp_queue_depth": ("gauge", "Prewarm scheduler queue depth."),
    "awpp_cpu_time_ms": ("gauge", "AWPP CPU time spent warming (ms)."),
    "awpp_budget_skips_total": ("counter", "Warm ops skipped under CPU/rate budget."),
    "awpp_memory_bytes": ("gauge", "Estimated warm-cache memory bytes."),
    "awpp_cache_hit_rate": ("gauge", "Warm-cache hit rate."),
    "awpp_policy_train_steps_total": ("counter", "Offline policy train steps."),
    "awpp_shadow_divergence_total": ("counter", "Shadow vs active action divergence."),
}


class AWPPMetrics:
    def __init__(self, bridge: Any | None = None) -> None:
        self.bridge = bridge
        self._local: dict[str, float] = {}
        self._correct = 0
        self._total_scored = 0
        self._cache_hits = 0
        self._cache_lookups = 0
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

    def observe_prediction(
        self,
        *,
        confidence: float,
        entropy: float,
        uncertainty: float,
        skipped: bool,
    ) -> None:
        self.inc("awpp_predictions_total")
        if skipped:
            self.inc("awpp_prediction_skips_total")
        self.set("awpp_confidence", confidence)
        self.set("awpp_entropy", entropy)
        self.set("awpp_uncertainty", uncertainty)

    def observe_warm(self, *, success: bool, latency_ms: float) -> None:
        if success:
            self.inc("awpp_warm_success_total")
        else:
            self.inc("awpp_warm_failures_total")
        self.set("awpp_warm_latency_ms", latency_ms)

    def record_accuracy(self, correct: bool) -> None:
        self._total_scored += 1
        if correct:
            self._correct += 1
        if self._total_scored:
            self.set("awpp_prediction_accuracy", self._correct / self._total_scored)

    def record_cache(self, hit: bool) -> None:
        self._cache_lookups += 1
        if hit:
            self._cache_hits += 1
        if self._cache_lookups:
            self.set("awpp_cache_hit_rate", self._cache_hits / self._cache_lookups)

    def snapshot(self) -> dict[str, float]:
        return dict(self._local)
