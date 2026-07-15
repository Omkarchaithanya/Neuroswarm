"""Shared fixtures for Rollback Manager tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.rollback import (
    FailureObservation,
    RollbackBuilder,
    RollbackStrategyKind,
    build_rollback_manager,
)


def make_operation(**overrides):
    builder = (
        RollbackBuilder()
        .workflow("wf_test", execution_id="ex_test")
        .checkpoint("ckpt_test")
        .strategy(RollbackStrategyKind.RESUME_CHECKPOINT)
        .reason("test_failure")
        .targets("n_1", "n_2")
        .node("n_2")
    )
    op = builder.build()
    if overrides:
        data = op.model_dump(mode="python")
        data.pop("checksum", None)
        data.update(overrides)
        data["checksum"] = None
        from neuroswarm_arm.runtime.swarm.rollback import RollbackOperation

        return RollbackOperation.model_validate(data)
    return op


def make_failure(**overrides):
    data = {
        "workflow_id": "wf_test",
        "execution_id": "ex_test",
        "failed_nodes": ["n_2"],
        "completed_nodes": ["n_1"],
        "checkpoint_reference": "ckpt_test",
        "reason": "test_failure",
        "node_id": "n_2",
    }
    data.update(overrides)
    return FailureObservation.model_validate(data)


def fresh_manager(**kwargs):
    return build_rollback_manager(**kwargs)


class FakeCheckpointPort:
    def __init__(self, ids: set[str] | None = None) -> None:
        self.ids = set(ids or {"ckpt_test"})
        self.payloads = {i: {"checkpoint_id": i} for i in self.ids}

    def checkpoint_exists(self, checkpoint_id: str) -> bool:
        return checkpoint_id in self.ids

    def get_checkpoint(self, checkpoint_id: str):
        return self.payloads[checkpoint_id]


class FakeRecoveryPort:
    def __init__(self, ids: set[str] | None = None) -> None:
        self.ids = set(ids or {"rplan_test"})

    def recovery_plan_exists(self, plan_id: str) -> bool:
        return plan_id in self.ids

    def get_recovery_plan(self, plan_id: str):
        return {"plan_id": plan_id}


class FakeTaskGraphPort:
    def __init__(self, nodes: list[str] | None = None) -> None:
        self._nodes = list(nodes or ["n_1", "n_2", "n_3"])

    def get_graph(self, graph_id: str | None = None):
        return {"nodes": self._nodes, "graph_id": graph_id}

    def node_ids(self):
        return list(self._nodes)

    def predecessors(self, node_id: str):
        return []

    def successors(self, node_id: str):
        return []
