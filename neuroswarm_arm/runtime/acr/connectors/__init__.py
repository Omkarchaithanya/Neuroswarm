"""HAOE / ASCR / AWPP connectors for ACR — connectors not ownership."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.acr.ir.context import ContextSnapshot
from neuroswarm_arm.runtime.acr.kernel import AdaptiveContextRuntime


def build_context_for_haoe(
    acr: AdaptiveContextRuntime | None,
    *,
    query: str,
    owner: str = "default",
    agent_role: str = "architect",
    tool_names: list[str] | None = None,
    tool_prompt_block: str = "",
    token_budget: int | None = None,
) -> ContextSnapshot | None:
    """Connector: HAOE asks ACR for assembled context; never imports OKF/Mem0 merge."""
    if acr is None or not acr.enabled:
        return None
    return acr.build_context(
        query,
        owner=owner,
        agent_role=agent_role,
        tool_names=tool_names,
        tool_prompt_block=tool_prompt_block,
        token_budget=token_budget,
    )


def escalate_memory_needed(
    acr: AdaptiveContextRuntime | None,
    *,
    query: str,
    owner: str = "default",
    agent_role: str = "architect",
    extra_budget: int = 800,
) -> str:
    """ASCR memory_needed escalation → compact context delta from ACR."""
    if acr is None or not acr.enabled:
        return ""
    snap = acr.build_context(
        query,
        owner=owner,
        agent_role=agent_role,
        token_budget=extra_budget,
        use_cache=False,
    )
    return snap.prompt or ""


def awpp_prefetch_hints(
    acr: AdaptiveContextRuntime | None,
    *,
    query: str,
    owner: str = "default",
    agent_role: str = "architect",
) -> dict[str, Any]:
    """AWPP consumes ACR understanding/plan signals for pre-warm targets."""
    if acr is None or not acr.enabled:
        return {}
    graph = acr.understanding.understand(query, agent_role=agent_role, owner=owner)
    plan = acr.planner.plan(graph, token_budget=acr.config.token_budget)
    return {
        "intent": graph.intent,
        "predicted_tools": graph.predicted_tools,
        "namespaces": [
            ns for n in graph.nodes for ns in (n.namespaces or [])
        ],
        "steps": [
            {"source": s.source.value, "priority": s.priority, "lazy": s.lazy}
            for s in plan.steps
        ],
        "agent_role": agent_role,
    }


def record_rtg_outcome(
    acr: AdaptiveContextRuntime | None,
    snapshot: ContextSnapshot | None,
    *,
    success: bool,
    cost: float = 0.0,
    latency_ms: float = 0.0,
    owner: str = "default",
) -> list[str]:
    """RTG/DIPA completion → Evolution Engine."""
    if acr is None or snapshot is None:
        return []
    return acr.evolve(snapshot, success=success, cost=cost, latency_ms=latency_ms, owner=owner)
