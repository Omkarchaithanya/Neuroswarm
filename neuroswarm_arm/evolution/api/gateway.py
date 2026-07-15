"""FastAPI /arop/* gateway."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from neuroswarm_arm.evolution.factory import AROPRuntime


class OptimizeBody(BaseModel):
    force: bool = True


class CanaryBody(BaseModel):
    policy_id: str
    percent: float = Field(default=10.0, ge=0.0, le=100.0)


def create_arop_router(runtime: AROPRuntime) -> APIRouter:
    router = APIRouter(prefix="/arop", tags=["arop"])

    @router.get("/health")
    def health() -> dict[str, Any]:
        return runtime.health()

    @router.get("/status")
    def status() -> dict[str, Any]:
        return runtime.status()

    @router.get("/policies")
    def policies() -> dict[str, Any]:
        return {
            "registry": runtime.registry.status(),
            "policies": [p.to_dict() for p in runtime.registry.list_policies()],
        }

    @router.post("/optimize")
    def optimize(body: OptimizeBody | None = None) -> dict[str, Any]:
        result = runtime.run_once()
        return {
            "status": result.status,
            "baseline_id": result.baseline_id,
            "candidate_id": result.candidate_id,
            "policy_id": result.policy_id,
            "message": result.message,
            "metrics": result.metrics,
            "details": result.details,
            "force": True if body is None else body.force,
        }

    @router.post("/rollback")
    def rollback() -> dict[str, Any]:
        rb = runtime.optimizer.deployment.rollback()
        return {
            "success": rb.success,
            "active_policy_id": rb.active_policy_id,
            "message": rb.message,
            "mode": rb.mode.value,
        }

    @router.get("/events")
    def events() -> dict[str, Any]:
        return {
            "events": [
                {"type": e.type.value, "at": e.at.isoformat(), "payload": dict(e.payload)}
                for e in runtime.bus.history(limit=50)
            ]
        }

    @router.get("/metrics")
    def metrics() -> dict[str, Any]:
        snap = runtime.aggregator.snapshot()
        return {
            "collected_at": snap.collected_at.isoformat(),
            "aggregate": dict(snap.aggregate),
            "providers": {k: dict(v) for k, v in snap.providers.items()},
        }

    return router
