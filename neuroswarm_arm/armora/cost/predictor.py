"""Pre-execution cost / resource prediction."""

from __future__ import annotations

from typing import Any

from .config import RCISRuntimeConfig
from .schemas import CostPrediction, RequestContext, safe_div


class DefaultCostPredictor:
    """Predict expected latency/cost/memory/CPU/energy/tokens/KV before execution."""

    def __init__(
        self,
        cfg: RCISRuntimeConfig,
        *,
        history_provider: Any | None = None,
    ) -> None:
        self.cfg = cfg
        self.history_provider = history_provider

    def predict(self, context: RequestContext) -> CostPrediction:
        cfg = self.cfg
        prompt_est = float(context.prompt_token_estimate or 0)
        if prompt_est <= 0:
            prompt_est = 512.0

        hist = self._history_priors(context)
        completion = float(hist.get("completion_tokens", cfg.default_tokens_completion))
        reasoning = float(hist.get("reasoning_tokens", cfg.default_tokens_reasoning))
        cpu_s = float(hist.get("cpu_seconds", cfg.default_cpu_seconds))
        mem = float(hist.get("memory_bytes", cfg.default_memory_bytes))
        kv_growth = float(hist.get("kv_growth_bytes", cfg.default_kv_growth_bytes))
        energy = float(hist.get("energy_joules", cfg.default_energy_joules))

        latency = float(
            hist.get(
                "latency_ms",
                cfg.default_latency_ms
                + prompt_est * cfg.latency_per_prompt_token_ms
                + completion * cfg.latency_per_completion_token_ms,
            )
        )

        # Cost prior from configurable rates (mirrors live estimator components)
        cost = 0.0
        cost += (prompt_est / 1000.0) * cfg.usd_per_1k_prompt
        cost += (completion / 1000.0) * cfg.usd_per_1k_completion
        cost += (reasoning / 1000.0) * cfg.usd_per_1k_reasoning
        cost += cpu_s * cfg.usd_per_cpu_second
        cost += energy * cfg.usd_per_joule
        cost += (kv_growth / (1024**3)) * (latency / 1000.0) * cfg.kv_usd_per_gb_s
        cost += cfg.planner_usd_per_ms * 5.0  # nominal planner overhead prior

        confidence = 0.45 if not hist else min(0.9, 0.5 + 0.05 * float(hist.get("samples", 1)))

        return CostPrediction(
            request_id=context.request_id,
            execution_id=context.execution_id,
            expected_latency_ms=latency,
            expected_cost_usd=cost,
            expected_memory_bytes=mem,
            expected_cpu_seconds=cpu_s,
            expected_energy_joules=energy,
            expected_prompt_tokens=prompt_est,
            expected_completion_tokens=completion,
            expected_reasoning_tokens=reasoning,
            expected_kv_growth_bytes=kv_growth,
            confidence=confidence,
            extensions={
                "p90_latency_ms": latency * cfg.prediction_p90_factor,
                "p90_cost_usd": cost * cfg.prediction_p90_factor,
                "backend": context.backend,
                "quantization": context.quantization,
                "model_tier": context.model_tier,
            },
        )

    def _history_priors(self, context: RequestContext) -> dict[str, float]:
        if self.history_provider is None:
            return {}
        try:
            reports = self.history_provider.query_reports(
                backend=context.backend,
                quantization=context.quantization,
                model_tier=context.model_tier,
                limit=min(50, self.cfg.history_window),
            )
        except Exception:
            return {}
        if not reports:
            return {}
        n = float(len(reports))
        return {
            "samples": n,
            "latency_ms": safe_div(sum(r.latency_ms for r in reports), n),
            "completion_tokens": safe_div(sum(r.completion_tokens for r in reports), n),
            "reasoning_tokens": safe_div(sum(r.reasoning_tokens for r in reports), n),
            "cpu_seconds": safe_div(sum(r.cpu_seconds for r in reports), n),
            "memory_bytes": safe_div(sum(r.peak_memory_bytes for r in reports), n),
            "kv_growth_bytes": safe_div(sum(r.kv_memory_bytes for r in reports), n),
            "energy_joules": safe_div(sum(r.energy_estimate_joules for r in reports), n),
            "cost_usd": safe_div(sum(r.estimated_dollars for r in reports), n),
        }
