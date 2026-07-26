"""Pillar 2 honesty remediation tests (BGE prefix, mem emergency, OTel attrs, gates)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import numpy as np
import pytest

from neuroswarm_arm.runtime.router.embedding_service import (
    BGE_QUERY_PREFIX,
    EmbeddingService,
    apply_bge_query_prefix,
)
from neuroswarm_arm.runtime.router.health import build_health_report
from neuroswarm_arm.runtime.router.history_ranker import HistoryRanker
from neuroswarm_arm.runtime.router.models import EmbeddingSpec
from neuroswarm_arm.runtime.router.telemetry import gen_ai_attrs, mcp_span_attrs


def test_bge_query_prefix_applied_for_bge_small():
    out = apply_bge_query_prefix("list s3 buckets", model_name="BAAI/bge-small-en-v1.5")
    assert out.startswith(BGE_QUERY_PREFIX)
    assert out.endswith("list s3 buckets")


def test_bge_query_prefix_kill_switch(monkeypatch):
    monkeypatch.setenv("NSA_ROUTER_BGE_QUERY_PREFIX", "0")
    out = apply_bge_query_prefix("list s3 buckets", model_name="BAAI/bge-small-en-v1.5")
    assert out == "list s3 buckets"


def test_bge_query_prefix_not_for_other_models():
    out = apply_bge_query_prefix("hello", model_name="sentence-transformers/all-MiniLM-L6-v2")
    assert out == "hello"


def test_encode_query_prefixes_encode_does_not(monkeypatch):
    monkeypatch.setenv("NSA_ROUTER_ALLOW_HASH", "1")
    monkeypatch.setenv("NSA_ROUTER_EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("NSA_ROUTER_BGE_QUERY_PREFIX", "1")
    svc = EmbeddingService(
        EmbeddingSpec(model_name="BAAI/bge-small-en-v1.5", dims=384, backend="hash"),
        allow_hash=True,
    )
    # Force a non-hash backend label to exercise prefix path without FastEmbed
    svc._backend = "fastembed"
    seen: list[str] = []
    orig = svc._encode_uncached

    def _capture(text: str) -> np.ndarray:
        seen.append(text)
        return orig(text)

    svc._encode_uncached = _capture  # type: ignore[method-assign]
    svc.encode("tool schema text")
    svc.encode_query("user intent")
    assert seen[0] == "tool schema text"
    assert seen[1].startswith(BGE_QUERY_PREFIX)
    assert "user intent" in seen[1]


def test_encode_query_skips_prefix_on_hash_backend(monkeypatch):
    monkeypatch.setenv("NSA_ROUTER_ALLOW_HASH", "1")
    monkeypatch.setenv("NSA_ROUTER_EMBEDDING_BACKEND", "hash")
    svc = EmbeddingService(
        EmbeddingSpec(model_name="BAAI/bge-small-en-v1.5", dims=384, backend="hash"),
        allow_hash=True,
    )
    seen: list[str] = []
    orig = svc._encode_uncached

    def _capture(text: str) -> np.ndarray:
        seen.append(text)
        return orig(text)

    svc._encode_uncached = _capture  # type: ignore[method-assign]
    svc.encode_query("user intent")
    assert seen == ["user intent"]


def test_high_conf_gate_health_fallback_is_070():
    class _Cfg:
        ann_backend = "exact"
        turbovec_min_tools = 0
        top_k = 3
        threshold = 0.42
        encoder_name = "BAAI/bge-small-en-v1.5"
        embedding_backend = "hash"
        enable_hot_reload = False
        snapshot_dir = "."
        # deliberately omit high_conf_gate

    class _Idx:
        backend_name = "exact"
        sve_kernels_active = False

        def size(self) -> int:
            return 0

        @property
        def active_backend(self) -> str:
            return "exact_numpy"

        @property
        def fallback_reason(self) -> str:
            return "forced_exact"

    class _Emb:
        backend_name = "hash"
        dims = 384
        cache = None

    class _Reg:
        def size(self) -> int:
            return 0

        def as_list(self):
            return []

    class _Feats:
        arch = "x86_64"
        is_arm64 = False
        neon = False
        sve = False
        sve2 = False
        numa_nodes = 1

    class _Rt:
        config = _Cfg()
        index = _Idx()
        embedder = _Emb()
        registry = _Reg()
        arm_features = _Feats()
        history = None

    report = build_health_report(_Rt())
    assert report["high_conf_gate"] == 0.70


def test_history_ranker_degraded_on_json_emergency(monkeypatch, tmp_path):
    monkeypatch.setenv("NSA_MEM_PROVIDER", "json")
    monkeypatch.setenv("NSA_MEM_STORE", str(tmp_path / "mem"))
    hr = HistoryRanker(root=tmp_path / "mem")
    st = hr.status()
    assert st["history_ranker_degraded"] is True
    assert st.get("emergency_active") is True or st.get("provider") in {
        "json_emergency",
        "json",
        "fallback",
    }


def test_otel_gen_ai_and_mcp_attrs():
    ga = gen_ai_attrs(operation="route")
    assert ga["gen_ai.system"] == "neuroswarm"
    assert ga["gen_ai.provider.name"] == "neuroswarm"
    assert ga["gen_ai.operation.name"] == "route"
    ma = mcp_span_attrs(
        method="tools/call",
        session_id="s3:put_object",
        protocol_version="2025-11-25",
    )
    assert ma["mcp.method.name"] == "tools/call"
    assert ma["mcp.session.id"] == "s3:put_object"
    assert ma["mcp.protocol.version"] == "2025-11-25"
    assert "gen_ai.system" in ma and "gen_ai.provider.name" in ma
