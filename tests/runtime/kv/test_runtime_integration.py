"""Integration tests for allocate, checkpoint, restore, dedup, tiering."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from neuroswarm_arm.runtime.kv.factory import build_kv_runtime
from neuroswarm_arm.runtime.kv.interfaces.types import StorageTier
from neuroswarm_arm.runtime.kv.utils.config import load_kv_config

_WORK = Path(__file__).resolve().parents[3] / "work" / "test-kv"


@pytest.fixture
def runtime():
    root = _WORK / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    cfg = load_kv_config(root)
    cfg.compression = "none"
    cfg.enable_background_migration = False
    rt = build_kv_runtime(cfg, enable_background=False)
    try:
        yield rt
    finally:
        rt.shutdown()
        shutil.rmtree(root, ignore_errors=True)

@pytest.mark.asyncio
async def test_allocate_and_dedup(runtime) -> None:
    payload = b"identical" * 32
    b1 = await runtime.allocate("s1", payload)
    b2 = await runtime.allocate("s1", payload)
    assert b1.physical_id == b2.physical_id
    assert runtime.block_manager.physical.get(b1.physical_id).refcount >= 2
    metrics = runtime.metrics()
    assert metrics["kv_blocks_total"] >= 1
    assert metrics["kv_dedup_ratio"] > 0


@pytest.mark.asyncio
async def test_checkpoint_restore(runtime) -> None:
    sid = "sess-restore"
    await runtime.allocate(sid, b"hello-kv-world")
    ckpt = await runtime.checkpoint(sid)
    assert ckpt["status"] == "ok"
    await runtime.release(sid)
    assert runtime.get_session(sid) is None
    restored = await runtime.restore(sid)
    assert restored.session_id == sid
    assert len(restored.blocks) >= 1
    resumed = await runtime.resume(sid)
    assert resumed.session_id == sid


@pytest.mark.asyncio
async def test_prefix_reuse(runtime) -> None:
    payloads = [b"aaa" * 16, b"bbb" * 16, b"ccc" * 16]
    prefix = ""
    for i, p in enumerate(payloads):
        block = await runtime.allocate("src", p, token_start=i * 256, prefix_hash=prefix)
        prefix = block.content_hash
    match = runtime.lookup_prefix(payloads[:2])
    assert match.hit
    reused = runtime.reuse_prefix("dst", match)
    assert len(reused) == 2


@pytest.mark.asyncio
async def test_migration_l1_to_l2(runtime) -> None:
    block = await runtime.allocate("mig", b"cold-data" * 64)
    assert block.physical_id
    ok = await runtime.migrate(block.physical_id, StorageTier.L2_COMPRESSED_RAM)
    assert ok
    rec = runtime.block_manager.physical.get(block.physical_id)
    assert rec is not None
    assert rec.tier == StorageTier.L2_COMPRESSED_RAM
    data = await runtime.block_manager.read_payload(block.physical_id)
    assert data == b"cold-data" * 64


@pytest.mark.asyncio
async def test_share_mmap(runtime) -> None:
    block = await runtime.allocate("share", b"shared-bytes")
    token = await runtime.share(block.physical_id, "agent-b")
    assert token.startswith("share:")
    loaded = await runtime.sharing.load(block.physical_id)
    assert loaded == b"shared-bytes"


@pytest.mark.asyncio
async def test_pressure_snapshot(runtime) -> None:
    await runtime.allocate("p", b"x" * 1024)
    snap = runtime.pressure_snapshot()
    assert 0.0 <= snap.pressure <= 1.0
    assert snap.blocks_total >= 1
    status = runtime.status()
    assert status["ok"] is True
