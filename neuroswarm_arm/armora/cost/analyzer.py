"""Post-execution analysis: predicted vs actual + RuntimeCostReport builder."""

from __future__ import annotations

from .schemas import (
    CostPrediction,
    LiveCostBreakdown,
    ObservedRuntimeSignals,
    PredictionErrorReport,
    RequestContext,
    RuntimeCostReport,
    safe_div,
)


class DefaultCostAnalyzer:
    def analyze(
        self,
        *,
        context: RequestContext,
        observed: ObservedRuntimeSignals,
        breakdown: LiveCostBreakdown,
        prediction: CostPrediction | None,
        energy_joules: float,
        watts: float,
        carbon_kg: float,
    ) -> RuntimeCostReport:
        total_tokens = int(
            observed.prompt_tokens + observed.completion_tokens + observed.reasoning_tokens
        )
        kv_total = int(observed.kv_cache_hits + observed.kv_cache_misses)
        kv_reuse = safe_div(float(observed.kv_cache_hits), float(kv_total), 0.0)
        draft_total = int(
            observed.accepted_speculative_tokens + observed.rejected_speculative_tokens
        )
        accept_ratio = safe_div(
            float(observed.accepted_speculative_tokens), float(draft_total), 0.0
        )

        latency = float(observed.wall_time_ms or observed.execution_time_ms)
        if latency <= 0:
            latency = (
                float(observed.queue_time_ms)
                + float(observed.planner_time_ms)
                + float(observed.execution_time_ms)
                + float(observed.streaming_time_ms)
            )

        dollars = float(breakdown.total_runtime_cost)
        useful = int(observed.completion_tokens + observed.accepted_speculative_tokens)
        tok_per_s = safe_div(float(useful), max(latency / 1000.0, 1e-9))
        tok_per_watt = safe_div(float(useful), max(watts, 1e-9))
        tok_per_dollar = safe_div(float(useful), max(dollars, 1e-12))

        memory_saved = float(observed.compression_savings_bytes) + (
            float(observed.pages_shared) * 4096.0
        )

        errors = None
        if prediction is not None:
            errors = self._errors(prediction, observed, dollars, latency, energy_joules)

        speculation_savings = -float(breakdown.speculation_net) if breakdown.speculation_net < 0 else 0.0

        return RuntimeCostReport(
            request_id=context.request_id,
            execution_id=context.execution_id,
            workflow_id=context.workflow_id,
            user_id=context.user_id,
            agent_id=context.agent_id,
            planner_id=context.planner_id,
            envelope_id=context.envelope_id,
            tenant_id=context.tenant_id,
            model=context.model,
            model_tier=context.model_tier,
            backend=context.backend,
            quantization=context.quantization,
            prompt_tokens=int(observed.prompt_tokens),
            completion_tokens=int(observed.completion_tokens),
            reasoning_tokens=int(observed.reasoning_tokens),
            total_tokens=total_tokens,
            accepted_speculative_tokens=int(observed.accepted_speculative_tokens),
            rejected_speculative_tokens=int(observed.rejected_speculative_tokens),
            kv_cache_hits=int(observed.kv_cache_hits),
            kv_cache_misses=int(observed.kv_cache_misses),
            kv_reuse_ratio=kv_reuse,
            kv_memory_bytes=float(observed.kv_memory_bytes),
            pages_shared=int(observed.pages_shared),
            migration_events=int(observed.migration_events),
            compression_savings_bytes=float(observed.compression_savings_bytes),
            memory_saved_bytes=memory_saved,
            cpu_seconds=float(observed.cpu_seconds),
            wall_time_ms=float(observed.wall_time_ms),
            planner_time_ms=float(observed.planner_time_ms),
            queue_time_ms=float(observed.queue_time_ms),
            execution_time_ms=float(observed.execution_time_ms),
            streaming_time_ms=float(observed.streaming_time_ms),
            latency_ms=latency,
            slo_latency_ms=float(context.slo_latency_ms),
            peak_memory_bytes=float(observed.peak_memory_bytes),
            average_memory_bytes=float(observed.average_memory_bytes),
            energy_estimate_joules=float(energy_joules),
            watts_estimate=float(watts),
            estimated_dollars=dollars,
            estimated_carbon_kg=float(carbon_kg),
            cost_breakdown=breakdown,
            throughput_tokens_per_s=tok_per_s,
            tokens_per_watt=tok_per_watt,
            tokens_per_dollar=tok_per_dollar,
            quality_score=float(observed.quality_score),
            success=bool(observed.success),
            failure_reason=str(observed.failure_reason or ""),
            retry_count=int(observed.retry_count),
            speculation_acceptance_ratio=accept_ratio,
            verifier_overhead_ms=float(observed.verifier_overhead_ms),
            draft_model_cost_usd=float(observed.draft_model_cost_usd),
            verifier_cost_usd=float(observed.verifier_cost_usd),
            speculation_net_savings_usd=speculation_savings,
            planner_decision_trace=dict(context.planner_decision_trace),
            prediction=prediction,
            prediction_errors=errors,
            hardware_metadata=context.hardware,
            telemetry_metadata=context.telemetry,
            trace_ids=dict(context.trace_ids),
            extensions=dict(context.extensions),
        )

    def _errors(
        self,
        prediction: CostPrediction,
        observed: ObservedRuntimeSignals,
        actual_cost: float,
        actual_latency: float,
        actual_energy: float,
    ) -> PredictionErrorReport:
        cost_err = actual_cost - float(prediction.expected_cost_usd)
        lat_err = actual_latency - float(prediction.expected_latency_ms)
        mem_err = float(observed.peak_memory_bytes) - float(prediction.expected_memory_bytes)
        energy_err = actual_energy - float(prediction.expected_energy_joules)
        cpu_err = float(observed.cpu_seconds) - float(prediction.expected_cpu_seconds)
        token_err = float(
            observed.prompt_tokens + observed.completion_tokens + observed.reasoning_tokens
        ) - (
            float(prediction.expected_prompt_tokens)
            + float(prediction.expected_completion_tokens)
            + float(prediction.expected_reasoning_tokens)
        )
        kv_err = float(observed.kv_memory_bytes) - float(prediction.expected_kv_growth_bytes)

        # Planner accuracy: 1 - mean relative absolute error across key dims
        rels = [
            abs(safe_div(cost_err, max(abs(prediction.expected_cost_usd), 1e-12))),
            abs(safe_div(lat_err, max(abs(prediction.expected_latency_ms), 1e-9))),
            abs(safe_div(energy_err, max(abs(prediction.expected_energy_joules), 1e-9))),
        ]
        mean_rel = sum(rels) / len(rels)
        accuracy = max(0.0, min(1.0, 1.0 - mean_rel))

        return PredictionErrorReport(
            cost_error=cost_err,
            latency_error=lat_err,
            memory_error=mem_err,
            energy_error=energy_err,
            cpu_error=cpu_err,
            token_error=token_err,
            kv_error=kv_err,
            planner_accuracy=accuracy,
            relative_cost_error=safe_div(cost_err, max(abs(prediction.expected_cost_usd), 1e-12)),
            relative_latency_error=safe_div(
                lat_err, max(abs(prediction.expected_latency_ms), 1e-9)
            ),
        )
