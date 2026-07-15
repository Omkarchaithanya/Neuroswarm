"""Production reranker with weighted features + LTR/RL hooks."""

from __future__ import annotations

from .hybrid_search import HybridCandidate
from .models import RouteContext, ScoredTool
from .ranking.learning_to_rank import LearningToRankModel, WeightedLTRModel
from .ranking.rl_hook import RLRoutingHook, NoOpRLHook
from .ranking_features import extract_features
from .router_config import RerankWeights
from .tool_schema_builder import build_tool_schema


class Reranker:
    def __init__(
        self,
        weights: RerankWeights | None = None,
        *,
        ltr: LearningToRankModel | None = None,
        rl_hook: RLRoutingHook | None = None,
    ) -> None:
        self.weights = weights or RerankWeights()
        self.ltr = ltr or WeightedLTRModel(self.weights)
        self.rl_hook = rl_hook or NoOpRLHook()

    def rerank(
        self,
        candidates: list[HybridCandidate],
        context: RouteContext | None = None,
        *,
        history_scores: dict[str, float] | None = None,
        okf_scores: dict[str, float] | None = None,
        top_k: int = 3,
    ) -> list[ScoredTool]:
        history_scores = history_scores or {}
        okf_scores = okf_scores or {}
        scored: list[ScoredTool] = []
        for cand in candidates:
            features = extract_features(
                cand,
                context,
                okf_relevance=okf_scores.get(cand.tool.id, 0.0),
                history_success=history_scores.get(cand.tool.id, cand.tool.success_rate * 0.5),
            )
            base = self.ltr.score(features)
            adjusted = self.rl_hook.adjust(cand.tool.id, base, features, context)
            scored.append(
                ScoredTool(
                    tool=cand.tool,
                    score=float(adjusted),
                    semantic_score=cand.semantic_score,
                    hybrid_score=cand.hybrid_score,
                    rerank_score=float(adjusted),
                    confidence=min(1.0, max(0.0, float(adjusted))),
                    features=features,
                    schema=build_tool_schema(cand.tool),
                )
            )
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[: max(1, top_k)]
