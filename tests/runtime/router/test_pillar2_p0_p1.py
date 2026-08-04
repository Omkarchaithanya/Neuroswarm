"""Pillar 2 P0/P1 audit regression tests."""

from __future__ import annotations

from pathlib import Path
import shutil
import uuid

import pytest

from neuroswarm_arm.runtime.dipa.execution.execution_pipeline import ExecutionPipeline
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest
from neuroswarm_arm.runtime.memory import build_memory_runtime
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.router import build_router, load_router_config
from neuroswarm_arm.runtime.router.backends.registry import build_vector_index, kernel_path_for
from neuroswarm_arm.runtime.router.embedding_service import EmbeddingService
from neuroswarm_arm.runtime.router.health import build_health_report
from neuroswarm_arm.runtime.router.models import EmbeddingSpec, MetricKind, RoutingResult, ToolRecord
from neuroswarm_arm.runtime.router.router_exceptions import EmbeddingError
from neuroswarm_arm.runtime.router.tool_serializer import serialize_tools_for_prompt
from neuroswarm_arm.runtime.router.turbovec_index import TurboVecIndex

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "templates" / "mcp-servers"
WORK = REPO / "work" / "test_router_p0"


def _scratch() -> Path:
    path = WORK / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(autouse=True)
def _allow_hash_env(monkeypatch):
    monkeypatch.setenv("NSA_ROUTER_ALLOW_HASH", "1")
    monkeypatch.setenv("NSA_ROUTER_EMBEDDING_BACKEND", "hash")


def test_missing_embedder_raises_loud(monkeypatch):
    monkeypatch.delenv("NSA_ROUTER_ALLOW_HASH", raising=False)
    monkeypatch.setenv("NSA_ROUTER_ALLOW_HASH", "0")
    monkeypatch.setenv("NSA_ROUTER_EMBEDDING_BACKEND", "fastembed")

    def _no_fe(self):
        return False

    def _no_st(self):
        return False

    monkeypatch.setattr(EmbeddingService, "_try_fastembed", _no_fe)
    monkeypatch.setattr(EmbeddingService, "_try_sentence_transformers", _no_st)
    with pytest.raises(EmbeddingError, match="NSA_ROUTER_ALLOW_HASH|fastembed"):
        EmbeddingService(EmbeddingSpec(model_name="nomic-embed-text-v1.5", backend="fastembed"), allow_hash=False)


def test_fastembed_backend_name(monkeypatch):
    class _FakeFE:
        def embed(self, texts):
            import numpy as np

            for _ in texts:
                yield np.ones(384, dtype=np.float32)

    def _ok(self):
        from neuroswarm_arm.runtime.router.embedding_service import _FastEmbedAdapter

        self._model = _FastEmbedAdapter(_FakeFE(), dims=384)
        self._dims = 384
        self._backend = "fastembed"
        return True

    monkeypatch.setenv("NSA_ROUTER_EMBEDDING_BACKEND", "fastembed")
    monkeypatch.setattr(EmbeddingService, "_try_fastembed", _ok)
    svc = EmbeddingService(EmbeddingSpec(backend="fastembed"), allow_hash=False)
    assert svc.backend_name == "fastembed"
    assert svc.dims == 384
    vec = svc.encode("hello world")
    assert vec.shape == (384,)


def test_turbovec_min_tools_uses_exact_below_threshold():
    tv = TurboVecIndex(8, metric=MetricKind.COSINE, min_tools_for_turbovec=100)
    import numpy as np

    for i in range(5):
        tv.insert(f"k{i}", np.ones(8, dtype=np.float32))
    assert tv.size() == 5
    assert tv.kernel_path == "numpy"
    assert tv._using_turbovec is False


def test_catalog_has_at_least_40_tools():
    from neuroswarm_arm.runtime.router.registry_loader import RegistryLoader

    tools = RegistryLoader().load_path(TOOLS)
    assert len(tools) >= 40
    ids = {t.id for t in tools}
    assert "github.list_issues" in ids
    assert "s3.put_object" in ids
    assert "web.search" in ids


def test_mcp_execute_disabled_by_default(monkeypatch):
    monkeypatch.delenv("NSA_MCP_EXECUTE", raising=False)
    from neuroswarm_arm.runtime.router.mcp_executor import call_tool_sync, mcp_execute_enabled

    assert mcp_execute_enabled() is False
    out = call_tool_sync("github.list_issues", {"repo": "a/b"})
    assert out["ok"] is False
    assert "NSA_MCP_EXECUTE" in out["error"]


def test_onnx_without_tokenizer_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("NSA_ROUTER_ALLOW_HASH", "0")
    # Minimal fake onnx path — session load may fail first; force tokenizer failure path.
    bogus = tmp_path / "model.onnx"
    bogus.write_bytes(b"not-a-real-onnx")

    def _fail_tok(self):
        raise EmbeddingError("Failed to load ONNX tokenizer from 'x'")

    monkeypatch.setattr(EmbeddingService, "_load_tokenizer", _fail_tok)

    # If ort cannot parse the file, we still get EmbeddingError (not silent hash).
    with pytest.raises(EmbeddingError):
        EmbeddingService(
            EmbeddingSpec(
                model_name="nomic-embed-text-v1.5",
                use_onnx=True,
                onnx_path=str(bogus),
            ),
            allow_hash=False,
        )


def test_factory_dims_consistency():
    scratch = _scratch()
    cfg = load_router_config(REPO)
    cfg.tool_metadata_root = TOOLS
    cfg.okf_root = scratch / "okf"
    cfg.okf_root.mkdir()
    cfg.index_path = scratch / "index"
    cfg.snapshot_dir = scratch / "snap"
    cfg.cache_dir = scratch / "cache"
    cfg.mem_store = scratch / "mem"
    cfg.enable_hot_reload = False
    cfg.ann_backend = "exact"
    cfg.allow_hash = True
    cfg.embedding_backend = "hash"
    cfg.ensure_dirs()
    mem = build_memory_runtime(
        config=MemoryRuntimeConfig(store_root=scratch / "mem", provider="json", llm_mode="none")
    )
    rt = build_router(cfg, start_sync=False, memory=mem)
    assert rt.embedder.dims == rt.index.dims
    rt.shutdown()
    shutil.rmtree(scratch, ignore_errors=True)


def test_turbovec_health_reports_real_backend():
    # Explicit exact backend → ok + numpy
    exact = build_vector_index("exact", 8)
    assert kernel_path_for(exact) == "numpy"

    class _Rt:
        config = type("C", (), {"ann_backend": "exact", "encoder_name": "x", "top_k": 3, "threshold": 0.42, "enable_hot_reload": False, "snapshot_dir": ".", "high_conf_gate": 0.85})()
        index = exact
        embedder = type("E", (), {"backend_name": "hash", "dims": 8, "cache": None})()
        registry = type("R", (), {"size": lambda self: 0})()
        arm_features = type("A", (), {"arch": "x", "is_arm64": False, "neon": False, "sve": False, "sve2": False, "numa_nodes": 1})()

    report_exact = build_health_report(_Rt())
    assert report_exact["status"] == "ok"
    assert report_exact["kernel_path"] == "numpy"

    # turbovec requested: numpy is OK when below min_tools with import success,
    # degraded only when turbovec import failed.
    tv = TurboVecIndex(8, metric=MetricKind.COSINE, min_tools_for_turbovec=100)
    _Rt.config = type(
        "C",
        (),
        {
            "ann_backend": "turbovec",
            "encoder_name": "x",
            "top_k": 3,
            "threshold": 0.42,
            "enable_hot_reload": False,
            "snapshot_dir": ".",
            "high_conf_gate": 0.85,
            "turbovec_min_tools": 100,
            "embedding_backend": "hash",
        },
    )()
    _Rt.index = tv
    report_tv = build_health_report(_Rt())
    if getattr(tv, "_turbovec_import_ok", False) and tv.kernel_path == "numpy":
        assert report_tv["status"] == "ok"
    elif tv.kernel_path == "numpy":
        assert report_tv["status"] == "degraded"
    else:
        assert report_tv["status"] == "ok"
        assert report_tv["kernel_path"] == "turbovec"


def test_high_confidence_flag():
    scratch = _scratch()
    cfg = load_router_config(REPO)
    cfg.tool_metadata_root = TOOLS
    cfg.okf_root = scratch / "okf"
    cfg.okf_root.mkdir()
    cfg.index_path = scratch / "index"
    cfg.snapshot_dir = scratch / "snap"
    cfg.cache_dir = scratch / "cache"
    cfg.mem_store = scratch / "mem"
    cfg.enable_hot_reload = False
    cfg.ann_backend = "exact"
    cfg.allow_hash = True
    cfg.embedding_backend = "hash"
    cfg.high_conf_gate = 0.01  # force true on any positive confidence
    cfg.ensure_dirs()
    mem = build_memory_runtime(
        config=MemoryRuntimeConfig(store_root=scratch / "mem", provider="json", llm_mode="none")
    )
    rt = build_router(cfg, start_sync=False, memory=mem)
    result = rt.route("Upload an artifact to object storage")
    assert isinstance(result, RoutingResult)
    assert result.high_confidence is True
    assert "high_confidence" in result.to_dict()
    rt.shutdown()
    shutil.rmtree(scratch, ignore_errors=True)


def test_high_conf_thinking_cap_wiring():
    req = InferenceRequest(
        messages=[{"role": "user", "content": "hi"}],
        tool_confidence=0.95,
        tool_high_confidence=True,
        thinking_token_cap=2048,
        max_tokens=4096,
        baggage={"high_conf_thinking_budget": 256},
    )
    ExecutionPipeline.apply_high_confidence_thinking_cap(req)
    assert req.thinking_token_cap == 256
    assert req.max_tokens == 256

    low = InferenceRequest(
        messages=[{"role": "user", "content": "hi"}],
        tool_high_confidence=False,
        thinking_token_cap=2048,
        max_tokens=4096,
    )
    ExecutionPipeline.apply_high_confidence_thinking_cap(low)
    assert low.thinking_token_cap == 2048
    assert low.max_tokens == 4096


def test_threshold_rerank_expansion_cap():
    scratch = _scratch()
    cfg = load_router_config(REPO)
    cfg.tool_metadata_root = TOOLS
    cfg.okf_root = scratch / "okf"
    cfg.okf_root.mkdir()
    cfg.index_path = scratch / "index"
    cfg.snapshot_dir = scratch / "snap"
    cfg.cache_dir = scratch / "cache"
    cfg.mem_store = scratch / "mem"
    cfg.enable_hot_reload = False
    cfg.ann_backend = "exact"
    cfg.allow_hash = True
    cfg.embedding_backend = "hash"
    cfg.threshold = 0.99  # force expand path
    cfg.top_k = 3
    cfg.candidate_multiplier = 2  # candidate_k = 6
    cfg.ensure_dirs()
    mem = build_memory_runtime(
        config=MemoryRuntimeConfig(store_root=scratch / "mem", provider="json", llm_mode="none")
    )
    rt = build_router(cfg, start_sync=False, memory=mem)
    # Pad registry so uncapped expand would exceed candidate_k.
    for i in range(20):
        rt.register_tool(
            ToolRecord(
                id=f"pad-{i}",
                name=f"pad-{i}",
                description=f"padding tool {i}",
                params={"x": "string"},
            )
        )
    result = rt.route("zzzz unlikely query that forces low semantic scores")
    candidate_k = min(rt.registry.size(), max(cfg.top_k * cfg.candidate_multiplier, cfg.top_k))
    assert result.candidate_count <= candidate_k
    rt.shutdown()
    shutil.rmtree(scratch, ignore_errors=True)


def test_serialize_max_tokens_drops_output_schema():
    tool = ToolRecord(
        id="fat",
        name="fat",
        description="Fat schema tool",
        params={"a": "string"},
        output_schema={"type": "object", "properties": {"x": {"type": "string"}}},
    )
    from neuroswarm_arm.runtime.router.models import ScoredTool
    from neuroswarm_arm.runtime.router.tool_schema_builder import build_tool_schema

    scored = ScoredTool(tool=tool, score=1.0, schema=build_tool_schema(tool))
    block = serialize_tools_for_prompt([scored], max_tokens=80)
    assert "output_schema" not in block


def test_mcpga_40_tool_smoke(monkeypatch):
    monkeypatch.setenv("NSA_ROUTER_ALLOW_HASH", "1")
    monkeypatch.setenv("NSA_ROUTER_MCPGA_HASH", "1")
    from benchmarks.router_mcpga import run_mcpga

    report = run_mcpga(top_k=3)
    assert report["tool_count"] >= 40
    assert report["top3_hit_rate"] >= 0.5  # hash embedder is weak; floor for CI
    assert report["avg_token_reduction_ratio"] >= 0.85
