"""Unit tests — lifecycle, refcount, dedup, hashing."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

import pytest

from neuroswarm_arm.runtime.maks import build_maks, load_maks_config
from neuroswarm_arm.runtime.maks.exceptions import KVPinnedError, KVStateError
from neuroswarm_arm.runtime.maks.hashing import SHA256Hasher
from neuroswarm_arm.runtime.maks.lifecycle import LifecycleManager
from neuroswarm_arm.runtime.maks.models import KVIdentity, KVState, ProviderName
from neuroswarm_arm.runtime.maks.reference_counter import ReferenceCounter

_ROOT = Path(__file__).resolve().parents[3] / "work" / "test_maks"


def _fresh_dir() -> Path:
    p = _ROOT / uuid.uuid4().hex
    p.mkdir(parents=True, exist_ok=True)
    return p


def test_hasher_identity_differs_by_quant():
    h = SHA256Hasher()
    a = KVIdentity(model_id="m", quantization="q4")
    b = KVIdentity(model_id="m", quantization="q8")
    assert h.hash_identity(a) != h.hash_identity(b)


def test_lifecycle_transitions():
    life = LifecycleManager()
    life.bind("k1", KVState.ALLOCATED)
    life.transition("k1", KVState.WARMED)
    life.transition("k1", KVState.SHARED)
    life.transition("k1", KVState.PINNED)
    with pytest.raises(KVStateError):
        life.transition("k1", KVState.EVICTED)


def test_refcount_orphan_zombie():
    rc = ReferenceCounter(orphan_grace_s=0.0)
    rc.increment("k1", "a")
    rc.decrement("k1", "a")
    assert rc.get("k1") == 0
    rc.increment("ghost", "")
    assert "ghost" in rc.orphans()
    assert "ghost" in rc.zombies({"k1"})


@pytest.fixture
def maks():
    path = _fresh_dir()
    mgr = build_maks(load_maks_config(path), enable_scheduler=False)
    yield mgr
    mgr.stop()
    shutil.rmtree(path, ignore_errors=True)


def test_create_share_release(maks):
    async def _run():
        h = await maks.create(b"payload", agent_id="a1", session_id="s1")
        tok = await maks.share(h.kv_id, "a2")
        assert tok
        data = await maks.load_payload(h.kv_id)
        assert data == b"payload"
        await maks.release(h.kv_id, "a2")
        await maks.release(h.kv_id, "a1")

    asyncio.run(_run())


def test_dedup_reuse(maks):
    async def _run():
        ident = KVIdentity(model_id="llama", quantization="q4_k")
        h1 = await maks.create(b"same", agent_id="a1", identity=ident, prompt_hash="p1")
        h2 = await maks.create(b"same", agent_id="a2", identity=ident, prompt_hash="p1")
        assert h1.kv_id == h2.kv_id
        assert maks.dedup.stats.hits >= 1

    asyncio.run(_run())


def test_pin_blocks_delete(maks):
    async def _run():
        h = await maks.create(b"x", agent_id="a1")
        await maks.pin(h.kv_id)
        with pytest.raises(KVPinnedError):
            await maks.delete(h.kv_id)
        await maks.unpin(h.kv_id)
        await maks.delete(h.kv_id)

    asyncio.run(_run())


def test_migrate_ram_to_mmap(maks):
    async def _run():
        h = await maks.create(b"migrate-me" * 10, agent_id="a1")
        loc = await maks.migrate(h.kv_id, ProviderName.MMAP, reason="test")
        assert "mmap" in loc
        data = await maks.load_payload(h.kv_id)
        assert data.startswith(b"migrate-me")

    asyncio.run(_run())


def test_prefix_lookup(maks):
    async def _run():
        ident = KVIdentity(model_id="m", quantization="q4")
        h = await maks.create(
            b"doc",
            agent_id="a1",
            identity=ident,
            prompt_hash="abc123prefix",
        )
        found = await maks.lookup(prompt_hash="abc123", identity=ident, partial_prefix=True)
        assert found is not None
        assert found.kv_id == h.kv_id

    asyncio.run(_run())


def test_mte_unavailable(maks):
    async def _run():
        from neuroswarm_arm.runtime.maks.exceptions import KVProviderUnavailableError

        with pytest.raises(KVProviderUnavailableError):
            await maks.migrate(
                (await maks.create(b"z", agent_id="a")).kv_id,
                ProviderName.FUTURE_MTE,
            )

    asyncio.run(_run())


def test_page_pool_registers_on_create(maks):
    async def _run():
        h = await maks.create(b"page-payload" * 100, agent_id="a1", session_id="s-pool")
        pages = maks.pool.pages_for(h.kv_id)
        assert len(pages) >= 1
        assert maks.pool.get_table(h.kv_id) is not None
        stats = maks.pool.stats()
        assert stats["handles"] >= 1
        assert stats["pages"] >= 1

    asyncio.run(_run())


def test_scored_eviction_default(maks):
    from neuroswarm_arm.runtime.maks.models import EvictionPolicyName
    from neuroswarm_arm.runtime.maks.policies.scored import ScoredEvictionPolicy

    assert maks.config.eviction_policy is EvictionPolicyName.SCORED
    assert isinstance(maks.eviction.policy, ScoredEvictionPolicy)


def test_capability_matrix_no_cross_model(maks):
    matrix = maks.capability_matrix()
    assert "llama.cpp" in matrix
    assert "vllm" in matrix
    assert "sglang" in matrix
    assert matrix["llama.cpp"]["supports_cross_model_reuse"] is False
    assert matrix["vllm"]["supports_paged_kv"] is True
    assert matrix["llama.cpp"]["supports_paged_kv"] is False
    assert maks.capabilities.can_reuse("llama.cpp", cross_model=True) is False


def test_connector_capability_surface(maks):
    from neuroswarm_arm.runtime.dipa.cache.maks_connector import MAKSConnector

    conn = MAKSConnector(sharing=maks, backend_id="llama.cpp")
    assert conn.supports_prefix_reuse() is True
    assert conn.supports_cross_model_reuse() is False
    assert conn.supports_paged_kv() is False
    assert "llama.cpp" in conn.capability_matrix()


def test_pressure_monitor_unified(maks):
    async def _run():
        await maks.create(b"pressure-bytes" * 50, agent_id="a1")
        snap = maks.pressure_snapshot()
        assert "pressure" in snap
        assert "pages" in snap
        assert "fragmentation" in snap
        assert snap["used_bytes"] > 0

    asyncio.run(_run())


def test_cow_share_increments_pool(maks):
    async def _run():
        h = await maks.create(b"shared", agent_id="a1")
        await maks.share(h.kv_id, "a2")
        pages = maks.pool.pages_for(h.kv_id)
        assert pages
        assert pages[0].share_count >= 1

    asyncio.run(_run())
