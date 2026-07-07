from __future__ import annotations

from fastapi import FastAPI

from .config import get_config
from .evolution.performix_client import PerformixClient
from .gateway import AgentGateway
from .governor import ReasoningGovernor
from .inference.cascade import CascadeRouter
from .inference.llama_client import LlamaClient
from .metrics import metrics
from .schemas import ChatRequest, ToolDef
from .tools.registry import ToolRegistry
from .tools.semantic_mcp_router import SemanticMCPRouter


cfg = get_config()
registry = ToolRegistry()
semantic_router = SemanticMCPRouter(registry=registry)
semantic_router.index_tools()
cascade = CascadeRouter(
    tier1=LlamaClient(cfg.tier1_url),
    tier2=LlamaClient(cfg.tier2_url),
    tier3=LlamaClient(cfg.tier3_url),
    governor=ReasoningGovernor(),
)
gateway = AgentGateway(registry=registry, semantic_router=semantic_router, cascade=cascade)
performix = PerformixClient()

app = FastAPI(title="NeuroSwarm-Arm", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def export_metrics() -> str:
    return metrics.export_prometheus()


@app.post("/tools/register")
def register_tool(tool: dict) -> dict:
    registry.register(ToolDef(**tool))
    semantic_router.index_tools()
    return {"registered": tool.get("id")}


@app.post("/tools/route")
def route_tools(payload: dict) -> dict:
    query = payload.get("query", "")
    tools = semantic_router.route(query)
    return {"tools": [t.model_dump() if hasattr(t, "model_dump") else t.__dict__ for t in tools]}


@app.post("/v1/chat/completions")
def chat(req: ChatRequest) -> dict:
    response = gateway.handle_chat(req)
    return response.model_dump()


@app.post("/bench/run")
def bench_run(payload: dict) -> dict:
    recipe = payload.get("recipe", "system-characterization")
    result = performix.run_recipe(recipe, output=cfg.benchmarks_dir / f"{recipe}.json")
    return result


def serve() -> None:
    import uvicorn

    uvicorn.run(app, host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    serve()
