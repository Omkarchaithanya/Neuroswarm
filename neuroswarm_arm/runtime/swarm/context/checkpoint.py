"""Checkpoint metadata — integrate with future Checkpoint Manager (no I/O)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ._utils import new_id, utc_now
from .context import SwarmContext
from .events import CheckpointCreated, CheckpointRestored, EventBus
from .exceptions import CheckpointError
from .models import _Base
from .snapshot import SwarmContextSnapshot, create_snapshot, restore_snapshot


class CheckpointMetadata(_Base):
    """Describe a checkpoint without persisting payloads."""

    checkpoint_id: str = Field(default_factory=lambda: new_id("ckpt_"))
    context_id: str = ""
    snapshot_id: str = ""
    content_hash: str = ""
    node_id: str | None = None
    label: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RestoreMetadata(_Base):
    """Describe a restore operation (no storage backend)."""

    restore_id: str = Field(default_factory=lambda: new_id("rst_"))
    checkpoint_id: str = ""
    snapshot_id: str = ""
    context_id: str = ""
    restored_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_checkpoint(
    ctx: SwarmContext,
    *,
    node_id: str | None = None,
    label: str = "",
    events: EventBus | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[CheckpointMetadata, SwarmContextSnapshot, SwarmContext]:
    """Create checkpoint metadata + immutable snapshot; return updated context."""
    snap = create_snapshot(ctx, label=label or "checkpoint", events=events, metadata=metadata)
    meta = CheckpointMetadata(
        context_id=ctx.swarm_id,
        snapshot_id=snap.snapshot_id,
        content_hash=snap.content_hash,
        node_id=node_id or ctx.current_node,
        label=label,
        metadata=dict(metadata or {}),
    )
    updated = ctx.evolve(
        checkpoints=list(ctx.checkpoints) + [meta.checkpoint_id],
        snapshot_id=snap.snapshot_id,
        metrics=ctx.metrics.bump("checkpoint_count"),
        execution=ctx.execution.model_copy(
            update={
                "checkpoint_ids": list(ctx.execution.checkpoint_ids) + [meta.checkpoint_id],
            }
        ),
    ).append_history("checkpoint", summary=meta.checkpoint_id, node_id=node_id or "")
    if events is not None:
        events.emit(
            CheckpointCreated(
                ctx.swarm_id,
                checkpoint_id=meta.checkpoint_id,
                snapshot_id=snap.snapshot_id,
            )
        )
    return meta, snap, updated


def restore_checkpoint(
    meta: CheckpointMetadata,
    snap: SwarmContextSnapshot,
    *,
    events: EventBus | None = None,
) -> tuple[RestoreMetadata, SwarmContext]:
    if meta.snapshot_id and snap.snapshot_id != meta.snapshot_id:
        raise CheckpointError(
            f"snapshot_id mismatch: meta={meta.snapshot_id} snap={snap.snapshot_id}"
        )
    ctx = restore_snapshot(snap, events=events)
    restore = RestoreMetadata(
        checkpoint_id=meta.checkpoint_id,
        snapshot_id=snap.snapshot_id,
        context_id=ctx.swarm_id,
    )
    if events is not None:
        events.emit(
            CheckpointRestored(
                ctx.swarm_id,
                checkpoint_id=meta.checkpoint_id,
                snapshot_id=snap.snapshot_id,
            )
        )
    return restore, ctx
