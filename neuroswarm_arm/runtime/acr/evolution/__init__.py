"""Context Evolution Engine — post-request learning + recommendations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from neuroswarm_arm.runtime.acr.ir.context import ContextSnapshot


@dataclass
class EvolutionRecord:
    request_id: str
    success: bool
    cost: float = 0.0
    latency_ms: float = 0.0
    compression_ratio: float = 1.0
    token_reduction: float = 0.0
    information_retained: float = 1.0
    retrieval_usefulness: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class EvolutionEngine:
    """Every completed request becomes learning for Layer 5 self-opt loop."""

    def __init__(self, memory: Any | None = None) -> None:
        self._memory = memory
        self._records: list[EvolutionRecord] = []

    def record(
        self,
        snapshot: ContextSnapshot,
        *,
        success: bool,
        cost: float = 0.0,
        latency_ms: float = 0.0,
        owner: str = "default",
        usefulness: float | None = None,
    ) -> list[str]:
        comp = snapshot.stats.compression
        usefulness_v = usefulness if usefulness is not None else (
            snapshot.stats.requirement_coverage or comp.information_retained
        )
        recs = self._recommend(snapshot, success=success, usefulness=usefulness_v)
        rec = EvolutionRecord(
            request_id=snapshot.request_id,
            success=success,
            cost=cost,
            latency_ms=latency_ms or snapshot.stats.total_latency_ms,
            compression_ratio=comp.compression_ratio,
            token_reduction=comp.token_reduction,
            information_retained=comp.information_retained,
            retrieval_usefulness=usefulness_v,
            recommendations=recs,
            metadata={"plan_id": snapshot.plan_id, "version": snapshot.version.version_id},
        )
        self._records.append(rec)
        if len(self._records) > 500:
            self._records = self._records[-250:]
        self._persist(rec, owner=owner, snapshot=snapshot)
        return recs

    def recommendations(self, limit: int = 10) -> list[str]:
        out: list[str] = []
        for r in reversed(self._records):
            out.extend(r.recommendations)
            if len(out) >= limit:
                break
        return out[:limit]

    def _recommend(self, snapshot: ContextSnapshot, *, success: bool, usefulness: float) -> list[str]:
        recs: list[str] = []
        comp = snapshot.stats.compression
        if comp.token_reduction < 0.1 and snapshot.stats.input_tokens > 500:
            recs.append("compression: enable stricter importance_filter / pack budget")
        if comp.information_retained < 0.6:
            recs.append("retrieval: raise must_have coverage; expand memory namespaces")
        if snapshot.stats.planning_latency_ms > 50:
            recs.append("planning: cache RetrievalExecutionPlan for similar intents")
        if snapshot.stats.cache_hit is False and snapshot.stats.total_latency_ms > 100:
            recs.append("cache: warm planning/assembly tiers for agent_role")
        if not success:
            recs.append("ranking: boost reflection/reasoning namespaces after failure")
        if usefulness < 0.4:
            recs.append("planner: reduce lazy tool_docs; prefer eager policy+knowledge")
        if not recs:
            recs.append("ok: maintain current compression/planning profile")
        return recs

    def _persist(self, rec: EvolutionRecord, *, owner: str, snapshot: ContextSnapshot) -> None:
        neuro = self._memory
        if neuro is None:
            return
        if hasattr(neuro, "neuro"):
            neuro = getattr(neuro, "neuro", neuro)
        text = (
            f"acr_evolution success={rec.success} ratio={rec.compression_ratio:.3f} "
            f"retain={rec.information_retained:.3f} recs={';'.join(rec.recommendations)}"
        )
        try:
            if hasattr(neuro, "remember_evolution"):
                neuro.remember_evolution(
                    text,
                    owner=owner,
                    tags=["acr", "evolution"],
                    metadata={"request_id": rec.request_id, "version": snapshot.version.version_id},
                )
            elif hasattr(neuro, "remember_reflection"):
                neuro.remember_reflection(
                    text,
                    owner=owner,
                    tags=["acr", "evolution"],
                    metadata={"request_id": rec.request_id, "version": snapshot.version.version_id},
                )
            elif hasattr(neuro, "remember_fact"):
                neuro.remember_fact(text, owner=owner, tags=["acr", "evolution"])
        except Exception:
            return
