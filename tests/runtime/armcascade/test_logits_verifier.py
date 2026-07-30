"""Unit tests for Leviathan logits acceptance verifier."""

from __future__ import annotations

import asyncio
import math
import random
from typing import Any

from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    Proposal,
    ProposalToken,
    VerifyMode,
    VerifyRequest,
)
from neuroswarm_arm.runtime.armcascade.verification.logits_verifier import (
    LogitsAcceptanceVerifier,
    leviathan_accept,
    parse_logits_bundle,
)
from neuroswarm_arm.runtime.dipa.interfaces.types import GenerateResult


def _raw_openai_logprobs(
    steps: list[tuple[str, list[tuple[str, float, int | None]]]],
) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    for token, top in steps:
        content.append(
            {
                "token": token,
                "logprob": top[0][1],
                "top_logprobs": [
                    {
                        "token": t,
                        "logprob": lp,
                        **({"token_id": tid} if tid is not None else {}),
                    }
                    for t, lp, tid in top
                ],
            }
        )
    text = " ".join(s[0] for s in steps)
    return {
        "choices": [
            {
                "message": {"content": text},
                "logprobs": {"content": content},
            }
        ]
    }


def _proposal_from_ids(
    tokens: list[tuple[str, int, float, int]],
    *,
    strategy: str = "draft_model",
) -> Proposal:
    pts = [
        ProposalToken(text=t, token_id=pid, logprob=lp, rank=rank)
        for t, pid, lp, rank in tokens
    ]
    text = " ".join(t for t, _, _, _ in tokens)
    return Proposal(
        tokens=pts,
        text=text,
        strategy=strategy,
        draft_len=len(pts),
        confidence=0.7,
        source_tier=1,
    )


def test_greedy_accept_all_argmax_match() -> None:
    draft = _proposal_from_ids(
        [("alpha", 1, -0.1, 0), ("beta", 2, -0.2, 0), ("gamma", 3, -0.3, 0)]
    )
    raw = _raw_openai_logprobs(
        [
            ("alpha", [("alpha", -0.1, 1), ("other", -2.0, 99)]),
            ("beta", [("beta", -0.2, 2), ("other", -2.0, 99)]),
            ("gamma", [("gamma", -0.3, 3), ("other", -2.0, 99)]),
        ]
    )
    bundle = parse_logits_bundle(raw, draft, top_n=2)
    out = leviathan_accept(bundle, greedy=True)
    assert out.accepted_prefix_len == 3


def test_greedy_reject_at_position_two() -> None:
    draft = _proposal_from_ids(
        [("alpha", 1, -0.1, 0), ("beta", 2, -0.2, 0), ("gamma", 3, -0.3, 0)]
    )
    raw = _raw_openai_logprobs(
        [
            ("alpha", [("alpha", -0.1, 1), ("other", -2.0, 99)]),
            ("beta", [("beta", -0.2, 2), ("other", -2.0, 99)]),
            ("wrong", [("wrong", -0.1, 4), ("gamma", -0.3, 3)]),
        ]
    )
    bundle = parse_logits_bundle(raw, draft, top_n=2)
    out = leviathan_accept(bundle, greedy=True)
    assert out.accepted_prefix_len == 2


def test_stochastic_accept_distribution() -> None:
    draft = _proposal_from_ids([("tok", 10, -1.0, 0)])
    q, p = -0.5, -1.0
    expected = min(1.0, math.exp(q - p))
    raw = _raw_openai_logprobs([("tok", [("tok", q, 10), ("alt", -3.0, 11)])])
    bundle = parse_logits_bundle(raw, draft, top_n=2)
    rng = random.Random(42)
    trials = 10000
    accepts = sum(
        1
        for _ in range(trials)
        if leviathan_accept(bundle, greedy=False, rng=rng).accepted_prefix_len == 1
    )
    empirical = accepts / trials
    assert abs(empirical - expected) < 0.05


def test_top_tau_fallback_accepts() -> None:
    draft = _proposal_from_ids([("draft_only", 50, 0.0, 0)])
    raw = _raw_openai_logprobs(
        [
            (
                "target",
                [("target", -0.1, 1), ("other", -1.0, 2)],
            )
        ]
    )
    bundle = parse_logits_bundle(raw, draft, top_n=2)
    out = leviathan_accept(bundle, greedy=True, tau_floor=0.8)
    assert out.accepted_prefix_len == 1
    assert out.top_tau_used


def test_bonus_token_when_all_accepted() -> None:
    draft = _proposal_from_ids(
        [("a", 1, -0.1, 0), ("b", 2, -0.2, 0), ("c", 3, -0.3, 0)]
    )
    raw = _raw_openai_logprobs(
        [
            ("a", [("a", -0.1, 1), ("x", -2.0, 99)]),
            ("b", [("b", -0.2, 2), ("x", -2.0, 99)]),
            ("c", [("c", -0.3, 3), ("x", -2.0, 99)]),
            ("bonus", [("bonus", -0.1, 100), ("x", -2.0, 99)]),
        ]
    )
    bundle = parse_logits_bundle(raw, draft, top_n=2)
    out = leviathan_accept(bundle, greedy=True)
    assert out.accepted_prefix_len == 3
    assert out.bonus_token == "bonus"


class _LogitsMockBackend:
    def __init__(self) -> None:
        self.name = "tier2"
        self.tier = 2
        self.calls: list[dict[str, Any]] = []

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
        ctx: Any = None,
    ) -> GenerateResult:
        self.calls.append(
            {
                "max_tokens": max_tokens,
                "top_logprobs": top_logprobs,
                "temperature": temperature,
            }
        )
        raw = _raw_openai_logprobs(
            [
                ("yes", [("yes", -0.1, 1), ("no", -1.0, 2)]),
            ]
        )
        return GenerateResult(
            text="yes",
            backend=self.name,
            tier_used=self.tier,
            raw=raw,
            metrics={"logits_available": 1.0},
        )


class _Registry:
    def __init__(self, backend: _LogitsMockBackend) -> None:
        self._backend = backend

    def require(self, name: str) -> _LogitsMockBackend:
        return self._backend


def test_backend_generate_routes_to_logits_path() -> None:
    backend = _LogitsMockBackend()
    registry = _Registry(backend)
    logits_v = LogitsAcceptanceVerifier()
    asyncio.run(
        logits_v.initialize(
            ASCRInitContext(
                registry=registry,
                config={"strategies": {"logits": {"enabled": True}}},
            )
        )
    )
    req = VerifyRequest(
        messages=[{"role": "user", "content": "hi"}],
        prompt_text="hi",
        temperature=0.0,
    )
    draft = _proposal_from_ids([("yes", 1, -0.1, 0)])
    result = asyncio.run(logits_v.verify(draft, req))
    assert backend.calls
    assert backend.calls[0]["top_logprobs"] > 0
    assert result.logits_available
    assert result.mode == VerifyMode.LOGITS
    assert result.accepted_prefix_len == 1


def test_e2e_build_dipa_logits_strategy() -> None:
    from neuroswarm_arm.runtime.dipa import build_dipa
    from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest

    rt = build_dipa(use_mock=True, start=True)
    try:
        req = InferenceRequest(
            messages=[{"role": "user", "content": "hello logits verify"}],
            max_tokens=16,
            agent_role="tool_call",
        )
        resp = rt.infer(req)
        assert resp.text
    finally:
        rt.shutdown()
