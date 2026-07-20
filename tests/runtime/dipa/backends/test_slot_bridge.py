"""Tests for llama-server session-to-slot bridge."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from neuroswarm_arm.runtime.dipa.backends.llama_cpp.backend import (
    LlamaCppBackend,
    _llama_chat_extra,
)
from neuroswarm_arm.runtime.dipa.backends.llama_cpp.slot_registry import SlotRegistry
from neuroswarm_arm.runtime.dipa.backends.llama_cpp.slot_router import SlotRouter
from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.dipa.interfaces.types import GenerateRequest, InferenceRequest


def test_slot_registry_bind_lookup_release() -> None:
    reg = SlotRegistry()
    reg.bind("sess-a", 2, "http://tier2:8080")
    assert reg.lookup("sess-a", "http://tier2:8080") == 2
    reg.release("sess-a", "http://tier2:8080")
    assert reg.lookup("sess-a", "http://tier2:8080") is None


def test_slot_registry_evict_lru() -> None:
    reg = SlotRegistry()
    reg.bind("old", 0, "http://t:8080")
    reg.bind("new", 1, "http://t:8080")
    evicted = reg.evict_lru("http://t:8080")
    assert evicted is not None
    session_id, id_slot = evicted
    assert session_id == "old"
    assert id_slot == 0
    assert reg.lookup("old", "http://t:8080") is None
    assert reg.lookup("new", "http://t:8080") == 1


def test_slot_router_acquire_existing_binding() -> None:
    reg = SlotRegistry()
    reg.bind("sess-1", 3, "http://127.0.0.1:8080")
    client = MagicMock()
    router = SlotRouter(registry=reg, client=client, tier_url="http://127.0.0.1:8080")
    extra = router.acquire("sess-1", "http://127.0.0.1:8080")
    assert extra == {"cache_prompt": True, "id_slot": 3}
    client.slots.assert_not_called()


def test_slot_router_acquire_idle_slot() -> None:
    reg = SlotRegistry()
    client = MagicMock()
    client.slots.return_value = [
        {"id": 0, "is_processing": False},
        {"id": 1, "is_processing": True},
    ]
    router = SlotRouter(registry=reg, client=client, tier_url="http://127.0.0.1:8080")
    extra = router.acquire("sess-new", "http://127.0.0.1:8080")
    assert extra["cache_prompt"] is True
    assert extra["id_slot"] == 0


def test_llama_chat_extra_uses_slot_router() -> None:
    reg = SlotRegistry()
    reg.bind("s", 5, "http://127.0.0.1:8080")
    router = SlotRouter(registry=reg, tier_url="http://127.0.0.1:8080")
    extra = _llama_chat_extra(
        session_id="s",
        slot_router=router,
        tier_url="http://127.0.0.1:8080",
    )
    assert extra["id_slot"] == 5
    assert extra["cache_prompt"] is True


@pytest.mark.asyncio
async def test_generate_uses_cache_prompt_and_id_slot() -> None:
    backend = LlamaCppBackend(name="tier2", base_url="http://127.0.0.1:8080", tier=2)
    backend._client = MagicMock()
    backend._client.chat.return_value = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        "id_slot": 2,
    }
    reg = backend._slot_router._registry
    reg.bind("sess-x", 2, "http://127.0.0.1:8080")
    req = GenerateRequest(
        messages=[{"role": "user", "content": "hi"}],
        session_id="sess-x",
        kv_handle="kv_should_not_be_sent",
    )
    ctx = ExecutionContext(
        request=InferenceRequest(messages=[{"role": "user", "content": "hi"}]),
    )
    await backend.generate(req, ctx)
    kwargs = backend._client.chat.call_args.kwargs
    extra = kwargs["extra"]
    assert extra["cache_prompt"] is True
    assert extra["id_slot"] == 2
    assert "kv_handle" not in extra
