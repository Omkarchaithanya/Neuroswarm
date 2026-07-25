"""Calibrated confidence fusion."""

from __future__ import annotations

import os
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
    """Calibrated heuristic for quality-cascade early-accept.

    Short, clear answers previously capped near ~0.5 (base) and never cleared a
    0.7 speculative threshold — forcing always-escalate-to-tier3. Defaults now
    reward concise substantive replies; quality-path thresholds are separate
    (see ``quality_accept_threshold`` in ascr.yaml / env).
    """
    conf: dict[str, Any] = {
        "empty_score": 0.0,
        "base_score": 0.55,
        "length_bonus_cap": 0.25,
        "length_divisor": 2000.0,
        "short_clear_bonus": 0.18,
        "short_clear_max_chars": 480,
        "short_clear_min_chars": 24,
        "completeness_bonus": 0.08,
        "uncertainty_penalty": 0.25,
        "uncertainty_phrases": [
            "I don't know",
            "I do not know",
            "cannot",
            "I'm not sure",
            "i am not sure",
            "unclear",
        ],
    }
    conf.update(dict(cfg or {}))
    # Nested weights block from ascr.yaml must not pollute numeric knobs.
    conf.pop("weights", None)

    stripped = text.strip()
    if not stripped:
        return float(conf["empty_score"])

    score = float(conf["base_score"])
    divisor = float(conf["length_divisor"]) or 2000.0
    score += min(float(conf["length_bonus_cap"]), len(stripped) / divisor)

    phrases = conf.get("uncertainty_phrases") or []
    lowered = stripped.lower()
    uncertain = False
    for phrase in phrases:
        token = str(phrase)
        if token.lower() == "cannot":
            if "cannot" in lowered:
                uncertain = True
                break
        elif token.lower() in lowered:
            uncertain = True
            break

    if uncertain:
        score -= float(conf["uncertainty_penalty"])
        # Do not award short/complete bonuses on uncertain replies.
        return _clip(score)

    n = len(stripped)
    min_c = int(conf["short_clear_min_chars"])
    max_c = int(conf["short_clear_max_chars"])
    if min_c <= n <= max_c:
        score += float(conf["short_clear_bonus"])

    if stripped[-1] in ".!?" and any(ch.isalpha() for ch in stripped):
        score += float(conf["completeness_bonus"])

    return _clip(score)


def quality_path_accept_threshold(cfg: Mapping[str, Any] | None = None) -> float:
    """Accept threshold for quality_cascade (lower than speculative logits path)."""
    defaults = dict((cfg or {}).get("defaults") or {})
    confidence = dict((cfg or {}).get("confidence") or {})
    if "quality_accept_threshold" in defaults:
        return float(defaults["quality_accept_threshold"])
    if "quality_accept_threshold" in confidence:
        return float(confidence["quality_accept_threshold"])
    if v := os.environ.get("NSA_ASCR_QUALITY_ACCEPT_THRESHOLD"):
        return float(v)
    return 0.55


def should_early_accept_quality(
    confidence: float,
    *,
    tier_id: int,
    threshold: float,
    cfg: Mapping[str, Any] | None = None,
) -> bool:
    """Early-accept strong tier1/tier2 quality answers without forcing tier3."""
    defaults = dict((cfg or {}).get("defaults") or {})
    early_raw = defaults.get("quality_early_accept_floor")
    if early_raw is None:
        env = os.environ.get("NSA_ASCR_QUALITY_EARLY_ACCEPT")
        early_floor = float(env) if env not in (None, "") else float(threshold)
    else:
        early_floor = float(early_raw)
    if confidence >= threshold:
        return True
    if tier_id <= 2 and confidence >= early_floor:
        return True
    return False


def _clip(v: float) -> float:
    return max(0.0, min(1.0, float(v)))
