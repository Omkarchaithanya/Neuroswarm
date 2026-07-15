"""ContextMetrics — in-process counters for the Context OS."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from .models import _Base


class ContextMetrics(_Base):
    """Track size, refs, budget usage, depth, snapshot/propagation/merge counts."""

    context_size_bytes: int = 0
    memory_ref_count: int = 0
    knowledge_ref_count: int = 0
    budget_usage_ratio: float = 0.0
    execution_depth: int = 0
    snapshot_count: int = 0
    propagation_count: int = 0
    merge_count: int = 0
    diff_count: int = 0
    checkpoint_count: int = 0
    custom: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "context_size_bytes",
        "memory_ref_count",
        "knowledge_ref_count",
        "execution_depth",
        "snapshot_count",
        "propagation_count",
        "merge_count",
        "diff_count",
        "checkpoint_count",
    )
    @classmethod
    def _non_neg(cls, v: int) -> int:
        if v < 0:
            raise ValueError("metric counters must be >= 0")
        return v

    @field_validator("budget_usage_ratio")
    @classmethod
    def _ratio(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("budget_usage_ratio must be >= 0")
        return v

    def bump(self, field: str, delta: int = 1) -> ContextMetrics:
        current = getattr(self, field, None)
        if not isinstance(current, int):
            raise ValueError(f"not an int counter: {field}")
        return self.model_copy(update={field: current + delta})

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")

    def export(self) -> dict[str, float]:
        out: dict[str, float] = {
            "nexus.swarm.context.size_bytes": float(self.context_size_bytes),
            "nexus.swarm.context.memory_refs": float(self.memory_ref_count),
            "nexus.swarm.context.knowledge_refs": float(self.knowledge_ref_count),
            "nexus.swarm.context.budget_usage_ratio": self.budget_usage_ratio,
            "nexus.swarm.context.execution_depth": float(self.execution_depth),
            "nexus.swarm.context.snapshots": float(self.snapshot_count),
            "nexus.swarm.context.propagations": float(self.propagation_count),
            "nexus.swarm.context.merges": float(self.merge_count),
            "nexus.swarm.context.diffs": float(self.diff_count),
            "nexus.swarm.context.checkpoints": float(self.checkpoint_count),
        }
        for k, v in self.custom.items():
            out[f"nexus.swarm.context.custom.{k}"] = v
        return out
