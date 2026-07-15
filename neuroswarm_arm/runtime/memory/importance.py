"""Importance scoring engine."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.memory.schemas import MemoryRecord


class ImportanceEngine:
    def __init__(self, config: MemoryRuntimeConfig) -> None:
        self.config = config

    def score(self, record: MemoryRecord, *, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        age_h = max(0.0, (now - record.timestamp).total_seconds() / 3600.0)
        recency = math.exp(-age_h / 72.0)  # ~3-day half-life shape
        frequency = min(1.0, math.log1p(record.access_count) / 5.0)
        success = max(0.0, min(1.0, record.success_score))
        # Lower cost → slightly higher importance for cheap reusable facts
        cost_signal = 1.0 / (1.0 + max(0.0, record.cost) * 10.0)
        reflection = float(record.metadata.get("reflection_score", record.confidence))
        workflow = 1.0 if record.workflow_id else 0.4
        cfg = self.config
        raw = (
            cfg.importance_recency_weight * recency
            + cfg.importance_frequency_weight * frequency
            + cfg.importance_success_weight * success
            + cfg.importance_cost_weight * cost_signal
            + cfg.importance_reflection_weight * reflection
            + cfg.importance_workflow_weight * workflow
        )
        return max(0.0, min(1.0, raw))

    def rescore(self, record: MemoryRecord) -> MemoryRecord:
        record.importance = self.score(record)
        return record
