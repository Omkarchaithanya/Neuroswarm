from __future__ import annotations

from .schemas import PlanState


class ReasoningGovernor:
    def cap(self, plan: PlanState) -> int:
        cap = 4096
        if plan.tool_confidence_top1 > 0.85:
            cap = min(cap, 256)
        if plan.kv_pressure > 0.70:
            cap = min(cap, 512)
        if plan.slo_remaining_ms < 4000:
            cap = min(cap, int(256 + 4 * plan.tool_confidence_top1 * 1024))
        if plan.self_consistency_score > 0.90:
            cap = min(cap, 128)
        return cap

    def prompt(self, plan: PlanState) -> str:
        cap = self.cap(plan)
        return (
            f"You may reason for up to {cap} tokens before producing a tool call. "
            "If your chosen tool confidence is >= 0.85, commit immediately."
        )

