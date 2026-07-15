"""Optional FastAPI router for MAKS Layer 5."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .manager import KVManager
from .models import KVIdentity, PrefetchRequest, ProviderName


class CreateBody(BaseModel):
    payload_b64: str = ""
    payload_text: str = ""
    agent_id: str = ""
    session_id: str = ""
    model_id: str = ""
    quantization: str = ""
    prompt_hash: str = ""


class ShareBody(BaseModel):
    kv_id: str
    consumer_id: str


class MigrateBody(BaseModel):
    kv_id: str
    target: str = "mmap"
    reason: str = "api"


def create_maks_router(manager: KVManager) -> APIRouter:
    router = APIRouter(prefix="/maks", tags=["maks"])

    @router.get("/status")
    async def status() -> dict[str, Any]:
        await manager.refresh_tier_gauges()
        return {
            "pressure": manager.pressure_snapshot(),
            "metrics": manager.metrics.snapshot(),
            "providers": list(manager.providers.keys()),
            "pool": manager.pool.stats(),
            "capabilities": manager.capability_matrix(),
        }

    @router.get("/capabilities")
    async def capabilities() -> dict[str, Any]:
        return manager.capability_matrix()

    @router.post("/create")
    async def create(body: CreateBody) -> dict[str, Any]:
        import base64

        if body.payload_b64:
            payload = base64.b64decode(body.payload_b64)
        else:
            payload = body.payload_text.encode("utf-8")
        handle = await manager.create(
            payload,
            agent_id=body.agent_id,
            session_id=body.session_id,
            identity=KVIdentity(model_id=body.model_id, quantization=body.quantization),
            prompt_hash=body.prompt_hash,
        )
        return handle.model_dump()

    @router.post("/share")
    async def share(body: ShareBody) -> dict[str, str]:
        token = await manager.share(body.kv_id, body.consumer_id)
        return {"token": token}

    @router.post("/migrate")
    async def migrate(body: MigrateBody) -> dict[str, str]:
        try:
            loc = await manager.migrate(body.kv_id, body.target, reason=body.reason)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"location": loc}

    @router.get("/lookup/{kv_id}")
    async def lookup(kv_id: str) -> dict[str, Any]:
        handle = await manager.lookup(kv_id=kv_id)
        if handle is None:
            raise HTTPException(status_code=404, detail="not found")
        return handle.model_dump()

    @router.post("/prefetch")
    async def prefetch(req: PrefetchRequest) -> dict[str, Any]:
        handle = await manager.prefetch(req)
        return handle.model_dump() if handle else {"kv_id": None}

    return router
