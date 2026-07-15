"""N-gram self-speculation proposer (no draft model)."""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import ProposalStrategy
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    Proposal,
    ProposalRequest,
)
from neuroswarm_arm.runtime.armcascade.proposal.registry import register_proposer


@register_proposer("self_speculation")
class SelfSpeculationProposer(ProposalStrategy):
    name = "self_speculation"

    def __init__(
        self,
        *,
        ngram_size: int = 24,
        draft_min: int = 4,
        draft_max: int = 48,
    ) -> None:
        self.ngram_size = ngram_size
        self.draft_min = draft_min
        self.draft_max = draft_max

    async def initialize(self, ctx: ASCRInitContext) -> None:
        strategies = dict((ctx.config or {}).get("strategies") or {})
        body = dict(strategies.get("self_speculation") or {})
        if body:
            self.ngram_size = int(body.get("ngram_size", self.ngram_size))
            self.draft_min = int(body.get("draft_min", self.draft_min))
            self.draft_max = int(body.get("draft_max", self.draft_max))

    async def propose(self, req: ProposalRequest) -> Proposal:
        text = req.prompt_text or ""
        words = text.split()
        draft_len = max(self.draft_min, min(self.draft_max, int(req.draft_len)))
        if len(words) < self.draft_min:
            return Proposal.from_text(
                "",
                strategy=self.name,
                confidence=0.0,
                metadata={"reason": "prompt_too_short"},
            )
        n = min(self.ngram_size, len(words))
        seed = words[-n:]
        draft_tokens: list[str] = []
        while len(draft_tokens) < draft_len:
            remaining = draft_len - len(draft_tokens)
            draft_tokens.extend(seed[:remaining])
            if remaining <= len(seed):
                break
        draft = " ".join(draft_tokens)
        # Confidence rises with longer prompt history (more stable n-gram).
        conf = min(0.9, 0.4 + 0.01 * min(50, len(words)))
        return Proposal.from_text(
            draft,
            strategy=self.name,
            source_tier=1,
            confidence=conf,
            metadata={"ngram_size": n, "seed_len": len(seed)},
        )

    def estimate_confidence(self, proposal: Proposal) -> float:
        return float(proposal.confidence)


@register_proposer("ngram")
class NgramProposer(SelfSpeculationProposer):
    name = "ngram"

    async def initialize(self, ctx: ASCRInitContext) -> None:
        strategies = dict((ctx.config or {}).get("strategies") or {})
        body = dict(strategies.get("ngram") or {})
        if body.get("ngram_size"):
            self.ngram_size = int(body["ngram_size"])
        await super().initialize(ctx)


@register_proposer("suffix")
class SuffixProposer(ProposalStrategy):
    """Suffix speculation: repeat trailing suffix as draft (agent boilerplate)."""

    name = "suffix"

    async def initialize(self, ctx: ASCRInitContext) -> None:
        return None

    async def propose(self, req: ProposalRequest) -> Proposal:
        words = (req.prompt_text or "").split()
        k = max(1, min(int(req.draft_len), 16, max(1, len(words))))
        if not words:
            return Proposal.from_text("", strategy=self.name, confidence=0.0)
        suffix = words[-k:]
        draft = " ".join(suffix)
        return Proposal.from_text(
            draft,
            strategy=self.name,
            confidence=0.45,
            metadata={"suffix_len": k},
        )
