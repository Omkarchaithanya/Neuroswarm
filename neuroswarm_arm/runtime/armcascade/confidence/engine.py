"""Calibrated confidence fusion."""

from __future__ import annotations

from typing import Any, Mapping

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import ConfidenceEngine
from neuroswarm_arm.runtime.armcascade.interfaces.types import AcceptanceSignals

DEFAULT_WEIGHTS: dict[str, float] = {
    "agreement": 0.30,
    "quality": 0.25,
    "historical": 0.15,
    "entropy_inv": 0.10,
    "tool": 0.10,
    "reasoning": 0.05,
    "runtime": 0.05,
}


class FusedConfidenceEngine(ConfidenceEngine):
    def __init__(self, weights: Mapping[str, float] | None = None) -> None:
        self.weights = {**DEFAULT_WEIGHTS, **dict(weights or {})}

    def fuse(self, signals: AcceptanceSignals) -> float:
        w = self.weights
        entropy_inv = 1.0 - min(1.0, max(0.0, signals.entropy))
        runtime = 1.0 - 0.5 * min(1.0, signals.cpu_utilization) - 0.5 * min(
            1.0, signals.kv_pressure
        )
        runtime = max(0.0, min(1.0, runtime))
        budget_ok = 1.0
        if signals.latency_budget_ms > 0:
            budget_ok = max(
                0.0,
                1.0 - signals.latency_used_ms / signals.latency_budget_ms,
            )

        score = (
            w["agreement"] * _clip(signals.agreement)
            + w["quality"] * _clip(signals.quality_score)
            + w["historical"] * _clip(signals.historical_acceptance)
            + w["entropy_inv"] * entropy_inv
            + w["tool"] * _clip(signals.tool_confidence)
            + w["reasoning"] * _clip(signals.reasoning_confidence)
            + w["runtime"] * (0.5 * runtime + 0.5 * budget_ok)
        )
        return _clip(score)


def text_quality_score(text: str, cfg: Mapping[str, Any] | None = None) -> float:
    """Legacy CascadeRouter-compatible heuristic (quality-cascade mode)."""
    conf = {
        "empty_score": 0.0,
        "base_score": 0.5,
        "length_bonus_cap": 0.4,
        "length_divisor": 8000.0,
        "uncertainty_penalty": 0.2,
        "uncertainty_phrases": ["I don't know", "cannot"],
        **dict(cfg or {}),
    }
    if not text.strip():
        return float(conf["empty_score"])
    score = float(conf["base_score"])
    divisor = float(conf["length_divisor"]) or 8000.0
    score += min(float(conf["length_bonus_cap"]), len(text) / divisor)
    phrases = conf.get("uncertainty_phrases") or []
    lowered = text.lower()
    for phrase in phrases:
        token = str(phrase)
        if token.lower() == "cannot":
            if "cannot" in lowered:
                score -= float(conf["uncertainty_penalty"])
                break
        elif token in text:
            score -= float(conf["uncertainty_penalty"])
            break
    return _clip(score)


def _clip(v: float) -> float:
    return max(0.0, min(1.0, float(v)))
