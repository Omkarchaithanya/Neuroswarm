"""Confidence estimation for routed tools."""

from __future__ import annotations

from .models import ScoredTool


def estimate_confidence(tools: list[ScoredTool]) -> float:
    if not tools:
        return 0.0
    top = tools[0].score
    if len(tools) == 1:
        return min(1.0, max(0.0, top))
    second = tools[1].score
    margin = max(0.0, top - second)
    # Blend absolute score and margin
    conf = 0.7 * min(1.0, max(0.0, top)) + 0.3 * min(1.0, margin * 2.0)
    tools[0].confidence = conf
    for tool in tools[1:]:
        tool.confidence = min(conf, max(0.0, tool.score))
    return conf


def below_threshold(confidence: float, threshold: float) -> bool:
    return confidence < threshold
