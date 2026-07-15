"""Live multi-resource runtime cost estimation (optimization signal, not billing)."""

from __future__ import annotations

from typing import Any, Mapping

from .config import RCISRuntimeConfig
from .schemas import LiveCostBreakdown, ObservedRuntimeSignals, safe_div


class DefaultLiveCostEstimator:
    """Estimates C = sum of configurable resource components."""

    def __init__(self, cfg: RCISRuntimeConfig) -> None:
        self.cfg = cfg

    def estimate_energy_joules(
        self,
        *,
        cpu_seconds: float,
        thread_count: int = 1,
        avg_cpu_utilization: float = 0.0,
        measured_joules: float = 0.0,
        watts_estimate: float = 0.0,
    ) -> tuple[float, float]:
        if measured_joules > 0.0:
            watts = watts_estimate if watts_estimate > 0.0 else safe_div(
                measured_joules, max(cpu_seconds, 1e-9)
            )
            return float(measured_joules), float(watts)
        util = avg_cpu_utilization if avg_cpu_utilization > 0.0 else 1.0
        util = max(0.0, min(1.0, util))
        watts = self.cfg.base_watts + (
            max(1, int(thread_count))
            * self.cfg.watts_per_thread
            * self.cfg.numa_efficiency
            * util
        )
        if watts_estimate > 0.0:
            watts = watts_estimate
        joules = max(0.0, float(cpu_seconds)) * watts
        return float(joules), float(watts)

    def estimate(
        self,
        observed: ObservedRuntimeSignals,
        *,
        hardware: Mapping[str, Any] | None = None,
    ) -> LiveCostBreakdown:
        hw = hardware or {}
        cfg = self.cfg
        threads = int(hw.get("thread_count", 1) or 1)

        prompt = float(observed.prompt_tokens)
        completion = float(observed.completion_tokens)
        reasoning = float(observed.reasoning_tokens)
        cache_read = float(observed.cache_read_tokens)
        cache_write = float(observed.cache_write_tokens)
        uncached = max(0.0, prompt - cache_read)

        prompt_cost = (uncached / 1000.0) * cfg.usd_per_1k_prompt
        prompt_cost += (cache_read / 1000.0) * cfg.usd_per_1k_cache_read
        prompt_cost += (cache_write / 1000.0) * cfg.usd_per_1k_cache_write
        completion_cost = (completion / 1000.0) * cfg.usd_per_1k_completion
        reasoning_cost = (reasoning / 1000.0) * cfg.usd_per_1k_reasoning

        cpu_cost = float(observed.cpu_seconds) * cfg.usd_per_cpu_second
        wall_s = max(float(observed.wall_time_ms), float(observed.execution_time_ms)) / 1000.0
        mem_gb = max(float(observed.average_memory_bytes), float(observed.peak_memory_bytes)) / (
            1024**3
        )
        memory_cost = mem_gb * max(wall_s, 1e-6) * cfg.usd_per_gb_memory_second

        joules, _watts = self.estimate_energy_joules(
            cpu_seconds=float(observed.cpu_seconds),
            thread_count=threads,
            avg_cpu_utilization=float(observed.avg_cpu_utilization),
            measured_joules=float(observed.energy_joules),
            watts_estimate=float(observed.watts_estimate),
        )
        energy_cost = joules * cfg.usd_per_joule

        kv_seconds = max(wall_s, 1e-6)
        kv_gb = float(observed.kv_memory_bytes) / (1024**3)
        kv_cost = kv_gb * kv_seconds * cfg.kv_usd_per_gb_s

        tool_cost = float(observed.tool_calls) * cfg.tool_call_usd
        retry_cost = float(observed.retry_count) * cfg.retry_usd
        streaming_cost = (float(observed.streaming_time_ms) / 1000.0) * cfg.streaming_usd_per_second
        planner_cost = float(observed.planner_time_ms) * cfg.planner_usd_per_ms
        queue_cost = float(observed.queue_time_ms) * cfg.queue_usd_per_ms

        accepted = float(observed.accepted_speculative_tokens)
        rejected = float(observed.rejected_speculative_tokens)
        draft_tokens = accepted + rejected
        speculation_net = 0.0
        if draft_tokens > 0 or observed.draft_model_cost_usd or observed.verifier_cost_usd:
            if observed.draft_model_cost_usd or observed.verifier_cost_usd:
                draft_cost = float(observed.draft_model_cost_usd)
                verify_cost = float(observed.verifier_cost_usd)
            else:
                draft_cost = (draft_tokens / 1000.0) * cfg.usd_per_1k_completion * cfg.draft_cost_factor
                verify_cost = (draft_tokens / 1000.0) * cfg.usd_per_1k_completion * cfg.verify_cost_factor
            saved = (accepted / 1000.0) * cfg.usd_per_1k_completion * cfg.saved_decode_factor
            # Net can be negative → savings (optimization signal)
            speculation_net = draft_cost + verify_cost - saved
            speculation_net += (rejected / 1000.0) * cfg.usd_per_1k_rejected_draft
            speculation_net += (accepted / 1000.0) * cfg.usd_per_1k_accepted_draft * 0.0

        return LiveCostBreakdown(
            prompt_cost=prompt_cost,
            completion_cost=completion_cost,
            reasoning_cost=reasoning_cost,
            cpu_cost=cpu_cost,
            memory_cost=memory_cost,
            energy_cost=energy_cost,
            kv_cost=kv_cost,
            tool_cost=tool_cost,
            retry_cost=retry_cost,
            streaming_cost=streaming_cost,
            planner_cost=planner_cost,
            queue_cost=queue_cost,
            speculation_net=speculation_net,
        )


class PsutilEnergySampler:
    """Fallback energy estimation using psutil when Performix/PMU unavailable."""

    def __init__(self, cfg: RCISRuntimeConfig) -> None:
        self.cfg = cfg

    def sample_utilization(self) -> float:
        try:
            import psutil  # type: ignore

            return float(psutil.cpu_percent(interval=0.0)) / 100.0
        except Exception:
            return 0.0

    def sample_rss_bytes(self) -> float:
        try:
            import psutil  # type: ignore

            return float(psutil.Process().memory_info().rss)
        except Exception:
            return 0.0
