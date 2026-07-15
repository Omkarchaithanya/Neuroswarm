"""Stub proposers for future speculative algorithms."""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import ProposalStrategy
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    Proposal,
    ProposalRequest,
)
from neuroswarm_arm.runtime.armcascade.proposal.registry import register_proposer


class _StubProposer(ProposalStrategy):
    stub_reason: str = "stub"

    async def initialize(self, ctx: ASCRInitContext) -> None:
        return None

    async def propose(self, req: ProposalRequest) -> Proposal:
        raise NotImplementedError(
            f"{self.name} not implemented yet ({self.stub_reason}). "
            "Register weights/config and replace stub."
        )


@register_proposer("eagle")
class EagleProposer(_StubProposer):
    name = "eagle"
    stub_reason = "needs trained EAGLE draft head"


@register_proposer("eagle3")
class Eagle3Proposer(_StubProposer):
    name = "eagle3"
    stub_reason = "needs EAGLE-3 draft head + ARM port"


@register_proposer("medusa")
class MedusaProposer(_StubProposer):
    name = "medusa"
    stub_reason = "needs Medusa multi-head weights"


@register_proposer("pard")
class PardProposer(_StubProposer):
    name = "pard"
    stub_reason = "PARD parallel draft not wired"
