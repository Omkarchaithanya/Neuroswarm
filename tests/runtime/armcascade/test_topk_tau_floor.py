"""G14: top-τ floor when draft token missing from target top-N."""

from __future__ import annotations

import math
from typing import Any

from neuroswarm_arm.runtime.armcascade.interfaces.types import Proposal, ProposalToken
from neuroswarm_arm.runtime.armcascade.verification.logits_verifier import (
    leviathan_accept,
    parse_logits_bundle,
)


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
) -> Proposal:
    pts = [
        ProposalToken(text=t, token_id=pid, logprob=lp, rank=rank)
        for t, pid, lp, rank in tokens
    ]
    text = " ".join(t for t, _, _, _ in tokens)
    return Proposal(
        tokens=pts,
        text=text,
        strategy="draft_model",
        draft_len=len(pts),
        confidence=0.7,
        source_tier=1,
    )


def _bundle_draft_not_in_topn(*, p_draft: float = 0.85):
    """Draft token absent from target top-N; draft mass = p_draft."""
    draft_lp = math.log(p_draft)
    draft = _proposal_from_ids([("draft_only", 50, draft_lp, 9)])
    raw = _raw_openai_logprobs(
        [
            (
                "target",
                [("target", -0.1, 1), ("other", -1.0, 2)],
            )
        ]
    )
    return parse_logits_bundle(raw, draft, top_n=2)


def test_tau_floor_accepts_when_p_draft_above_floor() -> None:
    bundle = _bundle_draft_not_in_topn(p_draft=0.85)
    out = leviathan_accept(bundle, greedy=True, tau_floor=0.8)
    assert out.accepted_prefix_len == 1
    assert out.top_tau_used
    assert out.bonus_token == "target"


def test_tau_floor_rejects_when_p_draft_below_floor() -> None:
    bundle = _bundle_draft_not_in_topn(p_draft=0.85)
    out = leviathan_accept(bundle, greedy=True, tau_floor=0.9)
    assert out.accepted_prefix_len == 0
    assert not out.top_tau_used


def test_tau_floor_zero_is_lossless_reject() -> None:
    """tau_floor=0 (default) never accepts missing-from-top-N tokens."""
    bundle = _bundle_draft_not_in_topn(p_draft=0.99)
    out = leviathan_accept(bundle, greedy=True, tau_floor=0.0)
    assert out.accepted_prefix_len == 0
    assert not out.top_tau_used
