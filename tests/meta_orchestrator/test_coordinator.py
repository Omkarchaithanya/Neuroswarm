"""Async coordinator / orchestrator integration tests."""

from __future__ import annotations

import asyncio

from neuroswarm_arm.runtime.swarm.meta_orchestrator import (
    WorkflowBuilder,
    WorkflowStatus,
    build_meta_orchestrator,
)
from neuroswarm_arm.runtime.swarm.task_graph import TaskGraphBuilder

from .conftest import MockCatalog, MockHaoePort, fan_graph, linear_graph, simple_context


def test_linear_workflow_completes() -> None:
    async def _run():
        haoe = MockHaoePort()
        orch = build_meta_orchestrator(haoe=haoe, catalog=MockCatalog())
        return await (
            WorkflowBuilder()
            .graph(linear_graph())
            .context(simple_context())
            .agents(["agent-1"])
            .execute(orch)
        )

    ex = asyncio.run(_run())
    assert ex.status == WorkflowStatus.COMPLETED
    assert len(ex.completed_nodes) == 3
    assert len(ex.aggregated.outputs) >= 1


def test_fan_in_workflow_completes() -> None:
    async def _run():
        haoe = MockHaoePort()
        orch = build_meta_orchestrator(haoe=haoe)
        return await (
            WorkflowBuilder()
            .graph(fan_graph())
            .context(simple_context())
            .agents(["agent-1"])
            .execute(orch)
        )

    ex = asyncio.run(_run())
    assert ex.status == WorkflowStatus.COMPLETED
    assert len(ex.completed_nodes) == 4


def test_failure_then_skip_with_retries_exhausted() -> None:
    g = (
        TaskGraphBuilder(name="fail")
        .retry(max_attempts=1)
        .task("a")
        .build()
    )
    nid = next(iter(g.nodes))

    async def _run():
        haoe = MockHaoePort(fail_nodes={nid})
        orch = build_meta_orchestrator(haoe=haoe, fail_fast=False)
        return await (
            WorkflowBuilder()
            .graph(g)
            .context(simple_context())
            .agents(["agent-1"])
            .execute(orch)
        )

    ex = asyncio.run(_run())
    assert ex.status in {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}
    assert nid in ex.skipped_nodes or nid in ex.failed_nodes


def test_cancel() -> None:
    haoe = MockHaoePort()
    orch = build_meta_orchestrator(haoe=haoe)
    ex = orch.create(graph=linear_graph(), context=simple_context(), agents=["a1"])
    orch.cancel(ex, forced=True)
    assert ex.status == WorkflowStatus.CANCELLED


def test_checkpoint_and_restore() -> None:
    class CK:
        def __init__(self) -> None:
            self.store: dict = {}

        def create(self, metadata):
            cid = "ckpt_1"
            self.store[cid] = metadata
            return cid

        def restore(self, checkpoint_id: str):
            return self.store.get(checkpoint_id)

    class ES:
        def __init__(self) -> None:
            self.blobs: dict = {}

        def store_snapshot(self, snapshot):
            hid = "snap_1"
            self.blobs[hid] = snapshot
            return hid

        def load_snapshot(self, handle: str):
            return self.blobs[handle]

    from neuroswarm_arm.runtime.swarm.meta_orchestrator.workflow_state import WorkflowStatus as WS

    haoe = MockHaoePort()
    orch = build_meta_orchestrator(
        haoe=haoe, checkpoint_manager=CK(), experience_store=ES()
    )
    ex = orch.create(graph=linear_graph(), context=simple_context(), agents=["a1"])
    orch.lifecycle.mark_ready(ex)
    orch.lifecycle.mark_running(ex)
    ex.completed_nodes = [ex.pending_nodes[0]]
    handle = orch.checkpoint(ex)
    assert handle.checkpoint_id
    assert ex.status == WS.CHECKPOINTED
    restored = orch.restore(ex, handle.checkpoint_id)
    assert restored.checkpoint_reference == handle.checkpoint_id


def test_attach_detach_context() -> None:
    haoe = MockHaoePort()
    orch = build_meta_orchestrator(haoe=haoe)
    ctx = simple_context()
    orch.attach_context(ctx)
    orch.detach_context("sw_test")
