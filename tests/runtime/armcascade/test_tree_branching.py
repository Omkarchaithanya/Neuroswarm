"""DraftModelProposer branching / TokenTree width bounds."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    ProposalRequest,
)
from neuroswarm_arm.runtime.armcascade.proposal.draft_model import DraftModelProposer
from neuroswarm_arm.runtime.armcascade.verification.tree import TokenTree


class _FakeResult:
    def __init__(self, text: str) -> None:
        self.text = text
        self.backend = "tier1"
        self.model = "fake-draft"
        self.latency_ms = 0.5
        self.raw: dict[str, Any] = {}
        self.metrics: dict[str, Any] = {}
        self.prompt_tokens = 1


class _FakeBackend:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, req: Any, ctx: Any = None) -> _FakeResult:
        self.calls += 1
        return _FakeResult(f"tok{self.calls}")


class _FakeRegistry:
    def __init__(self) -> None:
        self.backend = _FakeBackend()

    def require(self, name: str) -> Any:
        return self.backend


def _level_widths(tree: TokenTree) -> list[int]:
    if not tree.nodes:
        return []
    depths = [tree.node_depth(i) for i in range(tree.size)]
    max_d = max(depths)
    widths: list[int] = []
    for d in range(1, max_d + 1):
        widths.append(sum(1 for x in depths if x == d))
    return widths


def test_branching_4_width_and_leaf_bound() -> None:
    os.environ["NSA_ASCR_TREE_ENABLED"] = "1"

    async def _run() -> None:
        proposer = DraftModelProposer(backend_name="tier1")
        reg = _FakeRegistry()
        await proposer.initialize(
            ASCRInitContext(
                registry=reg,
                config={"strategies": {"tree": {"enabled": True}}},
            )
        )
        branching = 4
        depth = 3
        req = ProposalRequest(
            prompt_text="hello",
            messages=[{"role": "user", "content": "hello"}],
            draft_len=depth,
            max_tokens=depth,
            temperature=0.2,
            metadata={"branching": branching},
        )
        proposal = await proposer.propose(req)
        tree = proposal.tree
        assert isinstance(tree, TokenTree)
        assert tree.size > 0
        for w in _level_widths(tree):
            assert w <= branching
        for kids in tree.children:
            assert len(kids) <= branching
        assert tree.branches_total <= branching**depth

    asyncio.run(_run())


def test_branching_1_no_tree() -> None:
    os.environ["NSA_ASCR_TREE_ENABLED"] = "1"

    async def _run() -> None:
        proposer = DraftModelProposer(backend_name="tier1")
        reg = _FakeRegistry()
        await proposer.initialize(
            ASCRInitContext(
                registry=reg,
                config={"strategies": {"tree": {"enabled": True}}},
            )
        )
        req = ProposalRequest(
            prompt_text="hello",
            messages=[{"role": "user", "content": "hello"}],
            draft_len=4,
            max_tokens=4,
            temperature=0.2,
            metadata={"branching": 1},
        )
        proposal = await proposer.propose(req)
        assert proposal.tree is None
        assert proposal.text
        assert proposal.metadata.get("branching") == 1

    asyncio.run(_run())
