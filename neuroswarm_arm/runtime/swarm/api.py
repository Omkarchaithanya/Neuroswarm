"""HTTP API for durable long-horizon workflows (Meta Orchestrator + checkpoint)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from neuroswarm_arm.runtime.swarm.checkpoint import build_checkpoint_manager
from neuroswarm_arm.runtime.swarm.context import SwarmContextBuilder
from neuroswarm_arm.runtime.swarm.experience import build_experience_store
from neuroswarm_arm.runtime.swarm.experience.execution_record import ExecutionRecord
from neuroswarm_arm.runtime.swarm.haoe_adapter import InstantHaoeAdapter, StaticAgentCatalog
from neuroswarm_arm.runtime.swarm.meta_orchestrator import (
    MetaOrchestrator,
    WorkflowStatus,
    build_meta_orchestrator,
    dumps as dump_execution,
    loads as load_execution,
)
from neuroswarm_arm.runtime.swarm.task_graph.planner import WorkflowPlanner


class CreateWorkflowRequest(BaseModel):
    steps: list[str] = Field(
        default_factory=lambda: ["plan", "gather", "act", "review", "finalize"]
    )
    name: str = "long_horizon"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    agents: list[str] = Field(default_factory=lambda: ["workflow-agent"])


class WorkflowService:
    """Composition-root facade: create / run / checkpoint / resume / experience."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "index").mkdir(parents=True, exist_ok=True)
        self.experience = build_experience_store(root=self.root / "experience")
        self.checkpoints = build_checkpoint_manager(
            path=self.root / "checkpoints",
            experience_store=self.experience,
        )
        self.haoe = InstantHaoeAdapter()
        self.catalog = StaticAgentCatalog()
        self.orch: MetaOrchestrator = build_meta_orchestrator(
            haoe=self.haoe,
            catalog=self.catalog,
            checkpoint_manager=self.checkpoints,
            experience_store=self.experience,
        )
        self.planner = WorkflowPlanner()
        self._reload_index()

    def _index_path(self, execution_id: str) -> Path:
        return self.root / "index" / f"{execution_id}.json"

    def _persist(self, execution: Any) -> None:
        path = self._index_path(execution.execution_id)
        path.write_text(dump_execution(execution), encoding="utf-8")
        self.orch._executions[execution.execution_id] = execution

    def _reload_index(self) -> None:
        for path in sorted((self.root / "index").glob("*.json")):
            try:
                ex = load_execution(path.read_text(encoding="utf-8"))
                self.orch._executions[ex.execution_id] = ex
            except Exception:
                continue

    def _prior_experience(self, limit: int = 5) -> list[dict[str, Any]]:
        try:
            records = list(self.experience.query.filter(None))
        except Exception:
            records = []
        out: list[dict[str, Any]] = []
        for rec in records[-limit:]:
            try:
                out.append(
                    {
                        "execution_id": getattr(rec, "execution_id", None),
                        "workflow_id": getattr(rec, "workflow_id", None),
                        "success": getattr(rec, "success", None),
                        "tags": list(getattr(rec, "tags", []) or []),
                    }
                )
            except Exception:
                continue
        return out

    def create(self, req: CreateWorkflowRequest) -> dict[str, Any]:
        graph = self.planner.plan_from_steps(req.steps, name=req.name)
        prior = self._prior_experience()
        meta = dict(req.metadata)
        meta["prior_experience"] = prior
        ctx = (
            SwarmContextBuilder()
            .tags(*(req.tags or ["long_horizon"]))
            .metadata(**meta)
            .execution_plan({"steps": list(req.steps), "name": req.name})
            .build()
        )
        ex = self.orch.create(
            graph=graph,
            context=ctx,
            agents=req.agents,
            metadata={"template": req.name, "steps": list(req.steps)},
        )
        self._persist(ex)
        return self._public(ex)

    async def run(self, execution_id: str) -> dict[str, Any]:
        ex = self._get(execution_id)
        ex = await self.orch.start(ex)
        self._persist(ex)
        self._record_experience(ex)
        return self._public(ex)

    def get(self, execution_id: str) -> dict[str, Any]:
        return self._public(self._get(execution_id))

    def checkpoint(self, execution_id: str) -> dict[str, Any]:
        ex = self._get(execution_id)
        handle = self.orch.checkpoint(ex)
        self._persist(ex)
        return {
            "checkpoint_id": getattr(handle, "checkpoint_id", None),
            "execution_id": execution_id,
            "completed_nodes": list(getattr(handle, "completed_nodes", []) or []),
            "status": str(ex.status),
        }

    async def resume(self, execution_id: str, checkpoint_id: str | None = None) -> dict[str, Any]:
        ex = self._get(execution_id)
        ckpt = checkpoint_id or ex.checkpoint_reference
        if not ckpt:
            raise HTTPException(status_code=400, detail="no checkpoint_id; call /checkpoint first")
        restored = self.orch.restore(ex, ckpt)
        self._persist(restored)
        restored = await self.orch.start(restored)
        self._persist(restored)
        self._record_experience(restored)
        return self._public(restored)

    def cancel(self, execution_id: str, *, forced: bool = False) -> dict[str, Any]:
        ex = self.orch.cancel(execution_id, forced=forced)
        self._persist(ex)
        return self._public(ex)

    def list_experience(self, limit: int = 20) -> dict[str, Any]:
        return {"items": self._prior_experience(limit=limit), "limit": limit}

    def _get(self, execution_id: str) -> Any:
        try:
            return self.orch.get(execution_id)
        except Exception:
            path = self._index_path(execution_id)
            if path.exists():
                ex = load_execution(path.read_text(encoding="utf-8"))
                self.orch._executions[ex.execution_id] = ex
                return ex
            raise HTTPException(status_code=404, detail=f"workflow not found: {execution_id}")

    def _record_experience(self, ex: Any) -> None:
        try:
            success = ex.status == WorkflowStatus.COMPLETED
            rec = ExecutionRecord(
                execution_id=ex.execution_id,
                workflow_id=ex.workflow_id,
                success=success,
                tags=["workflow", "long_horizon"],
                metadata={
                    "status": str(ex.status),
                    "completed_nodes": list(ex.completed_nodes),
                    "failed_nodes": list(ex.failed_nodes),
                },
            )
            self.experience.record(rec)
        except Exception:
            pass

    @staticmethod
    def _public(ex: Any) -> dict[str, Any]:
        return {
            "execution_id": ex.execution_id,
            "workflow_id": ex.workflow_id,
            "status": str(ex.status),
            "completed_nodes": list(ex.completed_nodes),
            "failed_nodes": list(ex.failed_nodes),
            "skipped_nodes": list(ex.skipped_nodes),
            "checkpoint_reference": ex.checkpoint_reference,
            "graph_id": getattr(ex, "graph_id", None),
        }


def create_workflow_router(service: WorkflowService) -> APIRouter:
    router = APIRouter(prefix="/workflows", tags=["workflows"])

    @router.post("")
    def create_workflow(req: CreateWorkflowRequest) -> dict[str, Any]:
        return service.create(req)

    @router.post("/{execution_id}/run")
    async def run_workflow(execution_id: str) -> dict[str, Any]:
        return await service.run(execution_id)

    @router.get("/{execution_id}")
    def get_workflow(execution_id: str) -> dict[str, Any]:
        return service.get(execution_id)

    @router.post("/{execution_id}/checkpoint")
    def checkpoint_workflow(execution_id: str) -> dict[str, Any]:
        return service.checkpoint(execution_id)

    @router.post("/{execution_id}/resume")
    async def resume_workflow(execution_id: str, checkpoint_id: str | None = None) -> dict[str, Any]:
        return await service.resume(execution_id, checkpoint_id)

    @router.post("/{execution_id}/cancel")
    def cancel_workflow(execution_id: str, forced: bool = False) -> dict[str, Any]:
        return service.cancel(execution_id, forced=forced)

    return router


def create_experience_router(service: WorkflowService) -> APIRouter:
    router = APIRouter(prefix="/experience", tags=["experience"])

    @router.get("")
    def list_experience(limit: int = 20) -> dict[str, Any]:
        return service.list_experience(limit=limit)

    return router
