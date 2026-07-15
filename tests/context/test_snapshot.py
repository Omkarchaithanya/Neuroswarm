"""Snapshot + checkpoint tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.context import (
    EventBus,
    SwarmContextBuilder,
    compare_snapshots,
    create_checkpoint,
    create_snapshot,
    restore_checkpoint,
    restore_snapshot,
)


def test_snapshot_roundtrip():
    bus = EventBus()
    types: list[str] = []
    bus.subscribe(lambda e: types.append(e.type))
    ctx = SwarmContextBuilder(events=None).request(prompt="snap").budget(cost_usd_limit=1.0).build()
    snap = create_snapshot(ctx, label="t0", events=bus)
    assert snap.content_hash
    assert snap.label == "t0"
    restored = restore_snapshot(snap, events=bus)
    assert restored.request.prompt == "snap"
    assert restored.budget.cost_usd_limit == 1.0
    assert "SnapshotCreated" in types
    assert "SnapshotRestored" in types


def test_compare_snapshots():
    ctx = SwarmContextBuilder().request(prompt="x").build()
    a = create_snapshot(ctx)
    b = create_snapshot(ctx)
    cmp = compare_snapshots(a, b)
    assert cmp["same_hash"] is True


def test_checkpoint_create_restore():
    bus = EventBus()
    ctx = SwarmContextBuilder().request(prompt="ckpt").execution(run_id="r1").build()
    meta, snap, updated = create_checkpoint(ctx, node_id="n1", label="mid", events=bus)
    assert meta.checkpoint_id in updated.checkpoints
    assert updated.metrics.checkpoint_count >= 1
    restore_meta, restored = restore_checkpoint(meta, snap, events=bus)
    assert restore_meta.checkpoint_id == meta.checkpoint_id
    assert restored.request.prompt == "ckpt"
