"""PR 1 — ExecutionPipeline routes KV I/O through KVCacheManager."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

import pytest

from neuroswarm_arm.runtime.dipa import build_dipa
from neuroswarm_arm.runtime.dipa.cache.kv_connector import KVConnector
from neuroswarm_arm.runtime.dipa.cache.kv_loader import KVLoader
from neuroswarm_arm.runtime.dipa.cache.kv_writer import KVWriter
from neuroswarm_arm.runtime.dipa.control.kv_cache_manager import KVCacheManager
from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.dipa.execution.execution_state import advance
from neuroswarm_arm.runtime.dipa.interfaces.kv_cache import IKVCacheConnector
from neuroswarm_arm.runtime.dipa.interfaces.types import ExecutionPhase, InferenceRequest


class _RecordingConnector(IKVCacheConnector):
    def __init__(self) -> None:
        self.loads: list[tuple[str, str]] = []
        self.saves: list[tuple[str, bytes, str, Mapping[str, Any] | None]] = []
        self._store: dict[str, bytes] = {}

    async def load(self, session_id: str, agent_id: str = "") -> str | None:
        self.loads.append((session_id, agent_id))
        key = session_id or agent_id
        if key and key in self._store:
            return key
        return None

    async def save(
        self,
        session_id: str,
        payload: bytes,
        *,
        agent_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        key = session_id or agent_id or "anon"
        self.saves.append((session_id, payload, agent_id, metadata))
        self._store[key] = payload
        return key

    async def share(self, key: str, consumer_id: str) -> str:
        return f"share:{key}:{consumer_id}"

    async def release(self, key: str, consumer_id: str = "") -> None:
        self._store.pop(key, None)


class _RaisingConnector(IKVCacheConnector):
    def __init__(self, *, fail_load: bool = False, fail_save: bool = False) -> None:
        self.fail_load = fail_load
        self.fail_save = fail_save

    async def load(self, session_id: str, agent_id: str = "") -> str | None:
        if self.fail_load:
            raise RuntimeError("load failed")
        return session_id or None

    async def save(
        self,
        session_id: str,
        payload: bytes,
        *,
        agent_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        if self.fail_save:
            raise RuntimeError("save failed")
        return session_id or agent_id or "anon"

    async def share(self, key: str, consumer_id: str) -> str:
        return f"share:{key}:{consumer_id}"

    async def release(self, key: str, consumer_id: str = "") -> None:
        return None


@pytest.mark.asyncio
async def test_kv_cache_manager_delegates_to_connector() -> None:
    conn = _RecordingConnector()
    mgr = KVCacheManager(conn)

    assert await mgr.load("sess-a", "agent-1") is None
    handle = await mgr.save("sess-a", b"payload", agent_id="agent-1", metadata={"model": "m1"})
    assert handle == "sess-a"
    assert await mgr.load("sess-a", "agent-1") == "sess-a"
    assert conn.loads == [("sess-a", "agent-1"), ("sess-a", "agent-1")]
    assert len(conn.saves) == 1


@pytest.mark.asyncio
async def test_load_without_connector_returns_none() -> None:
    mgr = KVCacheManager()
    assert mgr.is_wired is False
    assert await mgr.load("sess-x", "agent-x") is None


@pytest.mark.asyncio
async def test_save_without_connector_returns_stable_key() -> None:
    mgr = KVCacheManager()
    assert await mgr.save("sess-y", b"payload", agent_id="agent-y") == "sess-y"
    assert await mgr.save("", b"payload", agent_id="agent-z") == "agent-z"
    assert await mgr.save("", b"payload") == "anon"


def test_run_async_load_matches_loader_sync() -> None:
    conn = _RecordingConnector()
    asyncio.run(conn.save("sess-b", b"seed", agent_id="agent-b"))
    kv_conn = KVConnector(conn)
    loader = KVLoader(kv_conn)
    mgr = KVCacheManager(conn)

    rt = build_dipa(use_mock=True)
    try:
        via_loader = loader.load_sync("sess-b", "agent-b")
        via_manager = rt._run_async(mgr.load("sess-b", "agent-b"))
        assert via_loader == via_manager == "sess-b"
    finally:
        rt.shutdown()


def test_pipeline_uses_kv_cache_manager_for_load_and_save() -> None:
    conn = _RecordingConnector()
    rt = build_dipa(use_mock=True)
    rt.kv_cache_manager = KVCacheManager(conn)
    try:
        req = InferenceRequest(
            messages=[{"role": "user", "content": "hello kv manager"}],
            agent_role="classification",
            max_tokens=16,
            session_id="pipeline-sess",
            agent_id="pipeline-agent",
        )
        ctx = ExecutionContext(request=req, ids=req.ids)
        plan = rt.decision_engine.decide(req)
        ctx.plan = plan
        ctx.mark(advance(ctx.phase, ExecutionPhase.PLANNED))
        result = rt.pipeline._execute_plan(ctx, plan)

        assert "mock-ok" in result.text
        assert conn.loads == [("pipeline-sess", "pipeline-agent")]
        assert len(conn.saves) == 1
        save_session, payload, agent_id, metadata = conn.saves[0]
        assert save_session == "pipeline-sess"
        assert agent_id == "pipeline-agent"
        assert payload.startswith(b"{")
        assert b"session_id" in payload
        assert metadata is not None
        assert metadata.get("record_type") == "session_metadata"
    finally:
        rt.shutdown()


def test_pipeline_raises_when_manager_unwired() -> None:
    rt = build_dipa(use_mock=True)
    rt.kv_cache_manager = KVCacheManager()
    try:
        req = InferenceRequest(
            messages=[{"role": "user", "content": "hello"}],
            agent_role="classification",
            max_tokens=16,
            session_id="unwired-sess",
        )
        ctx = ExecutionContext(request=req, ids=req.ids)
        plan = rt.decision_engine.decide(req)
        ctx.plan = plan
        ctx.mark(advance(ctx.phase, ExecutionPhase.PLANNED))
        with pytest.raises(RuntimeError, match="wired IKVCacheConnector"):
            rt.pipeline._execute_plan(ctx, plan)
    finally:
        rt.shutdown()


def test_load_exception_propagates_through_run_async() -> None:
    rt = build_dipa(use_mock=True)
    rt.kv_cache_manager = KVCacheManager(_RaisingConnector(fail_load=True))
    try:
        with pytest.raises(RuntimeError, match="load failed"):
            rt._run_async(rt.kv_cache_manager.load("sess-e", "agent-e"))
    finally:
        rt.shutdown()


def test_save_exception_propagates_through_run_async() -> None:
    rt = build_dipa(use_mock=True)
    rt.kv_cache_manager = KVCacheManager(_RaisingConnector(fail_save=True))
    try:
        with pytest.raises(RuntimeError, match="save failed"):
            rt._run_async(
                rt.kv_cache_manager.save("sess-f", b"x", agent_id="agent-f")
            )
    finally:
        rt.shutdown()


def test_load_failure_leaves_kv_handle_unset() -> None:
    rt = build_dipa(use_mock=True)
    rt.kv_cache_manager = KVCacheManager(_RaisingConnector(fail_load=True))
    try:
        req = InferenceRequest(
            messages=[{"role": "user", "content": "hello"}],
            agent_role="classification",
            max_tokens=16,
            session_id="fail-sess",
        )
        ctx = ExecutionContext(request=req, ids=req.ids)
        plan = rt.decision_engine.decide(req)
        ctx.plan = plan
        ctx.mark(advance(ctx.phase, ExecutionPhase.PLANNED))
        with pytest.raises(RuntimeError, match="load failed"):
            rt.pipeline._execute_plan(ctx, plan)
        assert ctx.kv_handle is None
    finally:
        rt.shutdown()


def test_run_async_save_matches_writer_sync() -> None:
    conn = _RecordingConnector()
    kv_conn = KVConnector(conn)
    writer = KVWriter(kv_conn)
    mgr = KVCacheManager(conn)
    rt = build_dipa(use_mock=True)
    try:
        payload = b"completion-bytes"
        metadata = {
            "model_id": "tier1",
            "model": "tier1",
            "quantization": "q4",
            "quant": "q4",
            "prompt_hash": "",
            "priority": 0,
        }
        via_writer = writer.save_sync(
            "save-sess",
            payload,
            agent_id="save-agent",
            metadata=metadata,
        )
        via_manager = rt._run_async(
            mgr.save(
                "save-sess",
                payload,
                agent_id="save-agent",
                metadata=metadata,
            )
        )
        assert via_writer == via_manager == "save-sess"
    finally:
        rt.shutdown()
