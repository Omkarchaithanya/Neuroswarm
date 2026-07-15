from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from nexus_okf.runtime.kernel import OKFRuntime, build_runtime
from nexus_okf.runtime.query import OKFQuery


class QueryRequest(BaseModel):
    text: str
    agent_profile: str = "architect"
    domains: list[str] | None = None
    token_budget: int = 1200
    expand_refs: int = 1


class ToolDocsRequest(BaseModel):
    tool_ids: list[str] = Field(default_factory=list)
    budget: int = 800


def create_app(artifact_dir: Path, source_root: Path | None = None) -> FastAPI:
    runtime = build_runtime(artifact_dir, source_root)
    app = FastAPI(title="OKF Knowledge OS", version="1.0.0")

    @app.get("/okf/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "docs": len(runtime.loader.document_index)}

    @app.post("/okf/query")
    def query(req: QueryRequest) -> dict[str, Any]:
        ctx = runtime.query(
            OKFQuery(
                text=req.text,
                agent_profile=req.agent_profile,
                domains=req.domains,
                token_budget=req.token_budget,
                expand_refs=req.expand_refs,
            )
        )
        return {
            "text": ctx.text,
            "tokens_used": ctx.tokens_used,
            "provenance": ctx.provenance,
            "metrics": ctx.metrics,
            "cache_hit": ctx.cache_hit,
        }

    @app.get("/okf/navigate")
    def navigate(path: str = "index.md", depth: int = 1) -> dict[str, Any]:
        node = runtime.navigate(path, depth=depth)
        return {
            "id": node.id,
            "title": node.title,
            "path": node.path,
            "children": node.children,
            "summary": node.summary,
        }

    @app.post("/okf/tool-docs")
    def tool_docs(req: ToolDocsRequest) -> dict[str, Any]:
        ctx = runtime.load_tool_docs(req.tool_ids, budget=req.budget)
        return {"text": ctx.text, "tokens_used": ctx.tokens_used, "provenance": ctx.provenance}

    @app.get("/okf/validate")
    def validate() -> dict[str, Any]:
        return runtime.validate_bundle()

    @app.get("/okf/stats")
    def stats() -> dict[str, Any]:
        return {
            "docs": len(runtime.loader.document_index),
            "metrics": runtime.metrics.snapshot(),
        }

    return app


def create_okf_router(runtime: OKFRuntime):
    """Mountable APIRouter for NEXUS main.py."""
    from fastapi import APIRouter

    router = APIRouter(prefix="/okf", tags=["okf"])

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "docs": len(runtime.loader.document_index)}

    @router.post("/query")
    def query(req: QueryRequest) -> dict[str, Any]:
        ctx = runtime.query(
            OKFQuery(
                text=req.text,
                agent_profile=req.agent_profile,
                domains=req.domains,
                token_budget=req.token_budget,
                expand_refs=req.expand_refs,
            )
        )
        return {
            "text": ctx.text,
            "tokens_used": ctx.tokens_used,
            "provenance": ctx.provenance,
            "metrics": ctx.metrics,
            "cache_hit": ctx.cache_hit,
        }

    @router.get("/validate")
    def validate() -> dict[str, Any]:
        return runtime.validate_bundle()

    @router.get("/stats")
    def stats() -> dict[str, Any]:
        return {"docs": len(runtime.loader.document_index), "metrics": runtime.metrics.snapshot()}

    return router
