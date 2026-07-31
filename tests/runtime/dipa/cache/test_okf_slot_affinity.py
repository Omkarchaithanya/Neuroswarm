"""Tests for OKF block-hash slot affinity (Phase 2)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from neuroswarm_arm.runtime.dipa.cache.okf_slot_affinity import BlockHashSlotAffinity
from neuroswarm_arm.runtime.dipa.cache.prefix_cache_manager import PrefixCacheManager
from neuroswarm_arm.runtime.slot_registry import SlotRegistry
from neuroswarm_arm.runtime.slot_router import SlotRouter


def test_same_content_same_hash_same_slot() -> None:
    aff = BlockHashSlotAffinity(num_slots=4)
    content = "shared-prefix-block"
    h1 = aff.hash_block(content)
    h2 = aff.hash_block(content)
    assert h1 == h2

    aff.assign_slot(h1, 2)
    assert aff.get_slot(h1) == 2
    assert aff.get_slot(h2) == 2


def test_different_content_different_hash() -> None:
    aff = BlockHashSlotAffinity(num_slots=4)
    h_a = aff.hash_block("block-alpha")
    h_b = aff.hash_block("block-beta")
    assert h_a != h_b


def test_ttl_expiry_evicts_stale_mappings() -> None:
    aff = BlockHashSlotAffinity(num_slots=4, ttl_seconds=60)
    block_hash = aff.hash_block("ttl-block")

    with patch(
        "neuroswarm_arm.runtime.dipa.cache.okf_slot_affinity.time.monotonic",
        side_effect=[100.0, 150.0, 200.0],
    ):
        aff.assign_slot(block_hash, 1)
        assert aff.get_slot(block_hash) == 1
        assert aff.get_slot(block_hash) is None

    assert aff.evict_expired() == 0
    stats = aff.stats()
    assert stats["active_mappings"] == 0
    assert stats["evictions_total"] >= 1


def test_stats_hit_rate() -> None:
    aff = BlockHashSlotAffinity(num_slots=4)
    h = aff.hash_block("stats-block")
    aff.assign_slot(h, 0)

    for _ in range(3):
        assert aff.get_slot(h) == 0
    for _ in range(2):
        assert aff.get_slot("missing-hash") is None

    stats = aff.stats()
    assert stats["hit_rate"] == pytest.approx(3 / 5)
    assert stats["active_mappings"] == 1


def test_integration_shared_prefix_same_slot() -> None:
    prefix = "institutional-okf-knowledge-prefix"
    affinity = BlockHashSlotAffinity(num_slots=4, ttl_seconds=300)
    cache = PrefixCacheManager(slot_affinity=affinity, num_slots=4)
    router = SlotRouter(registry=SlotRegistry(total_slots=4))

    asyncio.run(cache.warm(prefix))

    payload_a, _ = router.prepare_payload("agent-a", prefix, {})
    slot_a = payload_a["id_slot"]
    cache.record_slot_assignment(prefix, slot_a)

    lookup = cache.lookup(prefix)
    assert lookup["warmed"] is True
    assert lookup["affinity_slot"] == slot_a

    payload_b, telemetry_b = router.prepare_payload(
        "agent-b",
        prefix,
        {},
        affinity_hint=lookup["affinity_slot"],
    )
    assert payload_b["id_slot"] == slot_a
    assert telemetry_b.get("affinity_hint_honored") is True


def test_assign_slot_rejects_out_of_range() -> None:
    aff = BlockHashSlotAffinity(num_slots=2)
    with pytest.raises(ValueError, match="out of range"):
        aff.assign_slot(aff.hash_block("x"), 5)


def test_hash_block_backward_compat() -> None:
    a = BlockHashSlotAffinity(num_slots=4)
    assert a.hash_block("hello") == a.hash_block("hello", tool_ids=())
    assert a.hash_block("hello", tool_ids=()) == a.hash_block("hello", tool_ids=("",))
    assert a.hash_block("hello", tool_ids=("a",)) != a.hash_block("hello", tool_ids=("b",))


def test_tool_ids_slot_namespace_distinct() -> None:
    aff = BlockHashSlotAffinity(num_slots=8)
    h_a = aff.hash_block("shared", tool_ids=("tool.a",))
    h_b = aff.hash_block("shared", tool_ids=("tool.b",))
    assert h_a != h_b
    aff.assign_slot(h_a, 1, tool_ids=("tool.a",))
    aff.assign_slot(h_b, 2, tool_ids=("tool.b",))
    assert aff.get_slot(h_a, tool_ids=("tool.a",)) == 1
    assert aff.get_slot(h_b, tool_ids=("tool.b",)) == 2

