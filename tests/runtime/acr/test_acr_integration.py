"""Integration-ish ACR tests with HAOE chat handler wiring (no live llama)."""

from __future__ import annotations

from types import SimpleNamespace

from neuroswarm_arm.runtime.acr import build_acr
from neuroswarm_arm.runtime.acr.config import ACRConfig
from neuroswarm_arm.runtime.haoe.integration.chat import build_chat_handlers
from neuroswarm_arm.runtime.haoe.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.haoe.interfaces.types import CorrelationIds


class _Router:
    def route(self, query, context=None):
        return []

    def route_result(self, query, context=None):
        return SimpleNamespace(
            tool_names=["github-mcp"],
            schemas=[],
            confidence_top1=0.9,
            to_dict=lambda: {},
        )

    def prompt_block(self, result):
        return "TOOLS: github-mcp"


class _Engine:
    def handle(self, req, tool_names=None, **kwargs):
        return SimpleNamespace(content="ok", latency_ms=10, cost_usd=0.0, error=None)


class _FakeMemory:
    def recall(self, owner, query, *, limit=5, namespace=None):
        return ["prefers Arm"]

    def remember_success(self, *a, **k):
        return None

    def remember_execution(self, *a, **k):
        return None

    def remember_failure(self, *a, **k):
        return None

    def remember_tool(self, *a, **k):
        return None

    def remember_workflow(self, *a, **k):
        return None

    def remember_latency(self, *a, **k):
        return None

    def remember_cost(self, *a, **k):
        return None

    def remember_evolution(self, *a, **k):
        return None

    def reflect(self, **k):
        return None


class _FakeOKF:
    def query(self, *a, **k):
        return SimpleNamespace(text="okf", tokens_used=3, sections=[])

    def load_tool_docs(self, *a, **k):
        return SimpleNamespace(text="docs")


def test_haoe_handlers_use_acr():
    acr = build_acr(memory=_FakeMemory(), okf=_FakeOKF(), config=ACRConfig(enabled=True, token_budget=500))
    req = SimpleNamespace(
        messages=[SimpleNamespace(content="Arm cascade policy")],
        agent_id="agent1",
        agent_role="architect",
        session_id="s1",
    )
    handlers = build_chat_handlers(
        semantic_router=_Router(),
        inference=_Engine(),
        kv_runtime=None,
        request=req,
        memory=_FakeMemory(),
        okf_runtime=_FakeOKF(),
        acr=acr,
    )
    ctx = ExecutionContext(ids=CorrelationIds(agent_id="agent1", workflow_id="chat", execution_id="e1"))
    handlers["mem0_recall"](ctx)
    handlers["okf_context"](ctx)
    handlers["semantic_route"](ctx)
    merged = handlers["okf_tool_docs"](ctx)
    assert merged
    assert ctx.baggage.get("acr_snapshot_version")
    assert "acr_compression_ratio" in ctx.baggage
