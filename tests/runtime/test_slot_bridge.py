"""Tests for session-to-slot registry and router."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from neuroswarm_arm.runtime.slot_registry import SlotRegistry
from neuroswarm_arm.runtime.slot_router import SlotRouter


def test_slot_registry_acquire_lookup_release() -> None:
    reg = SlotRegistry(total_slots=4)
    slot_id, reused = reg.acquire("sess-a")
    assert reused is False
    assert slot_id == 0
    assert reg.lookup("sess-a") == 0
    meta = reg.get_metadata(slot_id)
    assert meta is not None
    assert meta.session_id == "sess-a"
    reg.release("sess-a")
    assert reg.lookup("sess-a") is None


def test_slot_registry_reuses_existing_binding() -> None:
    reg = SlotRegistry(total_slots=4)
    first, reused_first = reg.acquire("sess-a", prefix_hash="h1")
    second, reused_second = reg.acquire("sess-a", prefix_hash="h2")
    assert first == second == 0
    assert reused_first is False
    assert reused_second is True
    meta = reg.get_metadata(first)
    assert meta is not None
    assert meta.prefix_hash == "h2"


def test_slot_registry_lru_eviction() -> None:
    reg = SlotRegistry(total_slots=2)
    with patch(
        "neuroswarm_arm.runtime.slot_registry.time.time",
        side_effect=[100.0, 200.0, 300.0],
    ):
        reg.acquire("old")
        reg.acquire("new")
        slot_id, reused = reg.acquire("third")
    assert reused is False
    assert reg.lookup("old") is None
    assert reg.lookup("new") == 1
    assert reg.lookup("third") == slot_id
    assert slot_id in {0, 1}


def test_slot_router_prepare_payload_existing_binding() -> None:
    reg = SlotRegistry(total_slots=4)
    reg.acquire("sess-1", prefix_hash="abc")
    router = SlotRouter(registry=reg)
    payload, telemetry = router.prepare_payload(
        "sess-1",
        "hello",
        {"messages": [{"role": "user", "content": "hello"}]},
    )
    assert payload["cache_prompt"] is True
    assert payload["id_slot"] == 0
    assert telemetry["slot_reused"] is True
    assert telemetry["slot_id"] == 0


def test_slot_router_prepare_payload_assigns_idle_slot() -> None:
    reg = SlotRegistry(total_slots=4)
    router = SlotRouter(registry=reg)
    payload, telemetry = router.prepare_payload("sess-new", "hello", {})
    assert payload == {"cache_prompt": True, "id_slot": 0}
    assert telemetry["slot_reused"] is False
    assert telemetry["slot_id"] == 0


def test_slot_router_prepare_payload_without_session() -> None:
    router = SlotRouter(registry=SlotRegistry(total_slots=2))
    payload, telemetry = router.prepare_payload("", "hello", {"max_tokens": 8})
    assert payload == {"max_tokens": 8, "cache_prompt": True}
    assert telemetry["slot_reused"] is False
    assert telemetry["slot_id"] is None
