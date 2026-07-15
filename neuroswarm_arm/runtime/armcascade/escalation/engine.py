"""Escalation policy graphs (arbitrary DAGs)."""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import EscalationEngine
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    EscalationEdge,
    EscalationGraph,
    EscalationState,
)


class GraphEscalationEngine(EscalationEngine):
    def next(self, graph: EscalationGraph, state: EscalationState) -> EscalationEdge | None:
        candidates = [e for e in graph.edges if e.source == state.current]
        if not candidates:
            return None

        scored: list[tuple[float, EscalationEdge]] = []
        for edge in candidates:
            if not self._matches(edge.condition, state):
                continue
            # Prefer higher weight; avoid revisiting targets when possible.
            penalty = 0.5 if edge.target in state.visited else 0.0
            scored.append((edge.weight - penalty, edge))

        if not scored:
            # Fallback: unconditional edges only.
            for edge in candidates:
                if edge.condition == "always":
                    return edge
            return candidates[0]

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def _matches(self, condition: str, state: EscalationState) -> bool:
        c = (condition or "always").lower()
        if c == "always":
            return True
        if c == "high_confidence":
            return state.confidence >= 0.7
        if c == "low_confidence":
            return state.confidence < 0.7
        if c == "tool_needed":
            return state.tool_needed
        if c == "memory_needed":
            return state.memory_needed
        return False
