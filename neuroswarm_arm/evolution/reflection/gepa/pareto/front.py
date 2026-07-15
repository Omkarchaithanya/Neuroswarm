"""
Pareto frontier for GEPA candidates.

Official concept: maintain non-dominated candidates across task instances /
objectives; SelectCandidate samples from the frontier (paper Figure 4).

ArmCascade/AROP: multi-objective text-candidate selection — never collapse
to a single “best” threshold policy.
"""

from __future__ import annotations

import random
from typing import Iterable, Sequence

from neuroswarm_arm.evolution.reflection.gepa.candidate.models import (
    PARETO_OBJECTIVES,
    TextCandidate,
)

# Objectives where lower is better
MINIMIZE = frozenset(
    {
        "latency",
        "cost",
        "reasoning_tokens",
        "tool_calls",
        "prompt_length",
        "context_length",
        "memory",
        "cpu",
    }
)
# Higher is better
MAXIMIZE = frozenset({"accuracy", "acceptance_rate", "compression_ratio", "aggregate"})


def _objective_value(candidate: TextCandidate, obj: str) -> float | None:
    if obj in candidate.scores:
        return float(candidate.scores[obj])
    if obj == "aggregate":
        return candidate.mean_score()
    # Derive prompt_length from components if missing
    if obj == "prompt_length":
        return float(sum(len(v) for v in candidate.components.values()))
    return None


def dominates(a: TextCandidate, b: TextCandidate, objectives: Sequence[str]) -> bool:
    """True if a dominates b on the given objectives (at least one strict)."""
    better_or_eq = False
    strict = False
    for obj in objectives:
        va, vb = _objective_value(a, obj), _objective_value(b, obj)
        if va is None or vb is None:
            continue
        better_or_eq = True
        if obj in MINIMIZE:
            if va > vb:
                return False
            if va < vb:
                strict = True
        else:
            if va < vb:
                return False
            if va > vb:
                strict = True
    return better_or_eq and strict


class ParetoFront:
    """Non-dominated set of TextCandidates."""

    def __init__(self, objectives: Sequence[str] | None = None) -> None:
        self.objectives = tuple(objectives or PARETO_OBJECTIVES)
        self._members: list[TextCandidate] = []

    def update(self, candidates: Iterable[TextCandidate]) -> list[TextCandidate]:
        pool = list(self._members) + list(candidates)
        # Prefer latest score-bearing versions by id
        by_id: dict[str, TextCandidate] = {}
        for c in pool:
            by_id[c.id] = c
        items = list(by_id.values())
        front: list[TextCandidate] = []
        for c in items:
            if any(dominates(other, c, self.objectives) for other in items if other.id != c.id):
                continue
            front.append(c)
        self._members = front
        return list(self._members)

    def members(self) -> list[TextCandidate]:
        return list(self._members)

    def select(self, *, rng: random.Random | None = None) -> TextCandidate | None:
        """Stochastic select from frontier (official SelectCandidate style)."""
        if not self._members:
            return None
        r = rng or random.Random()
        # Weight by appearance / mean score
        weights = [max(0.01, c.mean_score() + 0.1) for c in self._members]
        total = sum(weights)
        pick = r.random() * total
        acc = 0.0
        for c, w in zip(self._members, weights):
            acc += w
            if pick <= acc:
                return c
        return self._members[-1]

    def __len__(self) -> int:
        return len(self._members)
