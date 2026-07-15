"""Validation engine — multi-metric scorecard + statistical gates."""

from __future__ import annotations

from neuroswarm_arm.evolution.interfaces.validation import ValidationReport, Validator
from neuroswarm_arm.evolution.models.experiment import CandidatePolicy, ExperimentResult
from neuroswarm_arm.evolution.models.policy import RuntimePolicy
from neuroswarm_arm.evolution.validation.stats import effect_size, welch_t_test


class ValidationEngine(Validator):
    SCORECARD_KEYS = (
        "ttft_ms",
        "tps",
        "latency_ms",
        "cost_usd",
        "accept_rate",
        "quality",
        "reasoning_tokens",
        "hallucination",
        "tool_success",
        "kv_usage",
        "memory",
        "cpu",
        "energy",
        "arm_pmu",
        "simd_util",
        "branch_misses",
        "cache_misses",
        "numa_traffic",
        "reward_scalar",
    )

    def __init__(self, *, alpha: float = 0.1, min_improvement: float = 0.01) -> None:
        self.alpha = alpha
        self.min_improvement = min_improvement

    def validate(
        self,
        candidate: CandidatePolicy,
        *,
        baseline: RuntimePolicy | None,
        offline: ExperimentResult | None = None,
        shadow: ExperimentResult | None = None,
    ) -> ValidationReport:
        base_metrics = dict(offline.metrics) if offline and baseline else {}
        if baseline:
            base_metrics.setdefault("reward_scalar", baseline.expected_reward)
            base_metrics.setdefault("accept_rate", float(baseline.parameters.get("accept_threshold", 0.7)))
        cand_metrics: dict[str, float] = {}
        if offline:
            cand_metrics.update({k: float(v) for k, v in offline.metrics.items()})
            cand_metrics.setdefault("reward_scalar", float(offline.offline_score))
        if shadow:
            cand_metrics.update({k: float(v) for k, v in shadow.metrics.items()})
            cand_metrics["reward_scalar"] = float(
                shadow.shadow_score or cand_metrics.get("reward_scalar", 0.0)
            )

        # Synthetic sample series for Welch from scores
        base_series = [base_metrics.get("reward_scalar", 0.0)] * 10
        cand_series = [cand_metrics.get("reward_scalar", 0.0)] * 10
        # Add tiny noise spread for test stability
        base_series = [v + (i - 5) * 0.001 for i, v in enumerate(base_series)]
        cand_series = [v + (i - 5) * 0.001 for i, v in enumerate(cand_series)]

        _, p_value = welch_t_test(cand_series, base_series)
        es = effect_size(cand_series, base_series)
        improvement = cand_metrics.get("reward_scalar", 0.0) - base_metrics.get("reward_scalar", 0.0)
        passed = improvement >= self.min_improvement and (p_value <= self.alpha or improvement >= 2 * self.min_improvement)

        # Fill scorecard keys for export
        for key in self.SCORECARD_KEYS:
            cand_metrics.setdefault(key, 0.0)
            base_metrics.setdefault(key, 0.0)

        return ValidationReport(
            passed=passed,
            p_value=p_value,
            effect_size=es,
            metrics_baseline=base_metrics,
            metrics_candidate=cand_metrics,
            message=(
                f"improvement={improvement:.4f} p={p_value:.3f} effect={es:.3f}"
                if passed
                else f"rejected improvement={improvement:.4f} p={p_value:.3f}"
            ),
        )
