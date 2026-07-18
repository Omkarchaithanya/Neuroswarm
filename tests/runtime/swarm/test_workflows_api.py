"""Durable workflow resume — create → partial run → checkpoint → reload → resume."""

from __future__ import annotations

import asyncio
from pathlib import Path

from neuroswarm_arm.runtime.swarm.api import CreateWorkflowRequest, WorkflowService
from neuroswarm_arm.runtime.swarm.meta_orchestrator import WorkflowStatus


def test_workflow_checkpoint_resume_across_reload(tmp_path: Path) -> None:
    root = tmp_path / "swarm"

    async def _partial_then_checkpoint() -> str:
        svc = WorkflowService(root)
        created = svc.create(
            CreateWorkflowRequest(steps=["a", "b", "c"], name="resume_demo")
        )
        eid = created["execution_id"]
        # One reconcile step only — leave work unfinished.
        ex = svc.orch.get(eid)
        await svc.orch.step(ex)
        svc._persist(svc.orch.get(eid))
        ck = svc.checkpoint(eid)
        assert ck["checkpoint_id"]
        return eid

    eid = asyncio.run(_partial_then_checkpoint())

    async def _resume() -> dict:
        # Fresh service simulates process restart (reloads index + checkpoint store).
        svc2 = WorkflowService(root)
        assert eid in svc2.orch._executions
        return await svc2.resume(eid)

    out = asyncio.run(_resume())
    assert out["execution_id"] == eid
    assert out["status"] in {
        str(WorkflowStatus.COMPLETED),
        WorkflowStatus.COMPLETED.value,
        "completed",
        "WorkflowStatus.COMPLETED",
    }
    assert len(out["completed_nodes"]) >= 1


def test_workflow_create_injects_prior_experience(tmp_path: Path) -> None:
    svc = WorkflowService(tmp_path / "swarm2")

    async def _run_once() -> None:
        created = svc.create(CreateWorkflowRequest(steps=["x", "y"]))
        await svc.run(created["execution_id"])

    asyncio.run(_run_once())
    created2 = svc.create(CreateWorkflowRequest(steps=["p", "q"]))
    ex = svc.orch.get(created2["execution_id"])
    meta = getattr(ex.context, "metadata", {}) or {}
    if hasattr(meta, "get"):
        prior = meta.get("prior_experience") or []
    else:
        prior = []
    assert isinstance(prior, list)
    assert len(prior) >= 1
