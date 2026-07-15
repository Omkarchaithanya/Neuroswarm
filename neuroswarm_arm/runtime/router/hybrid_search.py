"""Hybrid retrieval: semantic + keyword + symbolic + contextual signals."""

from __future__ import annotations

from dataclasses import dataclass

from .models import RouteContext, ToolRecord
from .router_config import HybridWeights
from .similarity import keyword_overlap


@dataclass(slots=True)
class HybridCandidate:
    tool: ToolRecord
    semantic_score: float
    hybrid_score: float
    components: dict[str, float]


class HybridSearch:
    def __init__(self, weights: HybridWeights | None = None) -> None:
        self.weights = weights or HybridWeights()

    def score_tool(
        self,
        query: str,
        tool: ToolRecord,
        *,
        semantic_score: float,
        context: RouteContext | None = None,
        history_success: float = 0.0,
    ) -> HybridCandidate:
        ctx = context or RouteContext()
        keyword = keyword_overlap(query, tool.index_text())
        param = self._param_similarity(query, tool)
        capability = self._capability_match(tool, ctx)
        workflow = self._workflow_match(tool, ctx)
        agent = self._agent_match(tool, ctx)
        popularity = min(1.0, max(0.0, tool.popularity))
        latency_cost = self._latency_cost(tool, ctx)
        w = self.weights
        components = {
            "semantic": semantic_score,
            "keyword": keyword,
            "param": param,
            "capability": capability,
            "workflow": workflow,
            "agent_role": agent,
            "popularity": popularity,
            "history_success": history_success,
            "latency_cost": latency_cost,
        }
        hybrid = (
            w.semantic * semantic_score
            + w.keyword * keyword
            + w.param * param
            + w.capability * capability
            + w.workflow * workflow
            + w.agent_role * agent
            + w.popularity * popularity
            + w.history_success * history_success
            + w.latency_cost * latency_cost
        )
        return HybridCandidate(
            tool=tool,
            semantic_score=semantic_score,
            hybrid_score=float(hybrid),
            components=components,
        )

    def fuse(
        self,
        query: str,
        semantic_hits: list[tuple[ToolRecord, float]],
        *,
        context: RouteContext | None = None,
        history_scores: dict[str, float] | None = None,
    ) -> list[HybridCandidate]:
        history_scores = history_scores or {}
        out = [
            self.score_tool(
                query,
                tool,
                semantic_score=score,
                context=context,
                history_success=history_scores.get(tool.id, tool.success_rate * 0.5),
            )
            for tool, score in semantic_hits
        ]
        out.sort(key=lambda c: c.hybrid_score, reverse=True)
        return out

    def _param_similarity(self, query: str, tool: ToolRecord) -> float:
        if not tool.params:
            return 0.0
        return keyword_overlap(query, " ".join(tool.params.keys()) + " " + " ".join(tool.params.values()))

    def _capability_match(self, tool: ToolRecord, ctx: RouteContext) -> float:
        if not ctx.required_capabilities:
            return 0.5 if tool.capabilities else 0.3
        if not tool.capabilities:
            return 0.0
        overlap = len(set(ctx.required_capabilities) & set(tool.capabilities))
        return overlap / max(1, len(ctx.required_capabilities))

    def _workflow_match(self, tool: ToolRecord, ctx: RouteContext) -> float:
        if not tool.workflow_stages:
            return 0.5
        return 1.0 if ctx.workflow_stage in tool.workflow_stages else 0.2

    def _agent_match(self, tool: ToolRecord, ctx: RouteContext) -> float:
        if not tool.agent_roles:
            return 0.5
        return 1.0 if ctx.agent_role in tool.agent_roles else 0.2

    def _latency_cost(self, tool: ToolRecord, ctx: RouteContext) -> float:
        # Higher score for cheaper/faster tools when SLO/budget tight
        latency_score = max(0.0, 1.0 - min(tool.p50_latency_ms, ctx.latency_slo_ms) / max(ctx.latency_slo_ms, 1.0))
        budget = max(ctx.budget_remaining_usd, 1e-6)
        cost_score = max(0.0, 1.0 - min(tool.cost_usd, budget) / budget)
        reliability = tool.reliability * (1.0 - tool.failure_rate)
        return 0.4 * latency_score + 0.4 * cost_score + 0.2 * reliability
