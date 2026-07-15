"""Checkpoint creation + builder tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.checkpoint import (
    CheckpointBuilder,
    CheckpointLevel,
    DuplicateCheckpointError,
    ExecutionSnapshot,
)

from .conftest import fresh_manager, make_checkpoint


def test_builder_creates_immutable_checkpoint() -> None:
    ckpt = make_checkpoint()
    assert ckpt.checkpoint_id.startswith("ckpt_")
    assert ckpt.workflow_id == "wf_test"
    assert ckpt.checksum
    assert ckpt.verify_checksum()
    assert ckpt.checkpoint_level == CheckpointLevel.AUTOMATIC


def test_clone_gets_new_id_and_parent() -> None:
    ckpt = make_checkpoint()
    clone = ckpt.clone(checkpoint_level=CheckpointLevel.MANUAL)
    assert clone.checkpoint_id != ckpt.checkpoint_id
    assert clone.parent_checkpoint == ckpt.checkpoint_id
    assert clone.checkpoint_level == CheckpointLevel.MANUAL
    assert clone.verify_checksum()


def test_manager_persists_checkpoint() -> None:
    mgr = fresh_manager()
    stored = mgr.checkpoint(make_checkpoint())
    got = mgr.get(stored.checkpoint_id)
    assert got.checkpoint_id == stored.checkpoint_id
    assert mgr.metrics.checkpoint_count == 1
    assert mgr.metrics.snapshot_count >= 1


def test_duplicate_id_rejected() -> None:
    mgr = fresh_manager()
    ckpt = make_checkpoint(checkpoint_id="ckpt_fixed")
    mgr.checkpoint(ckpt)
    try:
        mgr.checkpoint(make_checkpoint(checkpoint_id="ckpt_fixed"))
        raise AssertionError("expected DuplicateCheckpointError")
    except DuplicateCheckpointError:
        pass


def test_builder_requires_ids() -> None:
    try:
        CheckpointBuilder().build()
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_fluent_api_example() -> None:
    ckpt = (
        CheckpointBuilder()
        .workflow("wf_1", execution_id="ex_1")
        .execution(
            snapshot=ExecutionSnapshot(
                execution_id="ex_1", workflow_id="wf_1", completed_nodes=["a"]
            )
        )
        .level(CheckpointLevel.BARRIER)
        .build()
    )
    assert ckpt.checkpoint_level == CheckpointLevel.BARRIER
