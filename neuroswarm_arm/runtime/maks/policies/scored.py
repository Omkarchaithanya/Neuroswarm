"""Scored eviction — never plain LRU by default for Memory OS."""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..interfaces import IEvictionPolicy
from ..models import KVRegistryRecord


@dataclass
class EvictionWeights:
    """Modular score weights. Higher score = keep; victims = lowest scores."""

    recency: float = 1.0
    frequency: float = 1.0
    sharing: float = 2.0
    importance: float = 1.5
    prediction: float = 1.0
    pressure_bias: float = 0.5
    cascade_stage: float = 0.75
    reasoning_depth: float = 0.5


class ScoredEvictionPolicy(IEvictionPolicy):
    """
    Score = w_r*recency + w_f*freq + w_s*share + w_i*importance
          + w_p*prediction + w_c*cascade + w_d*depth - pressure_bias

    Never evict pinned. Prefer low score victims.
    """

    def __init__(
        self,
        weights: EvictionWeights | None = None,
        *,
        pressure: float = 0.0,
        page_signals: dict[str, dict] | None = None,
    ) -> None:
        self.weights = weights or EvictionWeights()
        self.pressure = pressure
        self.page_signals = page_signals or {}

    def set_pressure(self, pressure: float) -> None:
        self.pressure = float(pressure)

    def set_page_signals(self, signals: dict[str, dict]) -> None:
        self.page_signals = signals

    def score(self, rec: KVRegistryRecord) -> float:
        now = time.time()
        age_s = max(0.0, now - (rec.last_access or rec.created_at or now))
        # recency in [0,1]: recently accessed → high
        recency = 1.0 / (1.0 + age_s / 60.0)
        freq = min(1.0, (rec.access_count or 0) / 20.0)
        share = min(1.0, max(0, rec.refcount - 1) / 5.0)
        sig = self.page_signals.get(rec.kv_id, {})
        importance = float(sig.get("importance", rec.priority / 10.0 if rec.priority else 0.0))
        prediction = float(sig.get("prediction_score", 0.0))
        cascade = min(1.0, float(sig.get("cascade_stage", 0)) / 5.0)
        depth = min(1.0, float(sig.get("reasoning_depth", 0)) / 10.0)
        w = self.weights
        return (
            w.recency * recency
            + w.frequency * freq
            + w.sharing * share
            + w.importance * importance
            + w.prediction * prediction
            + w.cascade_stage * cascade
            + w.reasoning_depth * depth
            - w.pressure_bias * self.pressure
        )

    def select_victims(
        self,
        records: list[KVRegistryRecord],
        *,
        bytes_needed: int = 0,
        count: int = 1,
    ) -> list[str]:
        candidates = [r for r in records if not r.pinned and r.refcount <= 1]
        scored = sorted(candidates, key=self.score)  # lowest first
        out: list[str] = []
        freed = 0
        for rec in scored:
            out.append(rec.kv_id)
            freed += rec.metadata.kv_size
            if bytes_needed > 0 and freed >= bytes_needed:
                break
            if bytes_needed <= 0 and len(out) >= count:
                break
        return out
