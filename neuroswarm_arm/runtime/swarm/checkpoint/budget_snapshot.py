"""Immutable budget envelope snapshot (scalars / refs only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from ._utils import new_id, stable_hash, utc_now
from .models import _Frozen


class BudgetSnapshot(_Frozen):
    """Frozen budget remnant at checkpoint time — no ARMORA imports."""

    snapshot_id: str = Field(default_factory=lambda: new_id("bsnap_"))
    envelope_id: str | None = None
    max_cost_usd: float | None = None
    max_latency_ms: float | None = None
    max_tokens: int | None = None
    remaining_cost_usd: float | None = None
    remaining_latency_ms: float | None = None
    remaining_tokens: int | None = None
    content_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _hash(self) -> BudgetSnapshot:
        if self.content_hash:
            return self
        payload = {
            "envelope_id": self.envelope_id,
            "max_cost_usd": self.max_cost_usd,
            "max_latency_ms": self.max_latency_ms,
            "max_tokens": self.max_tokens,
            "remaining_cost_usd": self.remaining_cost_usd,
            "remaining_latency_ms": self.remaining_latency_ms,
            "remaining_tokens": self.remaining_tokens,
        }
        object.__setattr__(self, "content_hash", stable_hash(payload))
        return self
