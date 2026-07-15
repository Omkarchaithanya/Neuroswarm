"""Shared fixtures for Checkpoint Manager tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.checkpoint import (
    BudgetSnapshot,
    CheckpointBuilder,
    CheckpointLevel,
    ContextSnapshot,
    ExecutionSnapshot,
    GraphSnapshot,
    MetricsSnapshot,
    build_checkpoint_manager,
)


def make_checkpoint(**overrides):
    builder = (
        CheckpointBuilder()
        .workflow("wf_test", execution_id="ex_test")
        .execution(
            snapshot=ExecutionSnapshot(
                execution_id="ex_test",
                workflow_id="wf_test",
                completed_nodes=["n_1"],
            )
        )
        .context(ContextSnapshot(context_id="ctx_1", context_snapshot_id="snap_1"))
        .budget(BudgetSnapshot(envelope_id="env_1", remaining_cost_usd=0.5))
        .metrics(MetricsSnapshot(counters={"nodes": 1.0}))
        .graph(
            reference="g_1",
            snapshot=GraphSnapshot(
                graph_id="g_1",
                completed_nodes=["n_1"],
                frontier_nodes=["n_2"],
            ),
        )
        .level(CheckpointLevel.AUTOMATIC)
    )
    ckpt = builder.build()
    if overrides:
        data = ckpt.model_dump(mode="python")
        data.pop("checksum", None)
        data.update(overrides)
        data["checksum"] = None
        from neuroswarm_arm.runtime.swarm.checkpoint import Checkpoint

        return Checkpoint.model_validate(data)
    return ckpt


def fresh_manager(**kwargs):
    return build_checkpoint_manager(**kwargs)
