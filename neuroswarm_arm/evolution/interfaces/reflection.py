"""ReflectionStrategy — GEPA proposes only; never mutates runtime."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping

from neuroswarm_arm.evolution.interfaces.knowledge import KnowledgeView


@dataclass(frozen=True, slots=True)
class Analysis:
    findings: tuple[str, ...]
    metrics: Mapping[str, float] = field(default_factory=dict)
    severity: float = 0.0


@dataclass(frozen=True, slots=True)
class Reflection:
    summary: str
    analysis: Analysis
    hypotheses: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PolicyDelta:
    """Proposed parameter changes — not applied until OptimizationEngine versions them."""

    parameters: Mapping[str, Any]
    target_layers: frozenset[str]
    rationale: str = ""
    expected_reward: float = 0.0
    confidence: float = 0.5
    source: str = "unknown"


@dataclass(frozen=True, slots=True)
class Recommendation:
    deltas: tuple[PolicyDelta, ...]
    priority: float = 0.0
    notes: str = ""


class ReflectionStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def analyze(self, knowledge: KnowledgeView) -> Analysis:
        raise NotImplementedError

    @abstractmethod
    def reflect(self, analysis: Analysis) -> Reflection:
        raise NotImplementedError

    @abstractmethod
    def propose(self, reflection: Reflection) -> list[PolicyDelta]:
        raise NotImplementedError

    def confidence(self, proposal: PolicyDelta) -> float:
        return float(proposal.confidence)

    def explain(self, proposal: PolicyDelta) -> str:
        return proposal.rationale or f"{self.name}: {dict(proposal.parameters)}"

    def recommend(self, knowledge: KnowledgeView) -> Recommendation:
        analysis = self.analyze(knowledge)
        reflection = self.reflect(analysis)
        deltas = self.propose(reflection)
        return Recommendation(deltas=tuple(deltas), priority=analysis.severity)

    def estimate_reward(self, proposal: PolicyDelta) -> float:
        return float(proposal.expected_reward)
