"""Execution plan skeleton builder — classify, intent, lifecycle graph."""

from __future__ import annotations

from typing import Any

from ..execution.execution_graph import ExecutionGraph
from ..interfaces.types import ExecutionPlan, InferenceRequest, WorkloadClass
from .policy_engine import PolicyEngine

# Intent keyword buckets (checked in order).
_INTENT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("code", "python", "refactor", "compile", "debug", "implement"), "code"),
    (("reason", "think", "prove", "analyze", "why"), "reason"),
    (("classif", "classify", "label", "categor"), "classif"),
    (("embed", "embedding", "vector"), "embed"),
    (("tool", "function", "call api", "invoke"), "tool"),
)


class ExecutionPlanner:
    """Builds an :class:`ExecutionPlan` skeleton plus default lifecycle graph."""

    def __init__(
        self,
        policy_engine: PolicyEngine | None = None,
        *,
        afford_gate: Any | None = None,
    ) -> None:
        self.policy = policy_engine or PolicyEngine()
        self.afford_gate = afford_gate

    def bind_afford_gate(self, gate: Any) -> None:
        self.afford_gate = gate

    def detect_intent(self, prompt: str) -> str:
        text = (prompt or "").lower()
        for needles, intent in _INTENT_RULES:
            if any(n in text for n in needles):
                return intent
        return "tool"

    def plan(self, req: InferenceRequest) -> ExecutionPlan:
        workload = self.policy.classify_workload(req.agent_role, req.prompt_text)
        intent = self.detect_intent(req.prompt_text)
        policy = self.policy.apply(req, workload)
        graph = ExecutionGraph.default_lifecycle()

        meta: dict[str, Any] = {
            "policy": {
                k: v
                for k, v in policy.items()
                if k
                in {
                    "preferred_model",
                    "latency_sla_ms",
                    "cost_budget_usd",
                    "use_cascade",
                    "max_retries",
                    "workload",
                }
            },
            "agent_role": req.agent_role,
        }
        envelope_id = ""
        if isinstance(getattr(req, "baggage", None), dict):
            envelope_id = str(req.baggage.get("budget_envelope_id", "") or "")
            meta["budget_envelope_id"] = envelope_id
        if self.afford_gate is not None and envelope_id:
            meta = self.afford_gate.guard_metadata(envelope_id, meta)

        return ExecutionPlan(
            workload=workload,
            intent=intent,
            model=str(policy["preferred_model"]),
            use_cascade=bool(policy["use_cascade"]),
            stream=bool(req.stream),
            latency_sla_ms=float(policy["latency_sla_ms"]),
            cost_budget_usd=float(policy["cost_budget_usd"]),
            graph_nodes=graph.names(),
            metadata=meta,
        )

    def classify(self, req: InferenceRequest) -> WorkloadClass:
        return self.policy.classify_workload(req.agent_role, req.prompt_text)
