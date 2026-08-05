"""Unit / integration tests for DIPA PD orchestration."""

from __future__ import annotations

import os

from neuroswarm_arm.runtime.dipa.backends.factory import BackendFactory
from neuroswarm_arm.runtime.dipa.backends.llama_cpp import LlamaCppBackend
from neuroswarm_arm.runtime.dipa.backends.mock_backend import MockBackend
from neuroswarm_arm.runtime.dipa.backends.registry import BackendRegistry
from neuroswarm_arm.runtime.dipa.cache.prefix_cache_manager import PrefixCacheManager
from neuroswarm_arm.runtime.dipa.factory import build_dipa
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    InferenceRequest,
    KVTransferMode,
    PDMode,
    PrefillResult,
)
from neuroswarm_arm.runtime.dipa.pd.chunk_planner import ChunkPlanner
from neuroswarm_arm.runtime.dipa.pd.kv_transfer import KVTransferManager
from neuroswarm_arm.runtime.dipa.runtime.runtime_config import DIPARuntimeConfig


def test_chunk_planner_splits_long_prompt() -> None:
    planner = ChunkPlanner()
    words = " ".join(f"w{i}" for i in range(100))
    req = InferenceRequest(messages=[{"role": "user", "content": words}])
    chunks = planner.plan(req, chunk_size=20)
    assert len(chunks) > 1
    assert chunks[-1].total == len(chunks)
    assert "w99" in chunks[-1].messages[-1]["content"]


def test_kv_transfer_recompute_mode() -> None:
    xfer = KVTransferManager(default_mode=KVTransferMode.RECOMPUTE)
    mode = xfer.resolve_mode(
        prefill_backend="sglang",
        decode_backend="llama_cpp",
    )
    assert mode == KVTransferMode.RECOMPUTE
    handle = __import__("asyncio").run(
        xfer.handoff(
            PrefillResult(
                prefix_tokens=100,
                prefix_hit_tokens=40,
                backend="sglang",
                transfer_mode=KVTransferMode.RECOMPUTE,
                messages=[{"role": "user", "content": "hi"}],
            ),
            messages=[{"role": "user", "content": "hi"}],
            decode_backend="llama_cpp",
        )
    )
    assert handle.recompute_tokens == 60
    assert handle.transfer_mode == KVTransferMode.RECOMPUTE


def test_backend_factory_mock_registers_sglang() -> None:
    cfg = DIPARuntimeConfig(pd_mode="soft")
    reg = BackendFactory(cfg).build_registry(use_mock=True)
    assert reg.get("sglang") is not None
    assert isinstance(reg.get("sglang"), MockBackend)
    assert reg.get("llama_cpp") is not None


def test_backend_factory_injects_draft_model_config(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("NSA_TIER_SPEC_URL", raising=False)
    monkeypatch.delenv("NSA_DRAFT_MODEL_PATH", raising=False)
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "0")
    draft = tmp_path / "draft.gguf"
    draft.write_text("fake", encoding="utf-8")
    cfg = DIPARuntimeConfig(
        cascade={"speculation": {"enabled": True}},
        draft_models={
            "path": str(draft),
            "port": 9081,
            "ctx_size": 1024,
            "n_threads": 8,
        },
    )

    reg = BackendFactory(cfg).build_registry(
        tier_urls={"tier2": "http://127.0.0.1:8082"}
    )
    backend = reg.require("tier2")

    assert isinstance(backend, LlamaCppBackend)
    assert backend.draft_base_url == "http://127.0.0.1:9081"
    assert backend.capabilities.speculation is True
    assert backend._draft_command == [
        "llama-server",
        "-m",
        str(draft),
        "--port",
        "9081",
        "-c",
        "1024",
        "-t",
        "8",
        "--host",
        "127.0.0.1",
    ]


def test_backend_factory_uses_explicit_spec_url_without_spawning(monkeypatch) -> None:
    monkeypatch.setenv("NSA_TIER_SPEC_URL", "http://draft.example:8081")
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "0")
    cfg = DIPARuntimeConfig(cascade={"speculation": {"enabled": True}})

    reg = BackendFactory(cfg).build_registry(
        tier_urls={"tier2": "http://127.0.0.1:8082"}
    )
    backend = reg.require("tier2")

    assert isinstance(backend, LlamaCppBackend)
    assert backend.draft_base_url == "http://draft.example:8081"
    assert backend._draft_command is None
    assert backend.capabilities.speculation is True


def test_backend_factory_disables_missing_draft_model(caplog, monkeypatch) -> None:
    monkeypatch.delenv("NSA_TIER_SPEC_URL", raising=False)
    monkeypatch.setenv("NSA_DRAFT_MODEL_PATH", "missing-draft.gguf")
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "0")
    cfg = DIPARuntimeConfig(cascade={"speculation": {"enabled": True}})

    reg = BackendFactory(cfg).build_registry(
        tier_urls={"tier2": "http://127.0.0.1:8082"}
    )
    backend = reg.require("tier2")

    assert isinstance(backend, LlamaCppBackend)
    assert backend.draft_base_url == ""
    assert backend.capabilities.speculation is False
    assert "Draft model file does not exist" in caplog.text


def test_backend_factory_starts_draft_when_supervisor_is_ready(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("NSA_TIER_SPEC_URL", raising=False)
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "0")
    draft = tmp_path / "draft.gguf"
    draft.write_text("fake", encoding="utf-8")
    calls: list[tuple[str, list[str], str]] = []

    class FakeSupervisor:
        def start_draft(self, name, command, *, base_url):
            calls.append((name, list(command), base_url))

    reg = BackendRegistry()
    reg.register(
        LlamaCppBackend(
            name="tier2",
            base_url="http://127.0.0.1:8082",
            supervisor=FakeSupervisor(),
        )
    )
    cfg = DIPARuntimeConfig(
        cascade={"speculation": {"enabled": True}},
        draft_models={"path": str(draft)},
    )

    BackendFactory(cfg).build_registry(existing=reg, tier_urls={"tier2": "x"})

    assert calls
    assert calls[0][0] == "tier2"
    assert calls[0][1][:3] == ["llama-server", "-m", str(draft)]
    assert calls[0][2] == "http://127.0.0.1:8081"


def test_prefix_cache_hit_ratio() -> None:
    cache = PrefixCacheManager()
    cache.record_hit("a", 10, 20)
    cache.record_hit("b", 0, 10)
    snap = cache.snapshot()
    assert snap["hits"] == 1.0
    assert snap["misses"] == 1.0
    assert snap["hit_ratio"] == 0.5


def test_soft_pd_end_to_end_mock() -> None:
    os.environ["NSA_DIPA_PD_MODE"] = "soft"
    os.environ["NSA_DIPA_PD_MIN_PROMPT_TOKENS"] = "1"
    try:
        cfg = DIPARuntimeConfig(pd_mode="soft", pd_min_prompt_tokens=1, chunk_size=32)
        rt = build_dipa(cfg=cfg, use_mock=True, start=True)
        try:
            # Replace sglang with mock if factory used real (should be mock).
            if rt.backends.get("sglang") is None:
                rt.backends.register(MockBackend(name="sglang"))
            words = " ".join(f"token{i}" for i in range(80))
            req = InferenceRequest(
                messages=[{"role": "user", "content": words}],
                max_tokens=16,
                stream=False,
            )
            plan = rt.decision_engine.decide(req)
            assert plan.pd_mode == PDMode.SOFT
            assert plan.pd_enabled is True
            resp = rt.infer(req)
            assert resp.text
            assert resp.metrics.get("pd_enabled") == 1.0
            assert "kv_transfer_mode" in resp.metrics
            assert rt.metrics.snapshot().get("dipa_chunk_count", 0) >= 1.0
        finally:
            rt.shutdown()
    finally:
        os.environ.pop("NSA_DIPA_PD_MODE", None)
        os.environ.pop("NSA_DIPA_PD_MIN_PROMPT_TOKENS", None)


def test_pd_off_keeps_cascade() -> None:
    cfg = DIPARuntimeConfig(pd_mode="off")
    rt = build_dipa(cfg=cfg, use_mock=True, start=True)
    try:
        req = InferenceRequest(
            messages=[{"role": "user", "content": "hello world"}],
            max_tokens=8,
        )
        plan = rt.decision_engine.decide(req)
        assert plan.pd_enabled is False
        resp = rt.infer(req)
        assert resp.text.startswith("mock-ok:")
    finally:
        rt.shutdown()


def test_health_includes_pd_block() -> None:
    cfg = DIPARuntimeConfig(pd_mode="soft")
    rt = build_dipa(cfg=cfg, use_mock=True, start=True)
    try:
        health = rt.health()
        assert "pd" in health
        assert health["pd"]["mode"] == "soft"
    finally:
        rt.shutdown()


def test_prefix_warm() -> None:
    import asyncio

    cache = PrefixCacheManager(sglang_backend=MockBackend(name="sglang"))
    out = asyncio.run(cache.warm("system prompt shared across agents"))
    assert out.get("key")
    assert cache.snapshot()["warmed"] == 1.0
