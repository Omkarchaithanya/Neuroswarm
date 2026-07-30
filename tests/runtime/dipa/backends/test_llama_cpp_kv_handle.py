"""LlamaCppBackend forwards slot reuse fields into HTTP chat payload."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from neuroswarm_arm.runtime.dipa.backends.llama_cpp.backend import (
    LlamaCppBackend,
    _llama_chat_extra,
)
from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    DecodeRequest,
    GenerateRequest,
    InferenceRequest,
)
from neuroswarm_arm.runtime.slot_registry import SlotRegistry
from neuroswarm_arm.runtime.slot_router import SlotRouter


def test_llama_chat_extra_with_bound_slot() -> None:
    reg = SlotRegistry(total_slots=4)
    reg.acquire("sess-1")
    router = SlotRouter(registry=reg)
    extra, telemetry = _llama_chat_extra(
        session_id="sess-1",
        messages=[{"role": "user", "content": "hi"}],
        slot_router=router,
    )
    assert extra == {"cache_prompt": True, "id_slot": 0}
    assert telemetry["slot_reused"] is True
    assert telemetry["slot_id"] == 0


def test_llama_chat_extra_without_session() -> None:
    extra, telemetry = _llama_chat_extra(session_id="")
    assert extra == {"cache_prompt": True}
    assert telemetry["slot_reused"] is False


@pytest.mark.asyncio
async def test_generate_forwards_slot_fields_to_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "0")
    backend = LlamaCppBackend(name="tier1", base_url="http://127.0.0.1:8080", tier=1)
    backend._slot_router = SlotRouter(registry=SlotRegistry(total_slots=4))
    backend._client = MagicMock()
    backend._client.chat.return_value = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    backend._slot_router.registry.acquire("sess-x")
    req = GenerateRequest(
        messages=[{"role": "user", "content": "hi"}],
        session_id="sess-x",
        kv_handle="7",
    )
    ctx = ExecutionContext(
        request=InferenceRequest(messages=[{"role": "user", "content": "hi"}]),
    )
    result = await backend.generate(req, ctx)
    backend._client.chat.assert_called_once()
    kwargs = backend._client.chat.call_args.kwargs
    assert kwargs["extra"] == {"cache_prompt": True, "id_slot": 0}
    assert result.metrics["slot_id"] == 0.0
    assert result.metrics["slot_reused"] == 1.0
    assert result.metrics["ttft_seconds"] >= 0.0


@pytest.mark.asyncio
async def test_decode_forwards_slot_fields_to_http_client() -> None:
    backend = LlamaCppBackend(name="tier1", base_url="http://127.0.0.1:8080", tier=1)
    backend._slot_router = SlotRouter(registry=SlotRegistry(total_slots=4))
    backend._client = MagicMock()
    backend._client.chat_stream_raw.return_value = iter(["data: [DONE]\n"])
    backend._slot_router.registry.acquire("sess-y")

    req = DecodeRequest(
        messages=[{"role": "user", "content": "hi"}],
        session_id="sess-y",
        kv_handle="kv-y",
    )
    ctx = ExecutionContext(
        request=InferenceRequest(messages=[{"role": "user", "content": "hi"}]),
    )
    chunks = [c async for c in backend.decode(req, ctx)]
    backend._client.chat_stream_raw.assert_called_once()
    kwargs = backend._client.chat_stream_raw.call_args.kwargs
    assert kwargs["extra"] == {"cache_prompt": True, "id_slot": 0}
    assert chunks[-1].finished is True
