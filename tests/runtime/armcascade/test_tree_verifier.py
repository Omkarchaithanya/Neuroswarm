"""Unit tests for SpecInfer TreeVerifier / TreeAcceptor."""

from __future__ import annotations

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
    leviathan_accept,
    parse_logits_bundle,
)
from neuroswarm_arm.runtime.armcascade.verification.stubs import TreeVerifier
from neuroswarm_arm.runtime.armcascade.verification.tree import (
    TokenTree,
    TreeAcceptor,
    TreeBuilder,
)


def _build_depth4_width2() -> TokenTree:
    """
    Depth-4 binary-ish tree.

    Primary path ids: 10 → 20 → 30 → 40
    Sibling distractors at each level: 11, 21, 31, 41
    """
    b = TreeBuilder()
    r = b.add_root(10, -0.1, "a")
    # depth 2
    d1 = b.extend(r, [20, 21], [-0.2, -1.5], ["b", "b2"])
    # depth 3 under primary
    d2 = b.extend(d1[0], [30, 31], [-0.3, -1.5], ["c", "c2"])
    # depth 4 under primary
    b.extend(d2[0], [40, 41], [-0.4, -1.5], ["d", "d2"])
    return b.build()


def test_greedy_three_of_four_match() -> None:
    tree = _build_depth4_width2()
    # Target argmax follows 10,20,30 then diverges (99) — prefix len 3
    target = [
        [(10, -0.05, "a"), (11, -2.0, "x")],
        [(20, -0.05, "b"), (21, -2.0, "x")],
        [(30, -0.05, "c"), (31, -2.0, "x")],
        [(99, -0.05, "z"), (40, -2.0, "d")],
        [(50, -0.1, "bonus")],
    ]
    out = TreeAcceptor().accept(tree, target, greedy=True)
    assert out.path.depth == 3
    assert out.path.token_ids == [10, 20, 30]


def test_stochastic_matches_leviathan_depth2() -> None:
    """Depth-2 chain: SpecInfer stochastic ratio == Leviathan min(1, exp(q-p))."""
    b = TreeBuilder()
    r = b.add_root(1, -1.0, "tok")
    b.extend(r, [2], [-1.0], ["tok2"])
    tree = b.build()

    q, p = -0.5, -1.0
    expected = min(1.0, math.exp(q - p))
    # Only first position matters for single-token Leviathan compare;
    # use depth-1 tree for fair 1-step match, then depth-2 both high-q.
    b1 = TreeBuilder()
    b1.add_root(1, p, "tok")
    tree1 = b1.build()
    target1 = [[(1, q, "tok"), (9, -3.0, "alt")]]

    draft = Proposal(
        tokens=[ProposalToken(text="tok", token_id=1, logprob=p, rank=0)],
        text="tok",
        strategy="draft_model",
        draft_len=1,
    )
    raw = {
        "choices": [
            {
                "message": {"content": "tok"},
                "logprobs": {
                    "content": [
                        {
                            "token": "tok",
                            "logprob": q,
                            "top_logprobs": [
                                {"token": "tok", "logprob": q, "token_id": 1},
                                {"token": "alt", "logprob": -3.0, "token_id": 9},
                            ],
                        }
                    ]
                },
            }
        ]
    }
    bundle = parse_logits_bundle(raw, draft, top_n=2)

    trials = 10000
    rng_a = random.Random(42)
    rng_b = random.Random(42)
    tree_hits = sum(
        1
        for _ in range(trials)
        if TreeAcceptor().accept(tree1, target1, greedy=False, rng=rng_a).path.depth == 1
    )
    lev_hits = sum(
        1
        for _ in range(trials)
        if leviathan_accept(bundle, greedy=False, rng=rng_b).accepted_prefix_len == 1
    )
    tree_rate = tree_hits / trials
    lev_rate = lev_hits / trials
    assert abs(tree_rate - expected) < 0.03
    assert abs(lev_rate - expected) < 0.03
    assert abs(tree_rate - lev_rate) < 0.02

    # Depth-2 tree: both positions same ratio; joint ≈ expected^2 under indep.
    target2 = [
        [(1, q, "tok"), (9, -3.0, "alt")],
        [(2, q, "tok2"), (9, -3.0, "alt")],
    ]
    rng = random.Random(7)
    hits2 = sum(
        1
        for _ in range(trials)
        if TreeAcceptor().accept(tree, target2, greedy=False, rng=rng).path.depth == 2
    )
    joint = hits2 / trials
    assert abs(joint - expected * expected) < 0.04


def test_no_matching_branches() -> None:
    tree = _build_depth4_width2()
    target = [
        [(99, -0.01, "z"), (98, -0.02, "y")],
        [(97, -0.01, "z"), (96, -0.02, "y")],
    ]
    out = TreeAcceptor().accept(tree, target, greedy=True)
    assert out.path.depth == 0


def test_all_match_bonus_top1() -> None:
    tree = _build_depth4_width2()
    target = [
        [(10, -0.05, "a"), (11, -2.0, "x")],
        [(20, -0.05, "b"), (21, -2.0, "x")],
        [(30, -0.05, "c"), (31, -2.0, "x")],
        [(40, -0.05, "d"), (41, -2.0, "x")],
        [(777, -0.01, "bonus_tok"), (778, -2.0, "other")],
    ]
    out = TreeAcceptor().accept(tree, target, greedy=True)
    assert out.path.depth == 4
    assert out.bonus == "bonus_tok"
    assert out.bonus_token_id == 777


class _FakeRegistry:
    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw

    def require(self, name: str) -> Any:
        return _FakeBackend(self._raw)


class _FakeResult:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.text = "a b c d bonus_tok"
        self.backend = "tier2"
        self.model = "fake"
        self.latency_ms = 1.0
        self.raw = raw
        self.metrics: dict[str, Any] = {}


class _FakeBackend:
    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw

    async def generate_with_logits(self, **kwargs: Any) -> _FakeResult:
        return _FakeResult(self._raw)


def test_tree_verifier_end_to_end() -> None:
    import asyncio
    import os

    tree = _build_depth4_width2()
    draft = Proposal(
        tokens=[
            ProposalToken(text="a", token_id=10, logprob=-0.1),
            ProposalToken(text="b", token_id=20, logprob=-0.2),
            ProposalToken(text="c", token_id=30, logprob=-0.3),
            ProposalToken(text="d", token_id=40, logprob=-0.4),
        ],
        text="a b c d",
        strategy="draft_model",
        draft_len=4,
        tree=tree,
    )
    content = []
    for tid, tok, lp in [
        (10, "a", -0.05),
        (20, "b", -0.05),
        (30, "c", -0.05),
        (99, "z", -0.05),
        (50, "bonus", -0.1),
    ]:
        content.append(
            {
                "token": tok,
                "logprob": lp,
                "token_id": tid,
                "top_logprobs": [
                    {"token": tok, "logprob": lp, "token_id": tid},
                    {"token": "x", "logprob": -2.0, "token_id": 0},
                ],
            }
        )
    raw = {
        "choices": [
            {
                "message": {"content": "a b c z bonus"},
                "logprobs": {"content": content},
            }
        ]
    }

    async def _run() -> None:
        v = TreeVerifier(backend_name="tier2")
        os.environ["NSA_ASCR_TREE_ENABLED"] = "1"
        await v.initialize(
            ASCRInitContext(
                registry=_FakeRegistry(raw),
                config={"strategies": {"tree": {"enabled": True}}},
            )
        )
        v._registry = _FakeRegistry(raw)
        req = VerifyRequest(
            messages=[{"role": "user", "content": "hi"}],
            prompt_text="hi",
            temperature=0.0,
        )
        result = await v.verify(draft, req)
        assert result.mode == VerifyMode.TREE
        assert result.accepted_prefix_len == 3
        assert result.metrics["tree_depth"] == 4.0
        assert "tree_width_avg" in result.metrics
        assert "tree_branches_total" in result.metrics

    asyncio.run(_run())
