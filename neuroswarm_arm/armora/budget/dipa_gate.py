"""DIPA afford gate — consult ARMORA BudgetService before plan actions."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.armora.budget.schemas import AffordDecision, PlanAction
from neuroswarm_arm.armora.budget.service import BudgetService


class BudgetAffordGate:
    """Injected into DIPA ExecutionPlanner / DecisionEngine."""

    def __init__(self, service: BudgetService | None = None) -> None:
        self.service = service

    def bind(self, service: BudgetService) -> None:
        self.service = service

    def can_afford(self, envelope_id: str | None, action: PlanAction) -> AffordDecision:
        if self.service is None or not envelope_id:
            return AffordDecision(
                affordable=True,
                action=action.kind.value,
                message="budget service unbound — allow by default",
            )
        return self.service.can_afford(str(envelope_id), action)

    def select_affordable_tier(
        self, envelope_id: str | None, preferred: int = 1, maximum: int = 3
    ) -> int:
        for tier in range(int(preferred), int(maximum) + 1):
            d = self.can_afford(envelope_id, PlanAction.tier(tier))
            if d.affordable:
                return tier
        # Walk down if preferred too expensive
        for tier in range(int(preferred), 0, -1):
            d = self.can_afford(envelope_id, PlanAction.tier(tier))
            if d.affordable:
                return tier
        return 1

    def guard_metadata(self, envelope_id: str | None, plan_meta: dict[str, Any]) -> dict[str, Any]:
        out = dict(plan_meta)
        if not envelope_id or self.service is None:
            return out
        tier = int(out.get("preferred_model_tier", out.get("tier", 1)) or 1)
        chosen = self.select_affordable_tier(envelope_id, preferred=tier)
        out["preferred_model_tier"] = chosen
        out["budget_envelope_id"] = envelope_id
        quant = str(out.get("quantization", "") or "")
        if quant:
            qdec = self.can_afford(envelope_id, PlanAction.quant(quant))
            if not qdec.affordable:
                out["quantization"] = "q4"
                out["budget_quant_degraded"] = True
        return out
