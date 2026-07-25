"""FastAPI endpoints for Semantic MCP Tool Router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .models import RouteContext, ToolRecord
from .tool_router import SemanticToolRouter


class ToolBody(BaseModel):
    id: str
    name: str
    description: str = ""
    namespace: str = "default"
    version: str = "1.0.0"
    category: str = "general"
    capabilities: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    rate_limits: dict[str, float] = Field(default_factory=dict)
    cost_usd: float = 0.0
    p50_latency_ms: float = 50.0
    tags: list[str] = Field(default_factory=list)
    params: dict[str, str] = Field(default_factory=dict)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    example_prompts: list[str] = Field(default_factory=list)
    endpoint: str | None = None
    auth: str | None = None
    agent_roles: list[str] = Field(default_factory=list)
    workflow_stages: list[str] = Field(default_factory=list)


class RouteBody(BaseModel):
    query: str
    top_k: int | None = None
    agent_id: str = "default"
    agent_role: str = "tool_call"
    workflow_stage: str = "execute"
    conversation_excerpt: str = ""
    previous_tools: list[str] = Field(default_factory=list)
    task_type: str = "general"
    budget_remaining_usd: float = 1.0
    latency_slo_ms: float = 4000.0
    security_policies: list[str] = Field(default_factory=list)
    memory_pressure: float = 0.0
    quantization: str = ""
    inference_tier: int = 1
    required_capabilities: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)
    expected_output_format: str = ""


class SnapshotBody(BaseModel):
    name: str | None = None


class RestoreBody(BaseModel):
    name: str


class BenchmarkBody(BaseModel):
    cases: list[dict[str, Any]] | None = None


class CallToolBody(BaseModel):
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    timeout_s: float = 30.0


def _context_from_body(body: RouteBody) -> RouteContext:
    return RouteContext(
        agent_id=body.agent_id,
        agent_role=body.agent_role,
        workflow_stage=body.workflow_stage,
        conversation_excerpt=body.conversation_excerpt or body.query,
        previous_tools=body.previous_tools,
        task_type=body.task_type,
        budget_remaining_usd=body.budget_remaining_usd,
        latency_slo_ms=body.latency_slo_ms,
        security_policies=body.security_policies,
        memory_pressure=body.memory_pressure,
        quantization=body.quantization,
        inference_tier=body.inference_tier,
        required_capabilities=body.required_capabilities,
        required_permissions=body.required_permissions,
        expected_output_format=body.expected_output_format,
    )


def create_tool_router(runtime: SemanticToolRouter) -> APIRouter:
    tools_router = APIRouter(tags=["tools"])
    router_meta = APIRouter(prefix="/router", tags=["router"])

    @tools_router.post("/tools/register")
    def register_tool(body: ToolBody) -> dict[str, Any]:
        tool = runtime.register_tool(ToolRecord.from_dict(body.model_dump()))
        return {"status": "ok", "tool": tool.to_dict(), "indexed": runtime.index.size()}

    @tools_router.post("/tools/update")
    def update_tool(body: ToolBody) -> dict[str, Any]:
        try:
            tool = runtime.update_tool(body.id, **{k: v for k, v in body.model_dump().items() if k != "id"})
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "ok", "tool": tool.to_dict()}

    @tools_router.delete("/tools/remove")
    def remove_tool(tool_id: str) -> dict[str, Any]:
        try:
            tool = runtime.remove_tool(tool_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "ok", "removed": tool.to_dict()}

    @tools_router.post("/tools/search")
    def search_tools(body: RouteBody) -> dict[str, Any]:
        result = runtime.route(body.query, context=_context_from_body(body), top_k=body.top_k)
        return result.to_dict()

    @tools_router.post("/tools/route")
    def route_tools(body: RouteBody) -> dict[str, Any]:
        result = runtime.route(body.query, context=_context_from_body(body), top_k=body.top_k)
        payload = result.to_dict()
        payload["prompt_block"] = runtime.prompt_block(result)
        return payload

    @tools_router.post("/tools/call")
    def call_tool(body: CallToolBody) -> dict[str, Any]:
        """Optional demo execute path (NSA_MCP_EXECUTE=1). Not used by default chat."""
        from .mcp_executor import call_tool as mcp_call, mcp_execute_enabled

        if not mcp_execute_enabled():
            raise HTTPException(
                status_code=503,
                detail="MCP execute disabled. Set NSA_MCP_EXECUTE=1 and provide API keys.",
            )
        out = mcp_call(body.tool_id, body.arguments, timeout_s=body.timeout_s)
        if not out.get("ok"):
            raise HTTPException(status_code=400, detail=out)
        return out

    @tools_router.post("/tools/reload")
    def reload_tools() -> dict[str, Any]:
        return {"status": "ok", **runtime.reload()}

    @tools_router.get("/tools")
    def list_tools() -> dict[str, Any]:
        tools = [t.to_dict() for t in runtime.list_tools()]
        return {"count": len(tools), "tools": tools}

    @tools_router.get("/tools/{tool_id}")
    def get_tool(tool_id: str) -> dict[str, Any]:
        try:
            return runtime.get_tool(tool_id).to_dict()
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router_meta.get("/metrics")
    def router_metrics() -> dict[str, float]:
        return runtime.metrics_snapshot()

    @router_meta.get("/health")
    def router_health() -> dict[str, Any]:
        return runtime.health()

    @router_meta.post("/benchmark")
    def router_benchmark(body: BenchmarkBody | None = None) -> dict[str, Any]:
        cases = body.cases if body else None
        return runtime.benchmark(cases)

    @router_meta.post("/snapshot")
    def router_snapshot(body: SnapshotBody | None = None) -> dict[str, Any]:
        name = body.name if body else None
        path = runtime.snapshot(name)
        return {"status": "ok", "path": path}

    @router_meta.post("/restore")
    def router_restore(body: RestoreBody) -> dict[str, Any]:
        return {"status": "ok", **runtime.restore(body.name)}

    # Combine into one router
    root = APIRouter()
    root.include_router(tools_router)
    root.include_router(router_meta)
    return root
