"""Backend-backed draft-model proposer (Tier 1)."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import ProposalStrategy
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    Proposal,
    ProposalRequest,
    approx_tokens,
    build_messages,
)
from neuroswarm_arm.runtime.armcascade.proposal.registry import register_proposer


@register_proposer("draft_model")
class DraftModelProposer(ProposalStrategy):
    name = "draft_model"

    def __init__(self, backend_name: str = "tier1") -> None:
        self.backend_name = backend_name
        self._registry: Any = None
        self._ctx_exec: Any = None

    async def initialize(self, ctx: ASCRInitContext) -> None:
        self._registry = ctx.registry
        cfg = dict(ctx.config or {})
        for t in cfg.get("tiers") or []:
            if isinstance(t, dict) and t.get("role") == "draft":
                self.backend_name = str(t.get("backend", self.backend_name))

    def bind_execution_context(self, exec_ctx: Any) -> None:
        self._ctx_exec = exec_ctx

    async def propose(self, req: ProposalRequest) -> Proposal:
        from neuroswarm_arm.runtime.dipa.interfaces.types import GenerateRequest

        if self._registry is None:
            raise RuntimeError("DraftModelProposer not initialized")
        backend = self._registry.require(self.backend_name)
        messages = build_messages(req.messages)
        gen = GenerateRequest(
            messages=messages,
            max_tokens=max(1, int(req.draft_len)),
            temperature=float(req.temperature),
            session_id=req.session_id,
            quant=req.quant,
            stream=False,
            kv_handle=req.kv_handle,
            speculative=True,
        )
        result = await backend.generate(gen, self._ctx_exec)
        text = result.text or ""
        conf = 0.6
        if result.metrics.get("confidence") is not None:
            conf = float(result.metrics["confidence"])
        proposal = Proposal.from_text(
            text,
            strategy=self.name,
            source_tier=1,
            confidence=conf,
            metadata={
                "backend": result.backend or self.backend_name,
                "model": result.model,
                "latency_ms": result.latency_ms,
                "prompt_tokens": result.prompt_tokens or approx_tokens(req.prompt_text),
            },
        )
        return proposal

    def estimate_confidence(self, proposal: Proposal) -> float:
        if proposal.draft_len <= 0:
            return 0.0
        return float(proposal.confidence or 0.5)

