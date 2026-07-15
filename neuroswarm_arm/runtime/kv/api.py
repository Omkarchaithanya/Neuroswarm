"""REST API for the KV Memory Runtime."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .benchmark.runner import run_named_benchmark
from .interfaces.types import StorageTier
from .manager.runtime import KVRuntimeManager


class SessionCreateRequest(BaseModel):
    session_id: str
    agent_id: str = ""


class ShareRequest(BaseModel):
    physical_id: str
    consumer_id: str
    session_id: str = ""
    token: str | None = None


class CheckpointRequest(BaseModel):
    session_id: str


class RestoreRequest(BaseModel):
    session_id: str
    resume: bool = False


class ProviderSelectRequest(BaseModel):
    name: str


class AllocateRequestModel(BaseModel):
    session_id: str
    payload_b64: str | None = None
    payload_text: str = Field(default="")
    layer: int = 0
    head: int = 0
    token_start: int = 0
    token_end: int = 0
    agent_id: str = ""
    prefix_hash: str = ""


class BenchmarkRequest(BaseModel):
    name: str = "latency"
    iterations: int = 50


def create_kv_router(runtime: KVRuntimeManager) -> APIRouter:
    router = APIRouter(prefix="/kv", tags=["kv-memory-runtime"])

    @router.get("/status")
    def kv_status() -> dict[str, Any]:
        return runtime.status()

    @router.get("/metrics")
    def kv_metrics() -> dict[str, float]:
        return runtime.metrics()

    @router.post("/session")
    def create_session(req: SessionCreateRequest) -> dict[str, Any]:
        session = runtime.create_session(req.session_id, agent_id=req.agent_id)
        return {"session_id": session.session_id, "agent_id": session.agent_id, "blocks": 0}

    @router.get("/session")
    def get_session(session_id: str) -> dict[str, Any]:
        session = runtime.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return session.to_dict()

    @router.post("/allocate")
    async def allocate(req: AllocateRequestModel) -> dict[str, Any]:
        import base64

        if req.payload_b64:
            payload = base64.b64decode(req.payload_b64)
        else:
            payload = req.payload_text.encode("utf-8")
        block = await runtime.allocate(
            req.session_id,
            payload,
            layer=req.layer,
            head=req.head,
            token_start=req.token_start,
            token_end=req.token_end,
            agent_id=req.agent_id,
            prefix_hash=req.prefix_hash,
        )
        return block.to_dict()

    @router.post("/share")
    async def share(req: ShareRequest) -> dict[str, Any]:
        try:
            token = await runtime.share(
                req.physical_id,
                req.consumer_id,
                session_id=req.session_id,
                token=req.token,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"share_token": token, "physical_id": req.physical_id}

    @router.post("/checkpoint")
    async def checkpoint(req: CheckpointRequest) -> dict[str, Any]:
        try:
            return await runtime.checkpoint(req.session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/restore")
    async def restore(req: RestoreRequest) -> dict[str, Any]:
        try:
            if req.resume:
                session = await runtime.resume(req.session_id)
            else:
                session = await runtime.restore(req.session_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return session.to_dict()

    @router.get("/provider")
    def list_providers() -> dict[str, Any]:
        return {"providers": runtime.providers.list_providers()}

    @router.post("/provider")
    def select_provider(req: ProviderSelectRequest) -> dict[str, Any]:
        try:
            provider = runtime.providers.get(req.name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if req.name in {"cxl", "mte"}:
            raise HTTPException(
                status_code=501,
                detail=f"{req.name} is a future backend stub and cannot be selected",
            )
        return {"name": provider.name, "tier": int(provider.tier)}

    @router.post("/benchmark")
    async def benchmark(req: BenchmarkRequest) -> dict[str, Any]:
        try:
            return await run_named_benchmark(runtime, req.name, iterations=req.iterations)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/pressure")
    def pressure() -> dict[str, Any]:
        return runtime.pressure_snapshot().to_dict()

    @router.post("/migrate")
    async def migrate(payload: dict[str, Any]) -> dict[str, Any]:
        physical_id = str(payload.get("physical_id", ""))
        tier = StorageTier(int(payload.get("target_tier", StorageTier.L2_COMPRESSED_RAM)))
        ok = await runtime.migrate(physical_id, tier)
        return {"ok": ok, "physical_id": physical_id, "target_tier": int(tier)}

    return router
