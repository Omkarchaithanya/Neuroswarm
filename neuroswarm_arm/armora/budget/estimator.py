"""Resource estimators — cost, energy, KV, plan actions."""

from __future__ import annotations

from typing import Any, Mapping

from .config import BudgetRuntimeConfig
from .schemas import DimensionDelta, PlanAction, PlanActionKind, ResourceProjection


class DefaultCostModel:
    def __init__(self, cfg: BudgetRuntimeConfig) -> None:
        self.cfg = cfg

    def project(
        self,
        op: Mapping[str, Any],
        hardware: Mapping[str, Any] | None = None,
        cache_state: Mapping[str, Any] | None = None,
    ) -> ResourceProjection:
        del hardware
        cache_state = cache_state or {}
        prompt = float(op.get("prompt_tokens", 0))
        completion = float(op.get("completion_tokens", 0))
        reasoning = float(op.get("reasoning_tokens", 0))
        cache_read = float(op.get("cache_read_tokens", cache_state.get("cache_read_tokens", 0)))
        cache_write = float(
            op.get("cache_write_tokens", cache_state.get("cache_write_tokens", 0))
        )
        uncached = max(0.0, prompt - cache_read)
        tools = float(op.get("tool_calls", 0))
        kv_bytes = float(op.get("kv_bytes", 0))
        kv_seconds = float(op.get("kv_seconds", 1.0))
        retries = float(op.get("retries", 0))
        speculate_draft = float(op.get("draft_tokens", 0))
        planner = float(op.get("planner", 0))

        cfg = self.cfg
        cost = 0.0
        cost += (uncached / 1000.0) * cfg.usd_per_1k_prompt
        cost += (cache_read / 1000.0) * cfg.usd_per_1k_cache_read
        cost += (cache_write / 1000.0) * cfg.usd_per_1k_cache_write
        cost += (completion / 1000.0) * cfg.usd_per_1k_completion
        cost += (reasoning / 1000.0) * cfg.usd_per_1k_reasoning
        cost += tools * cfg.tool_call_usd
        cost += (kv_bytes / (1024**3)) * kv_seconds * cfg.kv_usd_per_gb_s
        cost += retries * cfg.tool_call_usd * 0.5
        # Speculative net: draft cheap + verify premium − saved decode heuristic
        if speculate_draft > 0:
            draft_cost = (speculate_draft / 1000.0) * cfg.usd_per_1k_completion * 0.25
            verify_cost = (speculate_draft / 1000.0) * cfg.usd_per_1k_completion * 0.15
            saved = (speculate_draft / 1000.0) * cfg.usd_per_1k_completion * 0.5
            cost += max(0.0, draft_cost + verify_cost - saved)
        if planner:
            cost += cfg.planner_overhead_usd

        p50 = DimensionDelta(
            values={
                "cost_usd": cost,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "reasoning_tokens": reasoning,
                "tokens_total": prompt + completion + reasoning,
                "tool_calls": tools,
                "kv_bytes": kv_bytes,
            }
        )
        p90_vals = {k: v * 1.25 for k, v in p50.values.items()}
        return ResourceProjection(
            p50=p50,
            p90=DimensionDelta(values=p90_vals),
            confidence=0.75,
        )


class DefaultEnergyModel:
    def __init__(self, cfg: BudgetRuntimeConfig) -> None:
        self.cfg = cfg

    def project(
        self,
        *,
        cpu_seconds: float,
        thread_count: int = 1,
        numa_node: int = 0,
        hardware: Mapping[str, Any] | None = None,
    ) -> ResourceProjection:
        del numa_node, hardware
        watts = self.cfg.base_watts + (
            max(1, int(thread_count)) * self.cfg.watts_per_thread * self.cfg.numa_efficiency
        )
        joules = max(0.0, float(cpu_seconds)) * watts
        d = DimensionDelta(values={"energy_joules": joules, "cpu_seconds": float(cpu_seconds)})
        return ResourceProjection(
            p50=d,
            p90=DimensionDelta(values={"energy_joules": joules * 1.2, "cpu_seconds": float(cpu_seconds) * 1.2}),
            confidence=0.6,
        )


class DefaultEstimator:
    def __init__(
        self,
        cfg: BudgetRuntimeConfig,
        *,
        cost_model: DefaultCostModel | None = None,
        energy_model: DefaultEnergyModel | None = None,
    ) -> None:
        self.cfg = cfg
        self.cost_model = cost_model or DefaultCostModel(cfg)
        self.energy_model = energy_model or DefaultEnergyModel(cfg)

    def project_kv(
        self,
        *,
        layers: int,
        kv_heads: int,
        head_dim: int,
        seq_len: int,
        batch: int = 1,
        elem_size: int = 2,
    ) -> ResourceProjection:
        raw = (
            2
            * int(layers)
            * int(kv_heads)
            * int(head_dim)
            * int(seq_len)
            * int(batch)
            * int(elem_size)
        )
        bytes_ = float(raw) * float(self.cfg.kv_paging_overhead)
        pages = max(1.0, bytes_ / 4096.0)
        d50 = DimensionDelta(values={"kv_bytes": bytes_, "memory_pages": pages})
        d90 = DimensionDelta(values={"kv_bytes": bytes_ * 1.1, "memory_pages": pages * 1.1})
        return ResourceProjection(p50=d50, p90=d90, confidence=0.85)

    def project_action(
        self,
        action: PlanAction,
        *,
        hardware: Mapping[str, Any] | None = None,
        cache_state: Mapping[str, Any] | None = None,
    ) -> ResourceProjection:
        hardware = hardware or {}
        kind = action.kind
        params = action.params
        if kind is PlanActionKind.TIER:
            tier = int(params.get("tier", 1))
            mult = {1: 0.4, 2: 1.0, 3: 2.5}.get(tier, 1.0)
            completion = 256.0 * mult
            cost_op = {
                "prompt_tokens": 512,
                "completion_tokens": completion,
                "reasoning_tokens": 64 if tier >= 2 else 0,
            }
            proj = self.cost_model.project(cost_op, hardware, cache_state)
            energy = self.energy_model.project(
                cpu_seconds=0.5 * mult,
                thread_count=int(hardware.get("threads", 4)),
            )
            return ResourceProjection(
                p50=proj.p50.merge(energy.p50),
                p90=proj.p90.merge(energy.p90),
                confidence=min(proj.confidence, energy.confidence),
            )
        if kind is PlanActionKind.QUANT:
            quant = str(params.get("quantization", "q4")).lower()
            mult = {"fp16": 2.0, "q8": 1.2, "q5": 1.0, "q4": 0.8, "q3": 0.6}.get(quant, 1.0)
            base = self.cost_model.project(
                {"prompt_tokens": 512, "completion_tokens": 256 * mult},
                hardware,
                cache_state,
            )
            mem = DimensionDelta(values={"memory_bytes": 2_000_000_000 * mult})
            return ResourceProjection(
                p50=base.p50.merge(mem),
                p90=base.p90.merge(DimensionDelta(values={"memory_bytes": 2_000_000_000 * mult * 1.2})),
                confidence=0.7,
            )
        if kind is PlanActionKind.REASONING:
            tokens = int(params.get("tokens", 256))
            return self.cost_model.project(
                {"reasoning_tokens": tokens, "completion_tokens": 0, "prompt_tokens": 0},
                hardware,
                cache_state,
            )
        if kind is PlanActionKind.SPECULATE:
            draft = int(params.get("draft_tokens", 8))
            return self.cost_model.project(
                {"draft_tokens": draft, "completion_tokens": draft},
                hardware,
                cache_state,
            )
        if kind is PlanActionKind.TOOL_CALL:
            cost = float(params.get("cost_usd", self.cfg.tool_call_usd))
            d = DimensionDelta(values={"tool_calls": 1.0, "cost_usd": cost})
            return ResourceProjection(p50=d, p90=d, confidence=0.9)
        if kind is PlanActionKind.RETRY:
            d = DimensionDelta(values={"retries": 1.0, "cost_usd": self.cfg.tool_call_usd * 0.5})
            return ResourceProjection(p50=d, p90=DimensionDelta(values={"retries": 1.0, "cost_usd": self.cfg.tool_call_usd}), confidence=0.8)
        if kind is PlanActionKind.FRONTIER_MODEL:
            return self.project_action(PlanAction.tier(3), hardware=hardware, cache_state=cache_state)
        if kind is PlanActionKind.EXPAND_CONTEXT:
            tokens = int(params.get("tokens", 1024))
            return self.cost_model.project({"prompt_tokens": tokens}, hardware, cache_state)
        if kind is PlanActionKind.BATCH:
            size = int(params.get("size", 1))
            return self.cost_model.project(
                {"prompt_tokens": 256 * size, "completion_tokens": 128 * size},
                hardware,
                cache_state,
            )
        if kind is PlanActionKind.STREAM:
            d = DimensionDelta(values={"streaming_ms": float(params.get("ms", 1000))})
            return ResourceProjection(p50=d, p90=d, confidence=0.7)
        # CUSTOM
        return self.cost_model.project(params, hardware, cache_state)
