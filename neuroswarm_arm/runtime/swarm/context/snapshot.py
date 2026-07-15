"""Immutable SwarmContext snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from ._utils import new_id, stable_hash, utc_now
from .context import SwarmContext
from .events import EventBus, SnapshotCreated, SnapshotRestored
from .exceptions import SnapshotError
from .models import _Frozen


class SwarmContextSnapshot(_Frozen):
    """Immutable deep-frozen view of a SwarmContext."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str = Field(default_factory=lambda: new_id("snap_"))
    context_id: str = ""
    content_hash: str = ""
    version: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    label: str = ""
    parent_snapshot_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")


def create_snapshot(
    ctx: SwarmContext,
    *,
    label: str = "",
    parent_snapshot_id: str | None = None,
    events: EventBus | None = None,
    metadata: dict[str, Any] | None = None,
) -> SwarmContextSnapshot:
    payload = ctx.model_dump(mode="json")
    snap = SwarmContextSnapshot(
        snapshot_id=new_id("snap_"),
        context_id=ctx.swarm_id,
        content_hash=stable_hash(payload),
        version=ctx.version,
        label=label,
        parent_snapshot_id=parent_snapshot_id,
        payload=payload,
        metadata=dict(metadata or {}),
    )
    if events is not None:
        events.emit(
            SnapshotCreated(
                ctx.swarm_id,
                snapshot_id=snap.snapshot_id,
                content_hash=snap.content_hash,
            )
        )
    return snap


def restore_snapshot(
    snap: SwarmContextSnapshot,
    *,
    events: EventBus | None = None,
) -> SwarmContext:
    if not snap.payload:
        raise SnapshotError("snapshot payload empty")
    data = dict(snap.payload)
    data["snapshot_id"] = snap.snapshot_id
    data["updated_at"] = utc_now().isoformat()
    ctx = SwarmContext.model_validate(data)
    if events is not None:
        events.emit(
            SnapshotRestored(
                ctx.swarm_id,
                snapshot_id=snap.snapshot_id,
                content_hash=snap.content_hash,
            )
        )
    return ctx


def compare_snapshots(a: SwarmContextSnapshot, b: SwarmContextSnapshot) -> dict[str, Any]:
    return {
        "same_hash": a.content_hash == b.content_hash,
        "a_id": a.snapshot_id,
        "b_id": b.snapshot_id,
        "a_hash": a.content_hash,
        "b_hash": b.content_hash,
        "a_version": a.version,
        "b_version": b.version,
    }
