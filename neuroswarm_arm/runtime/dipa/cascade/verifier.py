"""Confidence scoring for cascade acceptance (ported from CascadeRouter)."""

from __future__ import annotations

from typing import Any, Mapping

DEFAULT_CONFIDENCE_CFG: dict[str, Any] = {
    "empty_score": 0.0,
    "base_score": 0.5,
    "length_bonus_cap": 0.4,
    "length_divisor": 8000.0,
    "uncertainty_penalty": 0.2,
    "uncertainty_phrases": ["I don't know", "cannot"],
}


def confidence(text: str, cfg: Mapping[str, Any] | None = None) -> float:
    """Score *text* in ``[0, 1]`` using CascadeRouter-compatible heuristics.

    Empty text scores ``empty_score``. Otherwise starts at ``base_score``,
    adds a length bonus capped by ``length_bonus_cap``, and subtracts
    ``uncertainty_penalty`` when uncertainty phrases appear.
    """
    conf = {**DEFAULT_CONFIDENCE_CFG, **(dict(cfg) if cfg else {})}
    if not text.strip():
        return float(conf["empty_score"])

    score = float(conf["base_score"])
    divisor = float(conf["length_divisor"]) or 8000.0
    score += min(float(conf["length_bonus_cap"]), len(text) / divisor)

    phrases = conf.get("uncertainty_phrases") or []
    lowered = text.lower()
    for phrase in phrases:
        token = str(phrase)
        # Match CascadeRouter: "I don't know" is case-sensitive; "cannot" via lower().
        if token.lower() == "cannot":
            if "cannot" in lowered:
                score -= float(conf["uncertainty_penalty"])
                break
        elif token in text:
            score -= float(conf["uncertainty_penalty"])
            break

    return max(0.0, min(1.0, score))


class Verifier:
    """Callable wrapper around :func:`confidence` with a fixed config."""

    def __init__(self, cfg: Mapping[str, Any] | None = None) -> None:
        self.cfg: dict[str, Any] = {**DEFAULT_CONFIDENCE_CFG, **(dict(cfg) if cfg else {})}

    def __call__(self, text: str) -> float:
        return confidence(text, self.cfg)

    def score(self, text: str) -> float:
        return confidence(text, self.cfg)
