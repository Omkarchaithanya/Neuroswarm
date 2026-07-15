"""Deterministic weighted scoring for agent selection."""

from __future__ import annotations

from .agent import Agent
from .models import ScoreBreakdown, ScoringWeights, SelectionRequest
from ._utils import clamp


def _overlap(required: list[str], supported: list[str]) -> float:
    if not required:
        return 1.0
    if not supported:
        return 0.0
    req = set(required)
    sup = set(supported)
    return len(req & sup) / len(req)


def _latency_score(agent: Agent, req: SelectionRequest) -> float:
    budget = req.budget.max_latency_ms
    if budget is None:
        # Prefer lower latency mildly
        if agent.estimated_latency <= 0:
            return 1.0
        return clamp(1.0 / (1.0 + agent.estimated_latency / 1000.0), 0.0, 1.0)
    if agent.estimated_latency <= 0:
        return 1.0
    if agent.estimated_latency > budget:
        return 0.0
    return clamp(1.0 - (agent.estimated_latency / budget), 0.0, 1.0)


def _cost_score(agent: Agent, req: SelectionRequest) -> float:
    budget = req.budget.max_cost_usd
    if budget is None:
        if agent.estimated_cost <= 0:
            return 1.0
        return clamp(1.0 / (1.0 + agent.estimated_cost * 10.0), 0.0, 1.0)
    if agent.estimated_cost <= 0:
        return 1.0
    if agent.estimated_cost > budget:
        return 0.0
    return clamp(1.0 - (agent.estimated_cost / budget), 0.0, 1.0)


def _capability_score(agent: Agent, req: SelectionRequest) -> float:
    tasks = list(req.task_tags)
    if req.task:
        tasks = [req.task, *tasks]
    if not tasks:
        return 1.0
    supported = set(agent.effective_tasks())
    # also match agent_type / category / tags
    supported |= {agent.agent_type, agent.category, *agent.tags}
    hit = sum(1 for t in tasks if t.lower() in {s.lower() for s in supported})
    return hit / len(tasks)


def _resource_score(agent: Agent, req: SelectionRequest) -> float:
    max_mem = req.budget.max_memory_bytes
    if max_mem is None:
        return 1.0
    mem = agent.estimated_memory or agent.resource_requirements.memory_bytes
    if mem <= 0:
        return 1.0
    if mem > max_mem:
        return 0.0
    return clamp(1.0 - (mem / max_mem), 0.0, 1.0)


def _priority_score(agent: Agent) -> float:
    return clamp(agent.priority / 100.0, 0.0, 1.0)


def score_agent(
    agent: Agent,
    request: SelectionRequest,
    *,
    weights: ScoringWeights | None = None,
) -> tuple[float, ScoreBreakdown, list[str]]:
    """Return (weighted_score, breakdown, reasons)."""
    w = (weights or ScoringWeights()).normalized()
    tools = _overlap(request.required_tools, agent.effective_tools())
    models = _overlap(request.required_models, agent.effective_models())
    backends = _overlap(request.required_backends, agent.effective_backends())
    quants = _overlap(request.required_quantizations, agent.effective_quants())
    backend_quant = 0.5 * backends + 0.5 * quants if (
        request.required_backends or request.required_quantizations
    ) else 1.0

    breakdown = ScoreBreakdown(
        capability=_capability_score(agent, request),
        tools=tools,
        models=models,
        backend_quant=backend_quant,
        latency=_latency_score(agent, request),
        cost=_cost_score(agent, request),
        health=clamp(agent.health.score, 0.0, 1.0),
        priority=_priority_score(agent),
        confidence=clamp(agent.confidence_score, 0.0, 1.0),
        resources=_resource_score(agent, request),
    )

    total = (
        w.capability * breakdown.capability
        + w.tools * breakdown.tools
        + w.models * breakdown.models
        + w.backend_quant * breakdown.backend_quant
        + w.latency * breakdown.latency
        + w.cost * breakdown.cost
        + w.health * breakdown.health
        + w.priority * breakdown.priority
        + w.confidence * breakdown.confidence
        + w.resources * breakdown.resources
    )

    # Preferred agent boost (deterministic)
    reasons: list[str] = []
    if agent.id in request.preferred_agents or agent.name in request.preferred_agents:
        total = clamp(total + 0.05, 0.0, 1.0)
        reasons.append("preferred")

    reasons.append(f"capability={breakdown.capability:.2f}")
    reasons.append(f"tools={breakdown.tools:.2f}")
    reasons.append(f"health={breakdown.health:.2f}")
    return clamp(total, 0.0, 1.0), breakdown, reasons
