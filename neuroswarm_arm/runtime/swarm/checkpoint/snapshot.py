"""Immutable reference-only snapshot base types."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from ._utils import new_id, stable_hash, utc_now
from .models import ArtifactReference, _Frozen


class MetricsSnapshot(_Frozen):
    """Frozen metrics sample attached to a checkpoint (scalars / refs only)."""

    snapshot_id: str = Field(default_factory=lambda: new_id("msnap_"))
    counters: dict[str, float] = Field(default_factory=dict)
    gauges: dict[str, float] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    content_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _hash(self) -> MetricsSnapshot:
        if self.content_hash:
            return self
        payload = {
            "counters": self.counters,
            "gauges": self.gauges,
            "labels": self.labels,
        }
        object.__setattr__(self, "content_hash", stable_hash(payload))
        return self


class SnapshotBundle(_Frozen):
    """Bundle of snapshot references carried by a Checkpoint."""

    artifacts: list[ArtifactReference] = Field(default_factory=list)
    metrics: MetricsSnapshot | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
