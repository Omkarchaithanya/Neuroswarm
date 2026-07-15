"""Strategy object tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.rollback import (
    CustomStrategy,
    RestartNodeStrategy,
    ResumeCheckpointStrategy,
    RollbackStrategyKind,
    strategy_for,
)


def test_resume_checkpoint_shapes_fields():
    s = ResumeCheckpointStrategy()
    out = s.apply_plan({"workflow_id": "wf", "execution_id": "ex"})
    assert out["rollback_strategy"] == RollbackStrategyKind.RESUME_CHECKPOINT


def test_restart_node_sets_targets():
    s = RestartNodeStrategy()
    out = s.apply_plan(
        {"workflow_id": "wf", "execution_id": "ex", "target_nodes": ["n_1"]}
    )
    assert out["target_node"] == "n_1"
    assert out["rollback_level"].value == "node"


def test_custom_strategy_overrides():
    s = CustomStrategy(strategy_id="my_custom", overrides={"reason": "custom"})
    out = s.apply_plan({"workflow_id": "wf", "execution_id": "ex", "reason": "old"})
    assert out["reason"] == "custom"
    assert out["metadata"]["custom_strategy_id"] == "my_custom"
    assert out["rollback_strategy"] == RollbackStrategyKind.CUSTOM


def test_strategy_for_factory():
    s = strategy_for("restart_workflow")
    assert s.kind == RollbackStrategyKind.RESTART_WORKFLOW
