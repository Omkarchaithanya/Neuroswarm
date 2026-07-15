"""Recovery planning tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.checkpoint import (
    FailureContext,
    RecoveryStrategy,
)

from .conftest import fresh_manager, make_checkpoint


def test_resume_from_latest_checkpoint() -> None:
    mgr = fresh_manager()
    mgr.checkpoint(make_checkpoint())
    plan = mgr.plan_recovery(
        FailureContext(
            workflow_id="wf_test",
            execution_id="ex_test",
            failed_nodes=["n_2"],
            reason="node_fail",
        )
    )
    assert plan.strategy == RecoveryStrategy.RESUME_CHECKPOINT
    assert plan.checkpoint_id
    assert plan.rollback_notify is True


def test_restart_when_no_checkpoints() -> None:
    mgr = fresh_manager()
    plan = mgr.plan_recovery(
        FailureContext(workflow_id="wf_x", execution_id="ex_x", reason="boom")
    )
    assert plan.strategy == RecoveryStrategy.RESTART_WORKFLOW


def test_prefer_node_resume() -> None:
    mgr = fresh_manager()
    mgr.checkpoint(make_checkpoint())
    plan = mgr.plan_recovery(
        FailureContext(
            workflow_id="wf_test",
            execution_id="ex_test",
            node_id="n_2",
            failed_nodes=["n_2"],
        ),
        prefer_node=True,
    )
    assert plan.strategy == RecoveryStrategy.RESUME_NODE
    assert plan.resume_node_id == "n_2"


def test_prefer_subgraph_resume() -> None:
    mgr = fresh_manager()
    from neuroswarm_arm.runtime.swarm.checkpoint import GraphSnapshot

    mgr.checkpoint(
        make_checkpoint(
            graph_snapshot=GraphSnapshot(
                graph_id="g_1", subgraph_id="sg_1", completed_nodes=["n_1"]
            )
        )
    )
    plan = mgr.plan_recovery(
        FailureContext(
            workflow_id="wf_test",
            execution_id="ex_test",
            subgraph_id="sg_1",
            failed_nodes=["n_3"],
        ),
        prefer_subgraph=True,
    )
    assert plan.strategy == RecoveryStrategy.RESUME_SUBGRAPH
    assert plan.resume_subgraph_id == "sg_1"
