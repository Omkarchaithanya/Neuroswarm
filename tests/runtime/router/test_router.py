"""Router unit and integration tests."""

from __future__ import annotations

from pathlib import Path
import concurrent.futures
import shutil
import uuid

import numpy as np
import pytest

from neuroswarm_arm.runtime.memory import build_memory_runtime
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.router import build_router, load_router_config
from neuroswarm_arm.runtime.router.models import RouteContext, ToolRecord, ScoredTool
from neuroswarm_arm.runtime.router.similarity import l2_normalize, keyword_overlap
from neuroswarm_arm.runtime.router.confidence import estimate_confidence
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest
from neuroswarm_arm.runtime.dipa.execution.execution_pipeline import ExecutionPipeline


REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "templates" / "mcp-servers"
WORK = REPO / "work" / "test_router"


def _scratch() -> Path:
    path = WORK / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def router(monkeypatch):
    monkeypatch.setenv("NSA_ROUTER_ALLOW_HASH", "1")
    monkeypatch.setenv("NSA_ROUTER_EMBEDDING_BACKEND", "hash")
    scratch = _scratch()
    cfg = load_router_config(REPO)
    cfg.tool_metadata_root = TOOLS
    cfg.okf_root = scratch / "okf"
    cfg.embedding_backend = "hash"
    cfg.allow_hash = True
    cfg.okf_root.mkdir()
    cfg.index_path = scratch / "index"
    cfg.snapshot_dir = scratch / "snapshots"
    cfg.cache_dir = scratch / "cache"
    cfg.mem_store = scratch / "mem"
    cfg.enable_hot_reload = False
    cfg.ann_backend = "exact"
    cfg.allow_hash = True
    cfg.ensure_dirs()
    offline_mem = build_memory_runtime(
        config=MemoryRuntimeConfig(
            store_root=scratch / "mem",
            provider="json",
            llm_mode="none",
        )
    )
    rt = build_router(cfg, start_sync=False, memory=offline_mem)
    yield rt
    rt.shutdown()
    shutil.rmtree(scratch, ignore_errors=True)


def test_registry_load_and_route(router):
    assert router.registry.size() >= 40
    result = router.route("Upload an artifact to object storage")
    assert result.tools
    assert result.confidence_top1 >= 0.0
    ids = result.tool_ids
    assert "s3" in ids or any("s3" in x for x in ids)


def test_hybrid_and_schemas(router):
    result = router.route("Use slack to send a channel update about the release")
    assert result.schemas
    block = router.prompt_block(result)
    assert "Available tools" in block
    assert result.prompt_tokens_after <= result.prompt_tokens_before


def test_register_update_remove(router):
    tool = ToolRecord(
        id="custom-echo",
        name="echo",
        description="Echo text back for debugging agent loops",
        params={"text": "string"},
        tags=["debug"],
        example_prompts=["echo hello"],
    )
    router.register_tool(tool)
    assert router.get_tool("custom-echo").name == "echo"
    router.update_tool("custom-echo", description="Echo helper tool for tests")
    router.remove_tool("custom-echo")
    with pytest.raises(Exception):
        router.get_tool("custom-echo")


def test_snapshot_restore(router):
    path = router.snapshot("testsnap")
    assert Path(path).exists()
    router.registry.clear()
    router.index.clear()
    assert router.registry.size() == 0
    restored = router.restore(path)
    assert restored["tools"] >= 40
    assert router.index.size() >= 40


def test_hot_reload_scan(router):
    scratch = _scratch()
    root = scratch / "mcp"
    root.mkdir()
    meta = root / "okf-metadata.yaml"
    meta.write_text(
        "id: custom-search\nname: custom-search\ndescription: Custom web search tool\nparams:\n  q: query\n",
        encoding="utf-8",
    )
    router.config.tool_metadata_root = root
    assert router.sync is not None
    router.sync.roots = [root]
    stats = router.sync.scan()
    assert stats["loaded"] >= 1 or router.registry.get_optional("custom-search") is not None
    shutil.rmtree(scratch, ignore_errors=True)


def test_concurrency_batch_route(router):
    queries = [
        "github issues",
        "browser page text",
        "postgres query",
        "slack message",
        "s3 upload",
        "web search",
    ] * 4

    def _one(q: str):
        return router.route(q).tool_ids

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_one, queries))
    assert len(results) == len(queries)
    assert all(isinstance(r, list) for r in results)


def test_embedding_normalize_and_cache(router):
    v1 = router.embedder.encode("hello router")
    v2 = router.embedder.encode("hello router")
    assert v1.shape == v2.shape
    np.testing.assert_allclose(v1, v2, rtol=1e-5)
    assert abs(float(np.linalg.norm(l2_normalize(v1))) - 1.0) < 1e-5


def test_keyword_overlap():
    assert keyword_overlap("github issues", "GitHub API tools for issues") > 0


def test_confidence():
    tools = [
        ScoredTool(tool=ToolRecord(id="a", name="a"), score=0.9),
        ScoredTool(tool=ToolRecord(id="b", name="b"), score=0.2),
    ]
    conf = estimate_confidence(tools)
    assert 0.0 <= conf <= 1.0


def test_dipa_schema_injection():
    class Pipe:
        pass

    pipe = Pipe()
    req = InferenceRequest(
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=[{"type": "function", "function": {"name": "github"}}],
        tool_prompt_block="",
    )
    msgs = ExecutionPipeline._messages(pipe, req)  # type: ignore[arg-type]
    assert msgs[0]["role"] == "system"
    assert "github" in msgs[0]["content"]


def test_benchmark_runner(router):
    report = router.benchmark()
    assert report["status"] == "ok"
    assert "top3_accuracy" in report
    assert "latency_ms" in report


def test_fault_exact_backend(monkeypatch):
    monkeypatch.setenv("NSA_ROUTER_ALLOW_HASH", "1")
    scratch = _scratch()
    cfg = load_router_config(REPO)
    cfg.tool_metadata_root = TOOLS
    cfg.ann_backend = "exact"
    cfg.enable_hot_reload = False
    cfg.allow_hash = True
    cfg.snapshot_dir = scratch / "snap"
    cfg.index_path = scratch / "idx"
    cfg.cache_dir = scratch / "cache"
    cfg.mem_store = scratch / "mem"
    cfg.ensure_dirs()
    offline_mem = build_memory_runtime(
        config=MemoryRuntimeConfig(
            store_root=scratch / "mem",
            provider="json",
            llm_mode="none",
        )
    )
    r = build_router(cfg, start_sync=False, memory=offline_mem)
    assert r.index.size() >= 0
    out = r.route("slack channel update")
    assert out.tools
    r.shutdown()
    shutil.rmtree(scratch, ignore_errors=True)


def test_route_context_filters(router):
    ctx = RouteContext(
        agent_role="tool_call",
        workflow_stage="execute",
        security_policies=["deny:nonexistent"],
        conversation_excerpt="postgres sql rows",
    )
    result = router.route("Store structured data in postgres and query rows", context=ctx)
    assert result.tools
