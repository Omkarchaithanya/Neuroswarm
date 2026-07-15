"""Scored model selection from ``routing.yaml`` candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..interfaces.model import IModelRouter
from ..interfaces.types import (
    ExecutionPlan,
    InferenceRequest,
    ModelCandidate,
    RouteScore,
    WorkloadClass,
)


@dataclass(slots=True)
class _LengthBands:
    short_max_tokens: int = 32
    medium_max_tokens: int = 256
    short_model: str = "tier1"
    medium_model: str = "tier2"
    long_model: str = "tier3"


class ModelRouter(IModelRouter):
    """Score model candidates by length, role, reasoning, SLA, and cost."""

    def __init__(self, routing_cfg: Mapping[str, Any] | None = None) -> None:
        cfg = dict(routing_cfg or {})
        self._weights: dict[str, float] = {
            str(k): float(v) for k, v in (cfg.get("weights") or {}).items()
        }
        self._candidates: list[ModelCandidate] = []
        for name, raw in (cfg.get("models") or {}).items():
            if not isinstance(raw, Mapping):
                continue
            roles = tuple(str(r) for r in (raw.get("roles") or ()))
            self._candidates.append(
                ModelCandidate(
                    name=str(name),
                    size_b=float(raw.get("size_b", 1.0)),
                    roles=roles,
                    latency_hint_ms=float(raw.get("latency_hint_ms", 100.0)),
                    cost_per_1k=float(raw.get("cost_per_1k", 0.001)),
                    reasoning=bool(raw.get("reasoning", False)),
                )
            )
        bands = dict(cfg.get("prompt_length_routing") or {})
        self._bands = _LengthBands(
            short_max_tokens=int(bands.get("short_max_tokens", 32)),
            medium_max_tokens=int(bands.get("medium_max_tokens", 256)),
            short_model=str(bands.get("short_model", "tier1")),
            medium_model=str(bands.get("medium_model", "tier2")),
            long_model=str(bands.get("long_model", "tier3")),
        )
        if not self._candidates:
            self._candidates = [
                ModelCandidate("tier1", 0.5, ("classification", "tool_calling"), 40.0, 0.0001),
                ModelCandidate("tier2", 3.0, ("tool_calling", "coding"), 80.0, 0.0005),
                ModelCandidate(
                    "tier3", 8.0, ("coding", "reasoning"), 150.0, 0.002, reasoning=True
                ),
            ]

    def candidates(self) -> list[ModelCandidate]:
        return list(self._candidates)

    def route(self, req: InferenceRequest, plan: ExecutionPlan) -> RouteScore:
        scored = [self._score(c, req, plan) for c in self._candidates]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[0] if scored else RouteScore(name=plan.model or "tier2", score=0.0)

    def select_model(self, req: InferenceRequest, plan: ExecutionPlan) -> str:
        best = self.route(req, plan)
        plan.model = best.name
        plan.scores["model"] = best.score
        for key, val in best.factors.items():
            plan.scores[f"model_{key}"] = val
        plan.metadata.setdefault("model_route", {})
        plan.metadata["model_route"] = {
            "name": best.name,
            "score": best.score,
            "factors": dict(best.factors),
        }
        return best.name

    def _score(
        self, cand: ModelCandidate, req: InferenceRequest, plan: ExecutionPlan
    ) -> RouteScore:
        w = self._weights
        length = req.prompt_length
        factors: dict[str, float] = {}

        # Prompt-length band affinity.
        preferred = self._length_preferred(length)
        factors["prompt_length"] = 1.0 if cand.name == preferred else 0.35
        if length <= self._bands.short_max_tokens and cand.size_b <= 1.0:
            factors["prompt_length"] = max(factors["prompt_length"], 0.9)
        elif length > self._bands.medium_max_tokens and cand.size_b >= 5.0:
            factors["prompt_length"] = max(factors["prompt_length"], 0.85)

        # Agent role / workload fit.
        role = (req.agent_role or "").lower()
        workload = plan.workload.value if isinstance(plan.workload, WorkloadClass) else str(plan.workload)
        role_hit = any(
            r in cand.roles or r.replace("_", "") in {x.replace("_", "") for x in cand.roles}
            for r in (role, workload)
        )
        factors["agent_role"] = 1.0 if role_hit else 0.25

        # Reasoning flag alignment.
        needs_reason = plan.workload == WorkloadClass.REASONING or "reason" in role
        if needs_reason:
            factors["reasoning"] = 1.0 if cand.reasoning else 0.2
        else:
            factors["reasoning"] = 0.7 if not cand.reasoning else 0.55

        # Latency SLA: prefer models whose hint fits under SLA.
        sla = float(plan.latency_sla_ms or req.latency_sla_ms or 4000.0)
        if cand.latency_hint_ms <= sla * 0.25:
            factors["latency_sla"] = 1.0
        elif cand.latency_hint_ms <= sla:
            factors["latency_sla"] = 0.7
        else:
            factors["latency_sla"] = 0.2

        # Cost: cheaper is better within budget.
        budget = float(plan.cost_budget_usd or req.cost_budget_usd or 0.01)
        est = cand.cost_per_1k * max(1.0, length / 250.0)
        if est <= budget:
            factors["cost"] = 1.0 - min(0.5, est / max(budget, 1e-9))
        else:
            factors["cost"] = max(0.0, 0.3 - (est - budget))

        # Policy preferred model (from planner / PolicyEngine) is a strong prior.
        preferred = str(plan.model or "")
        factors["preferred"] = 1.0 if preferred and cand.name == preferred else 0.3

        score = (
            factors["prompt_length"] * w.get("prompt_length", 0.10)
            + factors["agent_role"] * max(w.get("agent_role", 0.05), 0.20)
            + factors["reasoning"] * 0.15
            + factors["latency_sla"] * w.get("latency_sla", 0.20)
            + factors["cost"] * w.get("cost", 0.05)
            + factors["preferred"] * 0.25
        )
        return RouteScore(name=cand.name, score=score, factors=factors)

    def _length_preferred(self, length: int) -> str:
        if length <= self._bands.short_max_tokens:
            return self._bands.short_model
        if length <= self._bands.medium_max_tokens:
            return self._bands.medium_model
        return self._bands.long_model
