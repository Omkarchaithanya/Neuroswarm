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


def test_speculative_from_tier1_registered() -> None:
    load_plugins()
    assert "speculative_from_tier1" in known_proposers()
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
