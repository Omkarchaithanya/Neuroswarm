"""Orchestrate policy, model, backend, and speculation into a full plan."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..interfaces.types import (
    ExecutionPlan,
    InferenceRequest,
    KVTransferMode,
    PDMode,
    PoolKind,
)

if TYPE_CHECKING:
    from ..routing.backend_selector import BackendSelector
    from ..routing.model_router import ModelRouter
    from ..routing.speculation_router import SpeculationRouter
    from .execution_planner import ExecutionPlanner
    from .policy_engine import PolicyEngine


class DecisionEngine:
    """Top-level planning: skeleton → model → backend → speculation flags."""

    def __init__(
        self,
        policy_engine: PolicyEngine,
        model_router: ModelRouter,
        backend_selector: BackendSelector,
        speculation_router: SpeculationRouter,
        planner: ExecutionPlanner,
        *,
        config: Any | None = None,
    ) -> None:
        self.policy_engine = policy_engine
        self.model_router = model_router
        self.backend_selector = backend_selector
        self.speculation_router = speculation_router
        self.planner = planner
        self.config = config

    def decide(self, req: InferenceRequest) -> ExecutionPlan:
        plan = self.planner.plan(req)

        policy = self.policy_engine.apply(req, plan.workload)
        plan.latency_sla_ms = float(policy["latency_sla_ms"])
        plan.cost_budget_usd = float(policy["cost_budget_usd"])
        plan.use_cascade = bool(policy["use_cascade"])
        if not plan.model:
            plan.model = str(policy["preferred_model"])

        model = self.model_router.select_model(req, plan)
        plan.model = model

        backend = self.backend_selector.select(req, plan)
        plan.backend = backend

        self.speculation_router.apply(plan)

        plan.stream = bool(req.stream)
        plan.prefill_pool = PoolKind.PREFILL
        plan.decode_pool = PoolKind.DECODE

        cfg = self.config
        pd_mode_raw = str(getattr(cfg, "pd_mode", "off") or "off").lower()
        try:
            plan.pd_mode = PDMode(pd_mode_raw)
        except ValueError:
            plan.pd_mode = PDMode.OFF
        plan.prefill_backend = str(
            getattr(cfg, "prefill_backend", "") or "sglang"
        )
        plan.decode_backend = str(
            getattr(cfg, "decode_backend", "") or "llama_cpp"
        )
        min_tokens = int(getattr(cfg, "pd_min_prompt_tokens", 64) or 64)
        long_enough = req.prompt_length >= min_tokens
        plan.pd_enabled = plan.pd_mode in {PDMode.SOFT, PDMode.NATIVE} and long_enough
        if plan.pd_mode == PDMode.NATIVE:
            plan.transfer_mode = KVTransferMode.NATIVE_SGLANG
        elif plan.pd_enabled:
            plan.transfer_mode = KVTransferMode.RECOMPUTE
        else:
            plan.transfer_mode = KVTransferMode.RECOMPUTE

        # Soft/native PD owns the path; skip cascade to avoid double generation.
        if plan.pd_enabled:
            plan.use_cascade = False

        cost_meta: dict[str, Any] = {}
        if plan.use_cascade:
            # Heuristic CostRouter: semantic tool confidence → cascade start tier.
            # Never hardcode tier=1 when tool_confidence is low (escalate honesty).
            try:
                from neuroswarm_arm.runtime.router.cost_router import CostRouter

                query = req.prompt_text
                decision = CostRouter().route(
                    query,
                    tool_confidence=float(req.tool_confidence or 0.0),
                    plan_state={
                        "tool_high_confidence": bool(req.tool_high_confidence),
                        "agent_role": req.agent_role,
                    },
                )
                plan.cascade_start_tier = int(decision.tier)
                if decision.quant and not plan.quant:
                    plan.quant = decision.quant
                cost_meta = decision.as_dict()
            except Exception:
                plan.cascade_start_tier = 1
                cost_meta = {"tier": 1, "reason": "cost_router_fallback"}
        else:
            plan.cascade_start_tier = _tier_from_name(plan.model)

        if not plan.fallbacks:
            plan.fallbacks = _default_fallbacks(plan.model)

        # AQR cascade_profiles → plan metadata for ASCR policy / quant floors.
        try:
            from neuroswarm_arm.runtime.aqr import plan_metadata_from_profiles

            tier = int(plan.cascade_start_tier or _tier_from_name(plan.model) or 1)
            aqr_meta = plan_metadata_from_profiles(tier)
            if aqr_meta:
                plan.metadata.update(aqr_meta)
                preferred = ""
                qmeta = aqr_meta.get("quant")
                if isinstance(qmeta, dict):
                    preferred = str(qmeta.get("aqr_preferred") or "")
                elif qmeta:
                    preferred = str(qmeta)
                if preferred and not plan.quant:
                    plan.quant = preferred
        except Exception:
            pass

        plan.metadata.setdefault("decision", {})
        plan.metadata["decision"].update(
            {
                "model": plan.model,
                "backend": plan.backend,
                "use_cascade": plan.use_cascade,
                "pd_enabled": plan.pd_enabled,
                "pd_mode": plan.pd_mode.value,
                "prefill_backend": plan.prefill_backend,
                "decode_backend": plan.decode_backend,
                "transfer_mode": plan.transfer_mode.value,
                "speculation": plan.speculation,
                "self_speculation": plan.self_speculation,
                "cascade_start_tier": int(plan.cascade_start_tier or 1),
                "tool_confidence": float(req.tool_confidence or 0.0),
                "cost_router": cost_meta,
            }
        )
        if cost_meta:
            plan.metadata["cost_router"] = cost_meta

        # Feed router_result into plan.metadata["router"] (wiring matrix L2).
        rr = getattr(req, "router_result", None)
        if rr is None:
            rr = (req.baggage or {}).get("router_result")
        if rr is not None:
            plan.router_result = rr  # type: ignore[assignment]
            if hasattr(rr, "to_dict"):
                plan.metadata["router"] = rr.to_dict()
            elif isinstance(rr, dict):
                plan.metadata["router"] = dict(rr)
            else:
                plan.metadata["router"] = {
                    "confidence_top1": float(getattr(rr, "confidence_top1", 0.0) or 0.0),
                    "tool_ids": list(getattr(rr, "tool_ids", []) or []),
                    "tool_names": list(getattr(rr, "tool_names", []) or []),
                }
        return plan


def _tier_from_name(name: str) -> int:
    text = (name or "").lower()
    for i in (1, 2, 3):
        if f"tier{i}" in text:
            return i
    return 2


def _default_fallbacks(model: str) -> list[str]:
    order = ["tier1", "tier2", "tier3"]
    if model in order:
        idx = order.index(model)
        return order[idx + 1 :] + [m for m in order[:idx] if m != model]
    return [m for m in order if m != model]
