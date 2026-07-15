"""Workload classification and SLA/cost policy application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..interfaces.types import InferenceRequest, WorkloadClass

# Prompt keyword → workload (checked in order; first hit wins).
_PROMPT_HINTS: tuple[tuple[tuple[str, ...], WorkloadClass], ...] = (
    (("classif", "classify", "label", "categor"), WorkloadClass.CLASSIFICATION),
    (("embed", "embedding", "vectoriz"), WorkloadClass.EMBEDDING),
    (("rerank", "ranking"), WorkloadClass.RERANKING),
    (("vision", "image", "screenshot", "ocr"), WorkloadClass.VISION),
    (("speech", "audio", "transcri", "asr"), WorkloadClass.SPEECH),
    (("code", "python", "refactor", "compile", "debug"), WorkloadClass.CODING),
    (("reason", "think", "chain-of-thought", "cot", "prove"), WorkloadClass.REASONING),
    (("tool", "function call", "api call"), WorkloadClass.TOOL_CALLING),
)


@dataclass(slots=True)
class PolicyDecision:
    preferred_model: str
    latency_sla_ms: float
    cost_budget_usd: float
    use_cascade: bool
    extras: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "preferred_model": self.preferred_model,
            "latency_sla_ms": self.latency_sla_ms,
            "cost_budget_usd": self.cost_budget_usd,
            "use_cascade": self.use_cascade,
        }
        out.update(self.extras)
        return out


class PolicyEngine:
    """Loads ``policy.yaml`` structure and maps role/prompt → workload + SLA."""

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        cfg = dict(config or {})
        self._workloads: dict[str, dict[str, Any]] = {
            str(k): dict(v) if isinstance(v, Mapping) else {}
            for k, v in (cfg.get("workloads") or {}).items()
        }
        self._role_map: dict[str, str] = {
            str(k): str(v) for k, v in (cfg.get("role_to_workload") or {}).items()
        }
        defaults = dict(cfg.get("defaults") or {})
        self._defaults: dict[str, Any] = {
            "preferred_model": defaults.get("preferred_model", "tier2"),
            "latency_sla_ms": float(defaults.get("latency_sla_ms", 4000.0)),
            "cost_budget_usd": float(defaults.get("cost_budget_usd", 0.01)),
            "use_cascade": bool(defaults.get("use_cascade", True)),
            "max_retries": int(defaults.get("max_retries", 2)),
        }

    def classify_workload(self, agent_role: str, prompt: str) -> WorkloadClass:
        role_key = (agent_role or "").strip().lower()
        mapped = self._role_map.get(role_key)
        if mapped:
            try:
                return WorkloadClass(mapped)
            except ValueError:
                pass

        # Direct enum value / name as role.
        if role_key:
            try:
                return WorkloadClass(role_key)
            except ValueError:
                pass
            for wc in WorkloadClass:
                if wc.name.lower() == role_key or wc.value == role_key:
                    return wc

        text = (prompt or "").lower()
        for needles, workload in _PROMPT_HINTS:
            if any(n in text for n in needles):
                return workload
        return WorkloadClass.TOOL_CALLING

    def apply(
        self, req: InferenceRequest, workload: WorkloadClass
    ) -> dict[str, Any]:
        """Return policy knobs for *workload*, with request overrides honored."""
        entry = dict(self._workloads.get(workload.value, {}))
        preferred = str(
            entry.get("preferred_model", self._defaults["preferred_model"])
        )
        latency = float(
            entry.get("latency_sla_ms", self._defaults["latency_sla_ms"])
        )
        cost = float(
            entry.get("cost_budget_usd", self._defaults["cost_budget_usd"])
        )
        use_cascade = bool(
            entry.get("use_cascade", self._defaults["use_cascade"])
        )

        # Request-level budgets win when tighter / explicitly set.
        if req.latency_sla_ms > 0:
            latency = min(latency, float(req.latency_sla_ms))
        if req.cost_budget_usd > 0:
            cost = min(cost, float(req.cost_budget_usd))

        decision = PolicyDecision(
            preferred_model=preferred,
            latency_sla_ms=latency,
            cost_budget_usd=cost,
            use_cascade=use_cascade,
            extras={
                "max_retries": int(
                    entry.get("max_retries", self._defaults["max_retries"])
                ),
                "workload": workload.value,
            },
        )
        return decision.as_dict()
