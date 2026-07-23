"""Tests for OKF block-hash slot affinity."""

from __future__ import annotations

import hashlib

import pytest

from neuroswarm_arm.runtime.okf_slot_affinity import OkfSlotAffinity, block_hashes_from_baggage
from neuroswarm_arm.runtime.radix_slot_router import RadixSlotRouter
from neuroswarm_arm.runtime.slot_registry import SlotRegistry


def _hash_block(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def test_hash_block_stable() -> None:
    try:
        from nexus_okf.internal.hashutil import hash_block
    except ImportError:
        pytest.skip("nexus_okf not installed")
    assert hash_block("okf-block-content") == _hash_block("okf-block-content")
    assert hash_block("okf-block-content") == hash_block("okf-block-content")


def test_okf_affinity_lru() -> None:
    aff = OkfSlotAffinity(max_entries=2)
    aff.record(["h1"], 0)
    aff.record(["h2"], 1)
    aff.record(["h3"], 2)
    assert aff.lookup(["h1"]) is None
    assert aff.lookup(["h2"]) == 1
    assert aff.lookup(["h3"]) == 2


def test_two_agents_same_okf_block_share_slot() -> None:
    block = "shared-okf-institutional-knowledge"
    block_hash = _hash_block(block)
    aff = OkfSlotAffinity()
    router = RadixSlotRouter(
        registry=SlotRegistry(total_slots=4),
        min_match=64,
        okf_affinity=aff,
    )

    tokens_a = list(range(200)) + [501, 502]
    tokens_b = list(range(200)) + [601, 602, 603]

    payload_a, _ = router.prepare_payload(
        "agent-a",
        "prompt-a",
        {},
        token_ids=tokens_a,
        okf_block_hashes=[block_hash],
    )
    slot_a = payload_a["id_slot"]
    aff.record([block_hash], slot_a)

    payload_b, meta_b = router.prepare_payload(
        "agent-b",
        "prompt-b",
        {},
        token_ids=tokens_b,
        okf_block_hashes=[block_hash],
    )
    assert payload_b["cache_prompt"] is True
    assert payload_b["id_slot"] == slot_a
    assert meta_b.get("okf_affinity") is True


def test_block_hashes_from_baggage_blocks() -> None:
    hashes = block_hashes_from_baggage({"okf_blocks": ["alpha", "beta"]})
    assert len(hashes) == 2
    assert hashes[0] == _hash_block("alpha")
