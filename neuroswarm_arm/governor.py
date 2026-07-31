"""ReasoningGovernor — compat facade over RTGRuntime (AIM Pillar 4).

Legacy ``cap(PlanState)`` / ``prompt(PlanState)`` API preserved for
CascadeRouter and benchmarks. Prefer ``neuroswarm_arm.runtime.rtg.build_rtg``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .schemas import PlanState

if TYPE_CHECKING:
    from .runtime.rtg import RTGRuntime


class ReasoningGovernor:
    """Thin facade: delegates to RTG when wired; else legacy heuristic path."""

    def __init__(self, rtg: RTGRuntime | None = None) -> None:
        self.rtg = rtg

    def cap(self, plan: PlanState, router_result: Any | None = None) -> int:
        if router_result is not None and hasattr(router_result, "confidence_top1"):
            conf = float(router_result.confidence_top1)
            # Upstream signals still win: take max with existing plan confidence.
            if hasattr(plan, "model_copy"):
                plan = plan.model_copy(
                    update={
                        "tool_confidence_top1": max(
                            float(getattr(plan, "tool_confidence_top1", 0.0) or 0.0),
                            conf,
                        )
                    }
                )
            else:
                plan.tool_confidence_top1 = max(
                    float(getattr(plan, "tool_confidence_top1", 0.0) or 0.0),
                    conf,
                )
        if self.rtg is not None and self.rtg.config.enabled:
            from .runtime.rtg.models import TelemetryFrame

            frame = TelemetryFrame.from_plan_state(plan)
            return int(self.rtg.initial_budget(frame))
        return self._legacy_cap(plan)

    def prompt(self, plan: PlanState) -> str:
        cap = self.cap(plan)
        if self.rtg is not None:
            base = self.rtg.prompt(cap)
        else:
            base = (
                f"You may reason for up to {cap} tokens before producing a tool call. "
                "If your chosen tool confidence is >= 0.85, commit immediately."
            )
        try:
            from neuroswarm_arm.evolution.reflection.gepa.active_prompt import (
                load_active_system_prompt,
            )

            evolved = load_active_system_prompt()
            if evolved:
                return f"{base}\n\n# GEPA evolved system prompt\n{evolved}"
        except Exception:
            pass
        return base

    def admit(self, plan: PlanState, **kwargs: Any) -> dict[str, Any]:
        if self.rtg is None:
            cap = self.cap(plan)
            return {"thinking_token_cap": cap, "system_prompt": self.prompt(plan)}
        from .runtime.rtg.models import TelemetryFrame

        frame = TelemetryFrame.from_plan_state(plan, **{
            k: v for k, v in kwargs.items() if k in TelemetryFrame.__dataclass_fields__
        })
        state = self.rtg.admit(frame)
        system = self.rtg.prompt(state.budget.initial_tokens)
        try:
            from neuroswarm_arm.evolution.reflection.gepa.active_prompt import (
                load_active_system_prompt,
            )

            evolved = load_active_system_prompt()
            if evolved:
                system = f"{system}\n\n# GEPA evolved system prompt\n{evolved}"
        except Exception:
            pass
        return {
            "session_id": state.session_id,
            "thinking_token_cap": state.budget.initial_tokens,
            "system_prompt": system,
        }

    @staticmethod
    def _legacy_cap(plan: PlanState) -> int:
        cap = 4096
        if plan.tool_confidence_top1 > 0.85:
            cap = min(cap, 256)
        if plan.kv_pressure > 0.70:
            cap = min(cap, 512)
        if plan.memory_pressure > 0.85:
            cap = min(cap, 256)
        if plan.kv_hit_rate < 0.20 and plan.kv_pressure > 0.50:
            cap = min(cap, 384)
        if plan.kv_migration_latency_ms > 50.0:
            cap = min(cap, 512)
        if plan.slo_remaining_ms < 4000:
            cap = min(cap, int(256 + 4 * plan.tool_confidence_top1 * 1024))
        if plan.self_consistency_score > 0.90:
            cap = min(cap, 128)
        return cap
