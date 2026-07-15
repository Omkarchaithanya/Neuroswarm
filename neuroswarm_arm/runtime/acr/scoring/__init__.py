"""Context Scoring Engine — unified multi-signal scores."""

from __future__ import annotations

import re

from neuroswarm_arm.runtime.acr.ir.bundles import KnowledgeBundle, MemoryBundle
from neuroswarm_arm.runtime.acr.ir.requirement import ContextRequirementGraph


class ScoringEngine:
    """Composite relevance scoring for memory + knowledge items."""

    def score_memory(self, bundle: MemoryBundle, graph: ContextRequirementGraph) -> MemoryBundle:
        terms = set(t.lower() for t in graph.topics + graph.entities)
        q_terms = set(re.findall(r"[a-z0-9_\-]{3,}", (graph.query or "").lower()))
        terms |= q_terms
        for item in bundle.items:
            low = item.content.lower()
            overlap = sum(1 for t in terms if t in low) / max(1, len(terms))
            relevance = overlap
            freshness = float(item.signals.get("freshness", 0.5))
            usage = float(item.signals.get("usage", 0.0))
            conflict = float(item.signals.get("conflict_risk", 0.0))
            composite = (
                0.35 * relevance
                + 0.25 * item.importance
                + 0.15 * item.confidence
                + 0.10 * freshness
                + 0.10 * usage
                + 0.05 * (1.0 - conflict)
            )
            item.score = composite
            item.signals = {
                **item.signals,
                "relevance": relevance,
                "importance": item.importance,
                "confidence": item.confidence,
                "freshness": freshness,
                "usage": usage,
                "conflict_risk": conflict,
                "composite": composite,
            }
        bundle.items.sort(key=lambda i: -i.score)
        return bundle

    def score_knowledge(
        self, bundle: KnowledgeBundle, graph: ContextRequirementGraph
    ) -> KnowledgeBundle:
        terms = set(t.lower() for t in graph.topics + graph.entities)
        q_terms = set(re.findall(r"[a-z0-9_\-]{3,}", (graph.query or "").lower()))
        terms |= q_terms
        for item in bundle.items:
            low = item.content.lower()
            overlap = sum(1 for t in terms if t in low) / max(1, len(terms))
            kind_boost = {"policy": 0.05, "tool_docs": 0.1, "knowledge": 0.0}.get(item.kind, 0.0)
            composite = 0.55 * overlap + 0.35 * item.score + kind_boost
            item.score = min(1.0, composite)
            item.metadata["signals"] = {
                "relevance": overlap,
                "planning_priority": item.score,
                "composite": item.score,
            }
        bundle.items.sort(key=lambda i: -i.score)
        return bundle
