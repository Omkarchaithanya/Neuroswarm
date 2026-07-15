"""Learning-to-rank abstraction."""

from __future__ import annotations

from typing import Protocol

from ..router_config import RerankWeights


class LearningToRankModel(Protocol):
    def score(self, features: dict[str, float]) -> float: ...

    def update(self, features: dict[str, float], label: float) -> None: ...


class WeightedLTRModel:
    def __init__(self, weights: RerankWeights | None = None) -> None:
        self.weights = weights or RerankWeights()
        self._online: dict[str, float] = {}

    def score(self, features: dict[str, float]) -> float:
        w = self.weights
        mapping = {
            "semantic": w.semantic,
            "param_compat": w.param_compat,
            "agent_type": w.agent_type,
            "workflow_stage": w.workflow_stage,
            "conversation": w.conversation,
            "history_success": w.history_success,
            "latency": w.latency,
            "failure_rate": w.failure_rate,
            "dependencies": w.dependencies,
            "permissions": w.permissions,
            "output_format": w.output_format,
            "okf_relevance": w.okf_relevance,
            "cost": w.cost,
            "budget": w.budget,
            "confidence": w.confidence,
        }
        total = 0.0
        weight_sum = 0.0
        for key, weight in mapping.items():
            online = self._online.get(key, 0.0)
            w_eff = weight + online
            total += w_eff * float(features.get(key, 0.0))
            weight_sum += abs(w_eff)
        if weight_sum <= 0:
            return float(features.get("hybrid", features.get("semantic", 0.0)))
        return total / weight_sum

    def update(self, features: dict[str, float], label: float) -> None:
        # Simple online perceptron-style nudge for future RL/active learning
        pred = self.score(features)
        err = label - pred
        lr = 0.01
        for key, value in features.items():
            self._online[key] = self._online.get(key, 0.0) + lr * err * value
