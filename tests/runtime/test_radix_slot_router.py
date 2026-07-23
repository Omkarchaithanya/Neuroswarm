"""Tests for RadixSlotRouter prefix-aware slot reuse."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from neuroswarm_arm.runtime.dipa.backends.llama_cpp.backend import (
    LlamaCppBackend,
    _llama_chat_extra,
)
from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.dipa.interfaces.types import GenerateRequest, InferenceRequest
from neuroswarm_arm.runtime.radix_slot_router import RadixSlotRouter
from neuroswarm_arm.runtime.slot_registry import SlotRegistry


def _shared_prefix_tokens(n: int = 200) -> list[int]:
    return list(range(n))


def test_match_longest_prefix_requires_min_match() -> None:
    router = RadixSlotRouter(registry=SlotRegistry(total_slots=4), min_match=64)
    prefix = _shared_prefix_tokens(200)
    router.insert(prefix, id_slot=2)
    slot, matched = router.match_longest_prefix(prefix + [999, 1000])
    assert slot == 2
    assert matched == 200


def test_two_sessions_share_prefix_slot() -> None:
    router = RadixSlotRouter(registry=SlotRegistry(total_slots=4), min_match=64)
    prefix = _shared_prefix_tokens(200)
    suffix_a = [1001, 1002, 1003]
    suffix_b = [2001, 2002]

    payload_a, meta_a = router.prepare_payload(
        "sess-a",
        "prompt-a",
        {},
        token_ids=prefix + suffix_a,
    )
    assert payload_a["cache_prompt"] is True
    slot_a = payload_a["id_slot"]

    payload_b, meta_b = router.prepare_payload(
        "sess-b",
        "prompt-b",
        {},
        token_ids=prefix + suffix_b,
    )
    assert payload_b["cache_prompt"] is True
    assert payload_b["id_slot"] == slot_a
    assert meta_b.get("radix_match_len", 0) >= 64


@pytest.mark.asyncio
async def test_backend_two_sessions_same_id_slot_in_http_payload() -> None:
    prefix = _shared_prefix_tokens(200)
    suffix_a = [11, 12]
    suffix_b = [21, 22]

    backend = LlamaCppBackend(name="tier2", base_url="http://127.0.0.1:8080", tier=2)
    registry = SlotRegistry(total_slots=4)
    router = RadixSlotRouter(registry=registry, min_match=64)
    backend._slot_router = router
    backend._client = MagicMock()

    def fake_tokenize(text: str) -> list[int]:
        if "suffix-a" in text:
            return prefix + suffix_a
        if "suffix-b" in text:
            return prefix + suffix_b
        return prefix

    backend.tokenize = fake_tokenize  # type: ignore[method-assign]
    backend._client.chat.return_value = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 202, "completion_tokens": 1},
        "id_slot": 0,
    }

    ctx = ExecutionContext(
        request=InferenceRequest(messages=[{"role": "user", "content": "x"}]),
    )
    await backend.generate(
        GenerateRequest(
            messages=[{"role": "user", "content": "shared suffix-a"}],
            session_id="sess-a",
        ),
        ctx,
    )
    first_extra = backend._client.chat.call_args.kwargs["extra"]

    await backend.generate(
        GenerateRequest(
            messages=[{"role": "user", "content": "shared suffix-b"}],
            session_id="sess-b",
        ),
        ctx,
    )
    second_extra = backend._client.chat.call_args.kwargs["extra"]

    assert first_extra["cache_prompt"] is True
    assert second_extra["cache_prompt"] is True
    assert second_extra["id_slot"] == first_extra["id_slot"]
    assert router.metrics.snapshot()["radix_prefix_hit_total"] >= 1


def test_llama_chat_extra_with_radix_router() -> None:
    router = RadixSlotRouter(registry=SlotRegistry(total_slots=4), min_match=64)
    prefix = _shared_prefix_tokens(200)
    router.insert(prefix, id_slot=1)
    extra, meta = _llama_chat_extra(
        session_id="s2",
        messages=[{"role": "user", "content": "hello"}],
        slot_router=router,
        tokenize_fn=lambda _: prefix + [99],
    )
    assert extra["id_slot"] == 1
    assert extra["cache_prompt"] is True
    assert meta["radix_match_len"] >= 64
