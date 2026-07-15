"""
Actionable Side Information (ASI) schemas.

Official concept: diagnostic feedback returned by evaluators — the
text-optimization analogue of a gradient (GEPA website / paper §3.2).

ArmCascade/AROP: ASI is observation evidence only; Performix never optimizes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ReflectiveRecord:
    """One reflective-dataset row (official recommended schema)."""

    Inputs: Mapping[str, str]
    Generated_Outputs: Mapping[str, str] | str
    Feedback: str
    score: float = 0.0
    metrics: Mapping[str, float] = field(default_factory=dict)
    extras: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "Inputs": dict(self.Inputs),
            "Generated Outputs": self.Generated_Outputs
            if isinstance(self.Generated_Outputs, str)
            else dict(self.Generated_Outputs),
            "Feedback": self.Feedback,
            "score": self.score,
            "metrics": dict(self.metrics),
            **dict(self.extras),
        }


@dataclass(frozen=True, slots=True)
class ActionableSideInformation:
    """Structured GEPA evidence assembled from runtime observations."""

    episode_id: str
    collected_at: datetime
    sources: tuple[str, ...]
    metrics: Mapping[str, float]
    records: tuple[ReflectiveRecord, ...]
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls, episode_id: str = "empty") -> ActionableSideInformation:
        return cls(
            episode_id=episode_id,
            collected_at=_utcnow(),
            sources=(),
            metrics={},
            records=(),
        )

    def feedback_text(self) -> str:
        parts = [r.Feedback for r in self.records if r.Feedback]
        if self.metrics:
            top = ", ".join(f"{k}={v:.4g}" for k, v in list(self.metrics.items())[:12])
            parts.append(f"Aggregate metrics: {top}")
        return "\n".join(parts) if parts else "No ASI available."
