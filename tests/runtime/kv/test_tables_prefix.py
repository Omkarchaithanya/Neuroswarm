"""Unit tests for KV block tables, hashing, CoW, and prefix cache."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.kv.block.cow import CopyOnWriteEngine
from neuroswarm_arm.runtime.kv.block.tables import LogicalBlockTable, PhysicalBlockTable
from neuroswarm_arm.runtime.kv.interfaces.types import BlockStatus, PhysicalBlockRecord, StorageTier
from neuroswarm_arm.runtime.kv.manager.prefix import PrefixCacheEngine
from neuroswarm_arm.runtime.kv.utils.hashing import content_hash, prefix_block_hash


def test_logical_physical_mapping() -> None:
    logical = LogicalBlockTable("s1")
    logical.map(0, "p1")
    logical.map(1, "p2")
    assert logical.resolve(0) == "p1"
    assert logical.physical_ids() == ["p1", "p2"]
    assert logical.unmap(1) == "p2"
    assert len(logical) == 1


def test_physical_refcount_and_dedup() -> None:
    table = PhysicalBlockTable()
    rec = PhysicalBlockRecord(
        physical_id="p1",
        content_hash=content_hash(b"abc"),
        prefix_hash="",
        tier=StorageTier.L1_RAM,
        provider_key="p1",
    )
    registered = table.register(rec)
    assert registered.physical_id == "p1"
    dup = PhysicalBlockRecord(
        physical_id="p2",
        content_hash=content_hash(b"abc"),
        prefix_hash="",
        tier=StorageTier.L1_RAM,
        provider_key="p2",
    )
    reused = table.register(dup)
    assert reused.physical_id == "p1"
    assert table.get("p1").refcount == 2
    assert table.release("p1") == 1
    assert table.release("p1") == 0
    assert table.get("p1") is None


def test_prefix_hash_chain() -> None:
    h0 = ""
    h1 = prefix_block_hash(h0, b"block1")
    h2 = prefix_block_hash(h1, b"block2")
    assert h1 != h2
    cache = PrefixCacheEngine()
    cache.insert(prefix_hash=h0, block_payload=b"block1", physical_id="p1", token_end=256)
    cache.insert(prefix_hash=h1, block_payload=b"block2", physical_id="p2", token_end=512)
    match = cache.longest_prefix_match([b"block1", b"block2", b"block3"])
    assert match.hit
    assert match.matched_blocks == ["p1", "p2"]
    assert match.matched_tokens == 512


def test_copy_on_write() -> None:
    table = PhysicalBlockTable()
    payload = b"shared"
    rec = table.register(
        PhysicalBlockRecord(
            physical_id="p1",
            content_hash=content_hash(payload),
            prefix_hash="",
            tier=StorageTier.L1_RAM,
            provider_key="p1",
            refcount=1,
        )
    )
    table.acquire(rec.physical_id)
    cow = CopyOnWriteEngine(table)
    assert cow.needs_cow(rec.physical_id)
    clone = cow.clone(rec.physical_id, b"mutated", provider_key="p_clone")
    assert clone.physical_id != rec.physical_id
    assert table.get(rec.physical_id) is not None
    assert table.get(rec.physical_id).status == BlockStatus.ALLOCATED
