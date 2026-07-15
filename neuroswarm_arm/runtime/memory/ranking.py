"""Post-Mem0 policy re-rank — does NOT replace Mem0 hybrid retrieval.

Mem0 owns semantic + BM25 + entity fusion. This module only blends
importance / confidence / time-decay onto already-retrieved Mem0 hits.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from neuroswarm_arm.runtime.memory.schemas import SearchHit


class RankingEngine:
    """Metadata/importance re-rank AFTER official Mem0 scores."""

    def fuse(
        self,
        hits: list[SearchHit],
        *,
        time_decay: bool = True,
        importance_weight: float = 0.2,
        confidence_weight: float = 0.1,
        mem0_weight: float = 0.55,
        now: datetime | None = None,
    ) -> list[SearchHit]:
        now = now or datetime.now(timezone.utc)
        ranked: list[SearchHit] = []
        for hit in hits:
            rec = hit.record
            age_h = max(0.0, (now - rec.timestamp).total_seconds() / 3600.0)
            decay = math.exp(-age_h / 168.0) if time_decay else 1.0
            # Preserve Mem0 hybrid score as primary signal
            mem0_score = float(hit.signals.get("mem0_hybrid") or hit.signals.get("mem0") or hit.score)
            rest = max(0.0, 1.0 - mem0_weight - importance_weight - confidence_weight)
            fused = (
                mem0_weight * mem0_score
                + importance_weight * rec.importance
                + confidence_weight * rec.confidence
                + rest * decay
            )
            signals = dict(hit.signals)
            signals.update({"fused": fused, "decay": decay, "mem0": mem0_score, "post_policy": True})
            ranked.append(SearchHit(record=rec, score=fused, signals=signals))
        ranked.sort(key=lambda h: h.score, reverse=True)
        return ranked
