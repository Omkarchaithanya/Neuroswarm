"""Tests for llama-server session-to-slot bridge."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from neuroswarm_arm.runtime.dipa.backends.llama_cpp.backend import (
    LlamaCppBackend,
    _llama_chat_extra,
)
from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.dipa.interfaces.types import GenerateRequest, InferenceRequest
from neuroswarm_arm.runtime.slot_registry import SlotRegistry
from neuroswarm_arm.runtime.slot_router import SlotRouter


def test_slot_router_prepare_payload_reuses_binding() -> None:
    reg = SlotRegistry(total_slots=4)
    reg.acquire("sess-1")
    router = SlotRouter(registry=reg)
    payload, telemetry = router.prepare_payload("sess-1", "hello", {})
    assert payload == {"cache_prompt": True, "id_slot": 0}
    assert telemetry["slot_reused"] is True


def test_slot_router_prepare_payload_assigns_slot() -> None:
    reg = SlotRegistry(total_slots=4)
    router = SlotRouter(registry=reg)
    payload, telemetry = router.prepare_payload("sess-new", "hello", {})
    assert payload["cache_prompt"] is True
    assert payload["id_slot"] == 0
    assert telemetry["slot_reused"] is False


def test_llama_chat_extra_uses_slot_router() -> None:
    reg = SlotRegistry(total_slots=4)
    reg.acquire("s")
    router = SlotRouter(registry=reg)
    extra, telemetry = _llama_chat_extra(
        session_id="s",
        messages=[{"role": "user", "content": "hi"}],
        slot_router=router,
    )
    assert extra["id_slot"] == 0
    assert extra["cache_prompt"] is True
    assert telemetry["slot_reused"] is True


@pytest.mark.asyncio
async def test_generate_uses_cache_prompt_and_id_slot() -> None:
    backend = LlamaCppBackend(name="tier2", base_url="http://127.0.0.1:8080", tier=2)
    backend._slot_router = SlotRouter(registry=SlotRegistry(total_slots=4))
    backend._client = MagicMock()
    backend._client.chat.return_value = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        "id_slot": 0,
    }
    backend._slot_router.registry.acquire("sess-x")
    req = GenerateRequest(
        messages=[{"role": "user", "content": "hi"}],
        session_id="sess-x",
        kv_handle="kv_should_not_be_sent",
    )
    ctx = ExecutionContext(
        request=InferenceRequest(messages=[{"role": "user", "content": "hi"}]),
    )
    result = await backend.generate(req, ctx)
    kwargs = backend._client.chat.call_args.kwargs
    extra = kwargs["extra"]
    assert extra["cache_prompt"] is True
    assert extra["id_slot"] == 0
    assert "kv_handle" not in extra
    assert result.metrics["slot_id"] == 0.0
    assert result.metrics["slot_reused"] == 1.0
    assert "ttft_seconds" in result.metrics
