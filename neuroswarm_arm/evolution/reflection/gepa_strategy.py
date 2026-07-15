"""
Reflection strategies for AROP.

GEPAReflectionStrategy — text-only Genetic-Pareto facade (official GEPA).
Does NOT emit numeric knob PolicyDeltas (those are RuleBased only).

Official: https://github.com/gepa-ai/gepa
"""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.evolution.interfaces.knowledge import KnowledgeView
from neuroswarm_arm.evolution.interfaces.reflection import (
    Analysis,
    PolicyDelta,
    Reflection,
    ReflectionStrategy,
)
from neuroswarm_arm.evolution.reflection.rule_strategy import RuleBasedReflectionStrategy


class GEPAReflectionStrategy(ReflectionStrategy):
    """
    GEPA as ReflectionStrategy: runs text candidate evolution via GEPAFacade.

    propose() returns empty PolicyDelta list by design — GEPA optimizes
    ``dict[str, str]`` text components, not RuntimePolicy knobs.
    Use ``last_result`` / ``facade`` for TextCandidates.
    """

    name = "gepa"

    def __init__(
        self,
        facade: Any | None = None,
        *,
        seed_components: dict[str, str] | None = None,
        max_iterations: int = 2,
    ) -> None:
        self.facade = facade
        self.seed_components = seed_components or {
            "system_prompt": "You are a helpful NEXUS-ARM assistant. Be concise and accurate.",
            "governor_policy": "# Governor policy\nPrefer short reasoning when confidence is high.\n",
        }
        self.max_iterations = max_iterations
        self.last_result: Any | None = None
        self._ensure_facade()

    def _ensure_facade(self) -> None:
        if self.facade is not None:
            return
        from neuroswarm_arm.evolution.reflection.gepa import GEPAFacade

        self.facade = GEPAFacade()

    def analyze(self, knowledge: KnowledgeView) -> Analysis:
        m = dict(knowledge.aggregate_metrics)
        findings = ("gepa_text_optimize",)
        severity = 0.2
        if m.get("ascr_accept_rate", m.get("accept_rate", 1.0)) < 0.55:
            findings = ("gepa_text_optimize", "low_accept_signal_for_prompt_review")
            severity = 0.5
        return Analysis(findings=findings, metrics=m, severity=severity)

    def reflect(self, analysis: Analysis) -> Reflection:
        self._ensure_facade()
        observations = [
            {
                "source": "knowledge",
                "metrics": dict(analysis.metrics),
                "labels": {"layer": "arop"},
            }
        ]
        asi = self.facade.reflect(observations=observations, metrics=dict(analysis.metrics))
        return Reflection(
            summary=asi.feedback_text()[:500],
            analysis=analysis,
            hypotheses=("gepa_reflective_mutation", "pareto_select", "system_aware_merge"),
        )

    def propose(self, reflection: Reflection) -> list[PolicyDelta]:
        """
        Run local GEPA text loop. Intentionally returns no knob PolicyDeltas.

        Text candidates are available on ``self.last_result``.
        """
        self._ensure_facade()
        trainset = [
            {"id": "t0", "input": "summarize cascade failure", "expected": "ok"},
            {"id": "t1", "input": "route tools for research", "expected": "ok"},
        ]
        self.last_result = self.facade.run_local_loop(
            self.seed_components,
            trainset=trainset,
            max_iterations=self.max_iterations,
            use_merge=True,
        )
        # Empty — GEPA must not mutate numeric knobs via PolicyDelta
        return []


class OfflineLLMReflectionStrategy(ReflectionStrategy):
    """Non-GEPA offline LLM stub — still knob-oriented via rule fallback."""

    name = "offline_llm"

    def __init__(self) -> None:
        self._fallback = RuleBasedReflectionStrategy()

    def analyze(self, knowledge: KnowledgeView) -> Analysis:
        return self._fallback.analyze(knowledge)

    def reflect(self, analysis: Analysis) -> Reflection:
        r = self._fallback.reflect(analysis)
        return Reflection(
            summary=f"offline_llm:{r.summary}",
            analysis=analysis,
            hypotheses=r.hypotheses,
        )

    def propose(self, reflection: Reflection) -> list[PolicyDelta]:
        deltas = self._fallback.propose(reflection)
        return [
            PolicyDelta(
                parameters=d.parameters,
                target_layers=d.target_layers,
                rationale=f"offline_llm:{d.rationale}",
                expected_reward=d.expected_reward,
                confidence=d.confidence,
                source=self.name,
            )
            for d in deltas
        ]


class HybridReflectionStrategy(ReflectionStrategy):
    """
    Hybrid = RuleBased (knobs) + GEPA (text).

    Knob deltas come only from RuleBased. GEPA runs text evolution side-effect
    via GEPAReflectionStrategy.propose (empty deltas).
    """

    name = "hybrid"

    def __init__(
        self,
        strategies: list[ReflectionStrategy] | None = None,
        *,
        gepa_facade: Any | None = None,
    ) -> None:
        self.rule = RuleBasedReflectionStrategy()
        self.gepa = GEPAReflectionStrategy(facade=gepa_facade)
        self.strategies = strategies or [self.rule, self.gepa]

    def analyze(self, knowledge: KnowledgeView) -> Analysis:
        analyses = [s.analyze(knowledge) for s in self.strategies]
        findings = tuple(dict.fromkeys(f for a in analyses for f in a.findings))
        severity = max((a.severity for a in analyses), default=0.0)
        metrics = dict(analyses[0].metrics) if analyses else {}
        return Analysis(findings=findings, metrics=metrics, severity=severity)

    def reflect(self, analysis: Analysis) -> Reflection:
        hyps = tuple(
            dict.fromkeys(h for s in self.strategies for h in s.reflect(analysis).hypotheses)
        )
        return Reflection(
            summary=analysis.findings[0] if analysis.findings else "hybrid",
            analysis=analysis,
            hypotheses=hyps,
        )

    def propose(self, reflection: Reflection) -> list[PolicyDelta]:
        # Run GEPA text loop for side effects (candidates), ignore empty deltas
        self.gepa.propose(reflection)
        # Only rule-based knob deltas
        deltas = self.rule.propose(reflection)
        return [
            PolicyDelta(
                parameters=d.parameters,
                target_layers=d.target_layers,
                rationale=f"hybrid_rule:{d.rationale}",
                expected_reward=d.expected_reward,
                confidence=d.confidence,
                source="rule",  # never label knobs as gepa
            )
            for d in deltas
        ]


class HumanReflectionStrategy(ReflectionStrategy):
    """Holds human-provided deltas; propose returns staged queue."""

    name = "human"

    def __init__(self) -> None:
        self._queue: list[PolicyDelta] = []

    def stage(self, delta: PolicyDelta) -> None:
        self._queue.append(delta)

    def analyze(self, knowledge: KnowledgeView) -> Analysis:
        return Analysis(findings=("human_review",), metrics=dict(knowledge.aggregate_metrics), severity=0.0)

    def reflect(self, analysis: Analysis) -> Reflection:
        return Reflection(summary="human", analysis=analysis, hypotheses=("human_staged",))

    def propose(self, reflection: Reflection) -> list[PolicyDelta]:
        out = list(self._queue)
        self._queue.clear()
        return out
