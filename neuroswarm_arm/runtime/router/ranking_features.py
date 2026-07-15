"""Ranking feature extraction."""

from __future__ import annotations

from .hybrid_search import HybridCandidate
from .models import RouteContext
from .similarity import keyword_overlap


def extract_features(
    candidate: HybridCandidate,
    context: RouteContext | None = None,
    *,
    okf_relevance: float = 0.0,
    history_success: float = 0.0,
) -> dict[str, float]:
    ctx = context or RouteContext()
    tool = candidate.tool
    conv = keyword_overlap(ctx.conversation_excerpt or "", tool.index_text())
    param_compat = candidate.components.get("param", 0.0)
    agent_type = candidate.components.get("agent_role", 0.5)
    workflow = candidate.components.get("workflow", 0.5)
    latency = max(0.0, 1.0 - min(tool.p50_latency_ms, 5000.0) / 5000.0)
    failure = 1.0 - tool.failure_rate
    deps = 1.0 if not tool.dependencies else max(
        0.0, 1.0 - len(set(tool.dependencies) - set(ctx.previous_tools)) / max(1, len(tool.dependencies))
    )
    perms = 1.0
    if ctx.required_permissions and tool.permissions:
        perms = len(set(ctx.required_permissions) & set(tool.permissions)) / max(
            1, len(ctx.required_permissions)
        )
    output_fmt = 0.5
    if ctx.expected_output_format:
        blob = str(tool.output_schema) + " " + tool.description
        output_fmt = 1.0 if ctx.expected_output_format.lower() in blob.lower() else 0.2
    cost = max(0.0, 1.0 - min(tool.cost_usd, 1.0))
    budget = 1.0 if tool.cost_usd <= ctx.budget_remaining_usd else 0.1
    confidence = min(1.0, max(0.0, candidate.semantic_score))
    return {
        "semantic": candidate.semantic_score,
        "param_compat": param_compat,
        "agent_type": agent_type,
        "workflow_stage": workflow,
        "conversation": conv,
        "history_success": history_success,
        "latency": latency,
        "failure_rate": failure,
        "dependencies": deps,
        "permissions": perms,
        "output_format": output_fmt,
        "okf_relevance": okf_relevance,
        "cost": cost,
        "budget": budget,
        "confidence": confidence,
        "hybrid": candidate.hybrid_score,
    }
