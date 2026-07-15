"""Uncertainty / entropy helpers for AWPP predictions."""

from __future__ import annotations

import math
from typing import Mapping, Sequence

from .confidence import clamp01


def shannon_entropy(probs: Sequence[float]) -> float:
    """Shannon entropy in nats; zero for empty / degenerate."""
    total = sum(max(0.0, float(p)) for p in probs)
    if total <= 0:
        return 0.0
    h = 0.0
    for p in probs:
        q = max(0.0, float(p)) / total
        if q > 0:
            h -= q * math.log(q)
    return h


def normalized_entropy(probs: Sequence[float]) -> float:
    """Entropy / log(k) → [0, 1]."""
    k = len([p for p in probs if float(p) > 0]) or len(probs)
    if k <= 1:
        return 0.0
    return clamp01(shannon_entropy(probs) / math.log(k))


def uncertainty_score(
    *,
    entropy: float,
    confidence: float,
    sample_factor: float = 1.0,
) -> float:
    """
    High entropy + low confidence + low samples → high uncertainty.
    Used to shrink / skip prewarm sets.
    """
    base = 0.5 * clamp01(entropy) + 0.5 * (1.0 - clamp01(confidence))
    return clamp01(base * (1.5 - 0.5 * clamp01(sample_factor)))


def probs_from_counts(counts: Mapping[str, float]) -> dict[str, float]:
    total = sum(max(0.0, float(v)) for v in counts.values())
    if total <= 0:
        return {}
    return {k: max(0.0, float(v)) / total for k, v in counts.items()}
