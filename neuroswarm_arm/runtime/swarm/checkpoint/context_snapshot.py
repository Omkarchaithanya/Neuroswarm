"""Immutable Swarm Context snapshot reference (refs only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from ._utils import new_id, stable_hash, utc_now
from .models import _Frozen


class ContextSnapshot(_Frozen):
    """Pointer to a Swarm Context snapshot — no nested live context objects."""

    snapshot_id: str = Field(default_factory=lambda: new_id("csnap_"))
    context_id: str = ""
    context_snapshot_id: str | None = None
    content_hash: str | None = None
    version: str | None = None
    parent_snapshot_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _hash(self) -> ContextSnapshot:
        if self.content_hash:
            return self
        payload = {
            "context_id": self.context_id,
            "context_snapshot_id": self.context_snapshot_id,
            "version": self.version,
            "parent_snapshot_id": self.parent_snapshot_id,
        }
        object.__setattr__(self, "content_hash", stable_hash(payload))
        return self
