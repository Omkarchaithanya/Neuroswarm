"""Budget optimizer — configurable degrade ladder under multi-objective constraints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .config import BudgetRuntimeConfig
from .envelope import BudgetEnvelope
from .schemas import AdmitDecision, AffordDecision, DimensionDelta, PlanAction
from .tracker import BudgetRuntimeState
from .validator import BudgetValidator


DegradeFn = Callable[[BudgetEnvelope, BudgetRuntimeState, dict[str, Any]], dict[str, float]]


@dataclass
class OptimizeResult:
    decision: AdmitDecision
    plan_adjustments: dict[str, Any] = field(default_factory=dict)
    actions_taken: list[str] = field(default_factory=list)


class BudgetOptimizer:
    def __init__(
        self,
        cfg: BudgetRuntimeConfig,
        *,
        validator: BudgetValidator | None = None,
        estimator: Any | None = None,
    ) -> None:
        self.cfg = cfg
        self.validator = validator or BudgetValidator()
        self.estimator = estimator
        self._handlers: dict[str, DegradeFn] = {
            "lower_tier": self._lower_tier,
            "lower_quant": self._lower_quant,
            "cut_reasoning": self._cut_reasoning,
            "trim_context": self._trim_context,
            "disable_speculation": self._disable_speculation,
            "drop_tools": self._drop_tools,
            "cut_retries": self._cut_retries,
            "abort": self._abort,
        }

    def can_afford(
        self,
        state: BudgetRuntimeState,
        action: PlanAction,
        *,
        projected: DimensionDelta | None = None,
    ) -> AffordDecision:
        if projected is None:
            if self.estimator is None:
                projected = DimensionDelta()
            else:
                proj = self.estimator.project_action(action)
                projected = proj.pick(self.cfg.reserve_percentile)
        blocking: list[str] = []
        for name, need in projected.values.items():
            if name not in state.categories:
                continue
            if float(need) > state.categories[name].remaining + 1e-12:
                if state.categories[name].hardness.value == "hard":
                    blocking.append(name)
        return AffordDecision(
            affordable=len(blocking) == 0,
            action=action.kind.value,
            projected=projected,
            blocking_dims=blocking,
            confidence=0.8,
            message="" if not blocking else f"blocked by: {', '.join(blocking)}",
        )

    def optimize(
        self,
        envelope: BudgetEnvelope,
        state: BudgetRuntimeState,
        *,
        projected: Mapping[str, float] | None = None,
        plan: dict[str, Any] | None = None,
    ) -> OptimizeResult:
        plan = dict(plan or {})
        plan.setdefault("tier", envelope.preferences.preferred_model_tier or 1)
        plan.setdefault("quantization", envelope.preferences.preferred_quantization or "q4")
        plan.setdefault("reasoning_tokens", int(envelope.categories.get("reasoning_tokens").limit) if "reasoning_tokens" in envelope.categories else 0)
        plan.setdefault("prompt_tokens", int(envelope.categories["prompt_tokens"].limit))
        plan.setdefault("allow_speculation", envelope.preferences.allow_speculation)
        plan.setdefault("tool_calls", int(envelope.categories["tool_calls"].limit))
        plan.setdefault("retries", int(envelope.categories["retries"].limit))

        actions_taken: list[str] = []
        current_proj = dict(projected or {})
        decision = self.validator.validate_state(state, projected=current_proj or None)
        if decision.accepted and not decision.soft_warnings:
            return OptimizeResult(decision=decision, plan_adjustments=plan)

        for step in self.cfg.degrade_ladder:
            handler = self._handlers.get(step)
            if handler is None:
                continue
            adjustments = handler(envelope, state, plan)
            if not adjustments and step != "abort":
                continue
            if step == "abort":
                actions_taken.append(step)
                return OptimizeResult(
                    decision=AdmitDecision(
                        accepted=False,
                        hard_failures=["optimizer abort"],
                        soft_warnings=decision.soft_warnings,
                        optimized=True,
                        degrade_actions=actions_taken,
                    ),
                    plan_adjustments=plan,
                    actions_taken=actions_taken,
                )
            state_adjust = {k: v for k, v in adjustments.items() if k in state.categories}
            if state_adjust:
                for k, v in state_adjust.items():
                    state.categories[k].limit = min(float(state.categories[k].limit), float(v))
                    state.categories[k].refresh_violation()
            actions_taken.append(step)
            state.degrade_actions.append(step)
            # Recompute naive projection from plan
            current_proj = self._project_from_plan(plan)
            decision = self.validator.validate_state(state, projected=current_proj)
            if decision.accepted:
                decision = AdmitDecision(
                    accepted=True,
                    soft_warnings=decision.soft_warnings,
                    hard_failures=[],
                    optimized=True,
                    degrade_actions=actions_taken,
                )
                return OptimizeResult(
                    decision=decision,
                    plan_adjustments=plan,
                    actions_taken=actions_taken,
                )

        return OptimizeResult(
            decision=AdmitDecision(
                accepted=False,
                soft_warnings=decision.soft_warnings,
                hard_failures=decision.hard_failures or ["optimizer exhausted"],
                optimized=True,
                degrade_actions=actions_taken,
            ),
            plan_adjustments=plan,
            actions_taken=actions_taken,
        )

    def _project_from_plan(self, plan: dict[str, Any]) -> dict[str, float]:
        if self.estimator is None:
            return {
                "reasoning_tokens": float(plan.get("reasoning_tokens", 0)),
                "prompt_tokens": float(plan.get("prompt_tokens", 0)),
                "tool_calls": float(plan.get("tool_calls", 0)),
                "retries": float(plan.get("retries", 0)),
            }
        action = PlanAction.tier(int(plan.get("tier", 1)))
        proj = self.estimator.project_action(action)
        values = dict(proj.pick(self.cfg.reserve_percentile).values)
        values["reasoning_tokens"] = float(plan.get("reasoning_tokens", 0))
        values["prompt_tokens"] = float(plan.get("prompt_tokens", 0))
        values["tool_calls"] = float(plan.get("tool_calls", 0))
        values["retries"] = float(plan.get("retries", 0))
        return values

    def _lower_tier(
        self, envelope: BudgetEnvelope, state: BudgetRuntimeState, plan: dict[str, Any]
    ) -> dict[str, float]:
        del envelope, state
        tier = max(1, int(plan.get("tier", 2)) - 1)
        plan["tier"] = tier
        return {}

    def _lower_quant(
        self, envelope: BudgetEnvelope, state: BudgetRuntimeState, plan: dict[str, Any]
    ) -> dict[str, float]:
        del envelope
        order = ["fp16", "q8", "q5", "q4", "q3"]
        cur = str(plan.get("quantization", "q4")).lower()
        if cur not in order:
            plan["quantization"] = "q4"
            return {}
        idx = order.index(cur)
        if idx >= len(order) - 1:
            return {}
        plan["quantization"] = order[idx + 1]
        if "memory_bytes" in state.categories:
            return {"memory_bytes": float(state.categories["memory_bytes"].limit) * 0.85}
        return {}

    def _cut_reasoning(
        self, envelope: BudgetEnvelope, state: BudgetRuntimeState, plan: dict[str, Any]
    ) -> dict[str, float]:
        del envelope
        cur = int(plan.get("reasoning_tokens", 0))
        nxt = max(0, cur // 2)
        plan["reasoning_tokens"] = nxt
        if "reasoning_tokens" in state.categories:
            return {"reasoning_tokens": float(nxt)}
        return {}

    def _trim_context(
        self, envelope: BudgetEnvelope, state: BudgetRuntimeState, plan: dict[str, Any]
    ) -> dict[str, float]:
        del envelope
        cur = int(plan.get("prompt_tokens", 0))
        nxt = max(256, int(cur * 0.75))
        plan["prompt_tokens"] = nxt
        if "prompt_tokens" in state.categories:
            return {"prompt_tokens": float(nxt)}
        return {}

    def _disable_speculation(
        self, envelope: BudgetEnvelope, state: BudgetRuntimeState, plan: dict[str, Any]
    ) -> dict[str, float]:
        del envelope, state
        plan["allow_speculation"] = False
        return {}

    def _drop_tools(
        self, envelope: BudgetEnvelope, state: BudgetRuntimeState, plan: dict[str, Any]
    ) -> dict[str, float]:
        del envelope
        cur = int(plan.get("tool_calls", 0))
        nxt = max(0, cur - 1)
        plan["tool_calls"] = nxt
        if "tool_calls" in state.categories:
            return {"tool_calls": float(nxt)}
        return {}

    def _cut_retries(
        self, envelope: BudgetEnvelope, state: BudgetRuntimeState, plan: dict[str, Any]
    ) -> dict[str, float]:
        del envelope
        cur = int(plan.get("retries", 0))
        nxt = max(0, cur - 1)
        plan["retries"] = nxt
        if "retries" in state.categories:
            return {"retries": float(nxt)}
        return {}

    def _abort(
        self, envelope: BudgetEnvelope, state: BudgetRuntimeState, plan: dict[str, Any]
    ) -> dict[str, float]:
        del envelope, state, plan
        return {}
