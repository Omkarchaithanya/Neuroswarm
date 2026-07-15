"""Integration + concurrency tests for MAKS."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

import pytest

from neuroswarm_arm.runtime.dipa.cache.maks_connector import MAKSConnector
from neuroswarm_arm.runtime.maks import build_maks, load_maks_config
from neuroswarm_arm.runtime.maks.models import KVIdentity

_ROOT = Path(__file__).resolve().parents[3] / "work" / "test_maks"


def _fresh_dir() -> Path:
    p = _ROOT / uuid.uuid4().hex
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def maks():
    path = _fresh_dir()
    mgr = build_maks(load_maks_config(path), enable_scheduler=False)
    yield mgr
    mgr.stop()
    shutil.rmtree(path, ignore_errors=True)


def test_dipa_connector_roundtrip(maks):
    async def _run():
        conn = MAKSConnector(sharing=maks)
        kid = await conn.save(
            "sess-1",
            b"hello-world",
            agent_id="agent-a",
            metadata={"model_id": "m", "quant": "q4_k"},
        )
        assert kid
        handle = await conn.load("sess-1", "agent-a")
        assert handle
        token = await conn.share(kid, "agent-b")
        assert token
        await conn.release(kid, "agent-b")

    asyncio.run(_run())


def test_identity_mismatch_no_blind_share(maks):
    async def _run():
        a = KVIdentity(model_id="m", quantization="q4")
        b = KVIdentity(model_id="m", quantization="q8")
        h = await maks.create(b"x", agent_id="a1", identity=a, prompt_hash="p")
        h2 = await maks.create(b"x", agent_id="a2", identity=b, prompt_hash="p")
        assert h.kv_id != h2.kv_id

    asyncio.run(_run())


def test_concurrent_creates(maks):
    async def one(i: int):
        return await maks.create(
            f"payload-{i % 5}".encode(),
            agent_id=f"a{i}",
            identity=KVIdentity(model_id="m", quantization="q4"),
            prompt_hash=f"p{i % 5}",
        )

    async def _run():
        handles = await asyncio.gather(*[one(i) for i in range(40)])
        assert len(handles) == 40
        unique = {h.kv_id for h in handles}
        assert len(unique) < 40

    asyncio.run(_run())


def test_refcount_race(maks):
    async def _run():
        h = await maks.create(b"race", agent_id="owner")
        await asyncio.gather(*[maks.share(h.kv_id, f"c{i}") for i in range(20)])
        assert maks.refcount.get(h.kv_id) >= 20
        await asyncio.gather(*[maks.release(h.kv_id, f"c{i}") for i in range(20)])
        await maks.release(h.kv_id, "owner")
        assert maks.refcount.get(h.kv_id) == 0

    asyncio.run(_run())


def test_pressure_relief(maks):
    async def _run():
        maks.config.ram_budget_bytes = 2048
        maks.allocator.ram_budget_bytes = 2048
        for i in range(10):
            await maks.create(b"x" * 400, agent_id=f"a{i}", session_id=f"s{i}")
        freed = await maks.relieve_pressure(bytes_needed=500)
        assert freed >= 0
        snap = maks.pressure_snapshot()
        assert "pressure" in snap

    asyncio.run(_run())


def test_sqlite_registry_persist():
    async def _run():
        path = _fresh_dir()
        try:
            cfg = load_maks_config(path)
            m1 = build_maks(cfg, enable_scheduler=False)
            h = await m1.create(b"persist", agent_id="a1", session_id="s1")
            kid = h.kv_id
            m1.stop()
            m2 = build_maks(load_maks_config(path), enable_scheduler=False)
            rec = await m2.registry.get(kid)
            assert rec is not None
            assert rec.session_id == "s1"
            m2.stop()
        finally:
            shutil.rmtree(path, ignore_errors=True)

    asyncio.run(_run())
