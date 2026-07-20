"""LlamaCppBackend forwards slot reuse fields into HTTP chat payload."""

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
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    DecodeRequest,
    GenerateRequest,
    InferenceRequest,
)


def test_llama_chat_extra_with_bound_slot() -> None:
    reg = SlotRegistry()
    reg.bind("sess-1", 42, "http://127.0.0.1:8080")
    router = SlotRouter(registry=reg, tier_url="http://127.0.0.1:8080")
    extra = _llama_chat_extra(
        session_id="sess-1",
        slot_router=router,
        tier_url="http://127.0.0.1:8080",
    )
    assert extra == {"cache_prompt": True, "id_slot": 42}


def test_llama_chat_extra_without_session() -> None:
    extra = _llama_chat_extra(session_id="")
    assert extra == {"cache_prompt": True}


@pytest.mark.asyncio
async def test_generate_forwards_slot_fields_to_http_client() -> None:
    backend = LlamaCppBackend(name="tier1", base_url="http://127.0.0.1:8080", tier=1)
    backend._client = MagicMock()
    backend._client.chat.return_value = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    backend._slot_router._registry.bind("sess-x", 7, "http://127.0.0.1:8080")
    req = GenerateRequest(
        messages=[{"role": "user", "content": "hi"}],
        session_id="sess-x",
        kv_handle="7",
    )
    ctx = ExecutionContext(
        request=InferenceRequest(messages=[{"role": "user", "content": "hi"}]),
    )
    await backend.generate(req, ctx)
    backend._client.chat.assert_called_once()
    kwargs = backend._client.chat.call_args.kwargs
    assert kwargs["extra"] == {"cache_prompt": True, "id_slot": 7}


@pytest.mark.asyncio
async def test_decode_forwards_slot_fields_to_http_client() -> None:
    backend = LlamaCppBackend(name="tier1", base_url="http://127.0.0.1:8080", tier=1)
    backend._client = MagicMock()
    backend._client.chat_stream_raw.return_value = iter(["data: [DONE]\n"])
    backend._slot_router._registry.bind("sess-y", 1, "http://127.0.0.1:8080")

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
    assert kwargs["extra"] == {"cache_prompt": True, "id_slot": 1}
    assert chunks[-1].finished is True
