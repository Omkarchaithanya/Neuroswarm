"""Unit tests for Layer-1 speculative decode wiring (n_probs + ASR metrics)."""

from __future__ import annotations

import json
from typing import Any

import pytest

import neuroswarm_arm.runtime.dipa.backends.llama_cpp.backend as llama_backend
from neuroswarm_arm.runtime.armcascade.interfaces.types import Proposal
from neuroswarm_arm.runtime.dipa.backends.llama_cpp.backend import (
    ASR_METRICS,
    LlamaCppBackend,
)
from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    GenerateRequest,
    HealthState,
    InferenceRequest,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._raw = json.dumps(payload).encode("utf-8")
        self.status = 200
        self.headers = {"Content-Type": "application/json"}

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        request=InferenceRequest(messages=[{"role": "user", "content": "hi"}]),
    )


def _patch_urlopen(monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]) -> None:
    """Monkey-patch urllib.request.urlopen used by LlamaHttpClient._post."""

    def fake_urlopen(req: Any, timeout: float = 0) -> _FakeResponse:  # noqa: ARG001
        url = str(getattr(req, "full_url", None) or getattr(req, "get_full_url", lambda: "")())
        body = getattr(req, "data", None)
        if body:
            parsed = json.loads(body.decode("utf-8"))
            if "chat/completions" in url or "messages" in parsed:
                captured["body"] = parsed
            elif "body" not in captured:
                captured["body"] = parsed
            if "tokenize" in url:
                return _FakeResponse({"tokens": [1, 2]})
        return _FakeResponse(
            {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            }
        )

    monkeypatch.setattr(llama_backend.request, "urlopen", fake_urlopen)


@pytest.fixture(autouse=True)
def _reset_asr_metrics() -> Any:
    ASR_METRICS.reset()
    yield
    ASR_METRICS.reset()


@pytest.mark.asyncio
async def test_chat_includes_n_probs_when_spec_url_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NSA_TIER_SPEC_URL", "http://tier-spec:8080")
    monkeypatch.setenv("NSA_LLAMA_N_PROBS", "0")
    monkeypatch.setenv("NSA_LLAMA_N_PROBS_DEFAULT", "5")
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "0")

    captured: dict[str, Any] = {}
    _patch_urlopen(monkeypatch, captured)

    backend = LlamaCppBackend(name="tier2", base_url="http://127.0.0.1:8082", tier=2)
    assert backend._spec_url == "http://tier-spec:8080"
    await backend.generate(
        GenerateRequest(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=8,
            temperature=0.1,
        ),
        _ctx(),
    )
    assert captured.get("body", {}).get("n_probs") == 5


@pytest.mark.asyncio
async def test_accepted_tokens_increment_only_when_verifier_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NSA_TIER_SPEC_URL", "http://tier-spec:8080")
    ASR_METRICS.reset()
    backend = LlamaCppBackend(name="tier2", base_url="http://127.0.0.1:8082", tier=2)
    draft = Proposal.from_text("hello world", strategy="draft_model")
    n = len(draft.tokens)

    backend.record_spec_verify(draft, accepted=False)
    assert ASR_METRICS.get("asr_accepted_tokens_total") == 0.0
    assert ASR_METRICS.get("asr_draft_tokens_total") == float(n)
    assert ASR_METRICS.get("asr_verify_calls_total") == 1.0

    backend.record_spec_verify(draft, accepted=True)
    assert ASR_METRICS.get("asr_accepted_tokens_total") == float(n)
    assert ASR_METRICS.get("asr_verify_calls_total") == 2.0


@pytest.mark.asyncio
async def test_empty_spec_url_falls_back_without_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NSA_TIER_SPEC_URL", raising=False)
    monkeypatch.setenv("NSA_LLAMA_N_PROBS", "0")
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "0")
    ASR_METRICS.reset()

    captured: dict[str, Any] = {}
    _patch_urlopen(monkeypatch, captured)

    backend = LlamaCppBackend(name="tier2", base_url="http://127.0.0.1:8082", tier=2)
    assert backend._spec_url == ""
    before = ASR_METRICS.snapshot()
    await backend.generate(
        GenerateRequest(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=8,
            temperature=0.1,
        ),
        _ctx(),
    )
    draft = Proposal.from_text("hello world", strategy="draft_model")
    backend.record_spec_verify(draft, accepted=True)
    assert ASR_METRICS.snapshot() == before
    assert "n_probs" not in (captured.get("body") or {})


@pytest.mark.asyncio
async def test_draft_url_enables_capabilities_and_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NSA_TIER_SPEC_URL", raising=False)
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "0")
    monkeypatch.setattr(
        llama_backend.LlamaHttpClient,
        "is_ready",
        lambda self: self.base_url == "http://127.0.0.1:9081",
    )

    backend = LlamaCppBackend(
        name="tier2",
        base_url="http://127.0.0.1:8082",
        draft_base_url="http://127.0.0.1:9081",
    )

    assert backend.capabilities.speculation is True
    assert backend.capabilities.self_speculation is True
    assert backend._draft_client is not None
    status = await backend.draft_health()
    assert status.state == HealthState.HEALTHY


@pytest.mark.asyncio
async def test_no_draft_url_is_backward_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NSA_TIER_SPEC_URL", raising=False)
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "0")

    backend = LlamaCppBackend(name="tier2", base_url="http://127.0.0.1:8082")

    assert backend.capabilities.speculation is False
    assert backend._draft_client is None
    status = await backend.draft_health()
    assert status.state == HealthState.UNKNOWN


@pytest.mark.asyncio
async def test_generate_with_logits_stream_records_asr_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NSA_TIER_SPEC_URL", raising=False)
    monkeypatch.setenv("NSA_LLAMA_SLOT_KV_REUSE", "0")
    backend = LlamaCppBackend(
        name="tier2",
        base_url="http://127.0.0.1:8082",
        draft_base_url="http://127.0.0.1:9081",
    )

    def fake_stream(self: Any, *args: Any, **kwargs: Any) -> list[str]:  # noqa: ARG001
        payload = {
            "choices": [
                {
                    "logprobs": {
                        "content": [
                            {
                                "token": "hello",
                                "logprob": 0.0,
                                "top_logprobs": [
                                    {"token": "hello", "logprob": 0.0}
                                ],
                            }
                        ]
                    }
                }
            ]
        }
        return [f"data: {json.dumps(payload)}", "data: [DONE]"]

    monkeypatch.setattr(
        llama_backend.LlamaHttpClient,
        "generate_with_logits_stream",
        fake_stream,
    )
    draft = Proposal.from_text("hello", strategy="draft_model")

    chunks = [
        chunk
        async for chunk in backend.generate_with_logits_stream(
            [{"role": "user", "content": "hi"}],
            max_tokens=2,
            temperature=0.0,
            draft=draft,
        )
    ]

    assert any(chunk.text == "hello" for chunk in chunks)
    assert ASR_METRICS.get("asr_draft_tokens_total") == 1.0
    assert ASR_METRICS.get("asr_verify_calls_total") == 1.0
    assert ASR_METRICS.get("asr_accepted_tokens_total") == 1.0
