"""Stub verifiers for hierarchical / tree modes."""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import VerifierStrategy
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    Proposal,
    VerifyRequest,
    VerifyResult,
)
from neuroswarm_arm.runtime.armcascade.proposal.registry import register_verifier


@register_verifier("hierarchical")
class HierarchicalVerifier(VerifierStrategy):
    name = "hierarchical"

    async def initialize(self, ctx: ASCRInitContext) -> None:
        return None

    async def verify(self, draft: Proposal, req: VerifyRequest) -> VerifyResult:
        raise NotImplementedError(
            "hierarchical verification stub — needs multi-tier logits path"
        )


@register_verifier("tree")
class TreeVerifier(VerifierStrategy):
    name = "tree"

    async def initialize(self, ctx: ASCRInitContext) -> None:
        return None

    async def verify(self, draft: Proposal, req: VerifyRequest) -> VerifyResult:
        raise NotImplementedError(
            "tree verification stub — needs branching draft + logits"
        )
