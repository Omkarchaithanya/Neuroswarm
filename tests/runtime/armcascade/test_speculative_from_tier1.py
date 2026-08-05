"""Tests for the tier1-backed speculative proposer."""

from __future__ import annotations

import asyncio
from typing import Any

from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    ProposalRequest,
)
from neuroswarm_arm.runtime.armcascade.plugins import load_plugins
from neuroswarm_arm.runtime.armcascade.proposal.registry import (
    ProposalRegistry,
    known_proposers,
)
from neuroswarm_arm.runtime.dipa.interfaces.types import GenerateResult


class _FakeBackendRegistry:
    def __init__(self, backend: Any | None) -> None:
        self.backend = backend

    def get(self, name: str) -> Any | None:
        return self.backend if name == "tier1" else None


class _HealthyDraftBackend:
    def __init__(self) -> None:
        self.last_request: Any = None

    async def generate(self, req: Any, ctx: Any) -> GenerateResult:  # noqa: ARG002
        self.last_request = req
        return GenerateResult(
            text="alpha beta",
            backend="tier1",
            model="tiny-draft",
            raw={
                "choices": [
                    {
                        "logprobs": {
                            "content": [
                                {
                                    "token": "alpha",
                                    "token_id": 101,
                                    "logprob": -0.1,
                                },
                                {
                                    "token": "beta",
                                    "token_id": 102,
                                    "logprob": -0.2,
                                },
                            ]
                        }
                    }
                ]
            },
        )


class _FailingDraftBackend:
    async def generate(self, req: Any, ctx: Any) -> GenerateResult:  # noqa: ARG002
        raise RuntimeError("draft unavailable")


class _TargetBackend:
    def __init__(self) -> None:
        self.called = False
        self.last_temperature = 0.0

    async def generate_with_logits(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float,
        top_logprobs: int,
        session_id: str = "",
        quant: str = "",
        kv_handle: str | None = None,
        id_slot: int | None = None,
        ctx: Any = None,
    ) -> GenerateResult:
        self.called = True
        self.last_temperature = temperature
        assert messages == [{"role": "user", "content": "target prompt"}]
        assert max_tokens == 2
        assert top_logprobs >= 1
        return GenerateResult(
            text="gamma delta",
            backend="tier2",
            model="target",
            tier_used=2,
            raw={
                "choices": [
                    {
                        "logprobs": {
                            "content": [
                                {"token": "gamma", "token_id": 201, "logprob": -0.3},
                                {"token": "delta", "token_id": 202, "logprob": -0.4},
                            ]
                        }
                    }
                ]
            },
        )


def test_speculative_from_tier1_registered() -> None:
    load_plugins()
    assert "speculative_from_tier1" in known_proposers()
    assert "self_speculation" in known_proposers()
    assert "ngram" in known_proposers()
    assert ProposalRegistry().get("speculative_from_tier1").name == (
        "speculative_from_tier1"
    )


def test_speculative_from_tier1_proposes_tokens_with_logprobs() -> None:
    async def _run() -> None:
        load_plugins()
        backend = _HealthyDraftBackend()
        proposer = ProposalRegistry().get("speculative_from_tier1")
        await proposer.initialize(
            ASCRInitContext(registry=_FakeBackendRegistry(backend), config={})
        )
        proposal = await proposer.propose(
            ProposalRequest(
                prompt_text="complete this",
                messages=[{"role": "user", "content": "ignored"}],
                draft_len=2,
                max_tokens=2,
            )
        )
        assert proposal.strategy == "speculative_from_tier1"
        assert proposal.source_tier == 1
        assert proposal.text == "alpha beta"
        assert proposal.draft_len == 2
        assert [t.text for t in proposal.tokens] == ["alpha", "beta"]
        assert [t.token_id for t in proposal.tokens] == [101, 102]
        assert [t.logprob for t in proposal.tokens] == [-0.1, -0.2]
        assert backend.last_request.max_tokens == 2
        assert backend.last_request.messages == [
            {"role": "user", "content": "complete this"}
        ]

    asyncio.run(_run())


def test_self_speculation_uses_target_generate_with_logits() -> None:
    async def _run() -> None:
        load_plugins()
        backend = _TargetBackend()
        proposer = ProposalRegistry().get("self_speculation")
        await proposer.initialize(
            ASCRInitContext(
                registry=_FakeBackendRegistry(backend),
                config={
                    "strategies": {
                        "self_speculation": {
                            "target_backend_name": "tier1",
                            "temperature": 0.8,
                            "top_logprobs": 4,
                        }
                    }
                },
            )
        )
        proposal = await proposer.propose(
            ProposalRequest(
                prompt_text="target prompt",
                messages=[],
                draft_len=2,
                max_tokens=2,
                temperature=0.0,
            )
        )
        assert backend.called is True
        assert backend.last_temperature > 0.0
        assert proposal.strategy == "self_speculation"
        assert proposal.source_tier == 2
        assert proposal.text == "gamma delta"
        assert proposal.draft_len == 2
        assert [t.token_id for t in proposal.tokens] == [201, 202]
        assert [t.logprob for t in proposal.tokens] == [-0.3, -0.4]

    asyncio.run(_run())


def test_ngram_proposer_uses_prompt_text_only() -> None:
    async def _run() -> None:
        load_plugins()
        proposer = ProposalRegistry().get("ngram")
        await proposer.initialize(
            ASCRInitContext(config={"strategies": {"ngram": {"ngram_size": 2}}})
        )
        proposal = await proposer.propose(
            ProposalRequest(
                prompt_text="alpha beta one two alpha beta",
                messages=[],
                draft_len=2,
                max_tokens=2,
            )
        )
        assert proposal.strategy == "ngram"
        assert proposal.text == "one two"
        assert proposal.draft_len == 2
        assert proposal.confidence == 0.5
        assert [t.text for t in proposal.tokens] == ["one", "two"]
        assert all(t.logprob == 0.0 for t in proposal.tokens)

    asyncio.run(_run())


def test_speculative_from_tier1_returns_empty_on_failure() -> None:
    async def _run() -> None:
        load_plugins()
        proposer = ProposalRegistry().get("speculative_from_tier1")
        await proposer.initialize(
            ASCRInitContext(
                registry=_FakeBackendRegistry(_FailingDraftBackend()),
                config={},
            )
        )
        proposal = await proposer.propose(
            ProposalRequest(
                prompt_text="complete this",
                messages=[],
                draft_len=2,
                max_tokens=2,
            )
        )
        assert proposal.strategy == "speculative_from_tier1"
        assert proposal.tokens == []
        assert proposal.text == ""
        assert proposal.draft_len == 0

    asyncio.run(_run())
