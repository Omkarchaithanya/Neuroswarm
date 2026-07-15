"""Confidence scoring for AWPP predictions."""

from __future__ import annotations

import math
from typing import Sequence


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def from_max_prob(probs: Sequence[float]) -> float:
    if not probs:
        return 0.0
    return clamp01(max(float(p) for p in probs))


def from_margin(probs: Sequence[float]) -> float:
    """Top1 − top2 margin as confidence."""
    if not probs:
        return 0.0
    ordered = sorted((float(p) for p in probs), reverse=True)
    if len(ordered) == 1:
        return clamp01(ordered[0])
    return clamp01(ordered[0] - ordered[1])


def blend(scores: Sequence[float], weights: Sequence[float] | None = None) -> float:
    if not scores:
        return 0.0
    if weights is None or len(weights) != len(scores):
        weights = [1.0] * len(scores)
    total_w = sum(weights) or 1.0
    return clamp01(sum(s * w for s, w in zip(scores, weights)) / total_w)


def gate(confidence: float, threshold: float) -> bool:
    return confidence >= threshold


def sample_size_factor(n: int, *, saturation: int = 50) -> float:
    """Confidence grows with observation count, saturating at `saturation`."""
    if n <= 0:
        return 0.0
    return clamp01(1.0 - math.exp(-n / max(saturation, 1)))
