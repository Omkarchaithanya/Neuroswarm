"""AWPP policies — frequency/Markov first; PPO offline later."""

from __future__ import annotations

from .frequency import FrequencyPolicy
from .markov import MarkovPolicy


def build_policy(name: str, **kwargs):
    key = (name or "markov").strip().lower()
    if key in {"frequency", "freq"}:
        return FrequencyPolicy(**kwargs)
    return MarkovPolicy(**kwargs)


__all__ = ["FrequencyPolicy", "MarkovPolicy", "build_policy"]
