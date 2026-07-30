"""Verification strategies."""

from __future__ import annotations

import time
from typing import Any

from neuroswarm_arm.runtime.armcascade.confidence.engine import text_quality_score
from neuroswarm_arm.runtime.armcascade.interfaces.proposal import VerifierStrategy
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    Proposal,
    VerifyMode,
    VerifyRequest,
    VerifyResult,
    approx_tokens,
    build_messages,
)
from neuroswarm_arm.runtime.armcascade.proposal.registry import register_verifier


def _token_agreement(draft: str, verified: str) -> tuple[int, float]:
    d = draft.split()
    v = verified.split()
    if not d:
        return 0, 0.0
    n = 0
    for a, b in zip(d, v):
        if a == b:
            n += 1
        else:
            break
    return n, n / max(1, len(d))


class _BackendVerifierBase(VerifierStrategy):
    def __init__(self, backend_name: str = "tier2") -> None:
        self.backend_name = backend_name
        self._registry: Any = None
        self._ctx_exec: Any = None
        self._quality_cfg: dict[str, Any] = {}

    async def initialize(self, ctx: ASCRInitContext) -> None:
        self._registry = ctx.registry
        self._quality_cfg = dict((ctx.config or {}).get("confidence") or {})
        for t in (ctx.config or {}).get("tiers") or []:
            if isinstance(t, dict) and t.get("role") == "verify":
                self.backend_name = str(t.get("backend", self.backend_name))

    def bind_execution_context(self, exec_ctx: Any) -> None:
        self._ctx_exec = exec_ctx

    def set_backend(self, name: str) -> None:
        self.backend_name = name

    async def _generate(
        self,
        req: VerifyRequest,
        max_tokens: int,
        *,
        top_logprobs: int = 0,
    ) -> Any:
        from neuroswarm_arm.runtime.dipa.interfaces.types import GenerateRequest

        if self._registry is None:
            raise RuntimeError(f"{self.name} not initialized")
        backend = self._registry.require(self.backend_name)
        messages = build_messages(req.messages)
        if top_logprobs > 0 and hasattr(backend, "generate_with_logits"):
            return await backend.generate_with_logits(
                messages=messages,
                max_tokens=max(1, int(max_tokens)),
                temperature=float(req.temperature),
                top_logprobs=int(top_logprobs),
                session_id=req.session_id,
                quant=req.quant,
                kv_handle=req.kv_handle,
                ctx=self._ctx_exec,
            )
        gen = GenerateRequest(
            messages=messages,
            max_tokens=max(1, int(max_tokens)),
            temperature=float(req.temperature),
            session_id=req.session_id,
            quant=req.quant,
            stream=False,
            kv_handle=req.kv_handle,
            speculative=True,
        )
        return await backend.generate(gen, self._ctx_exec)


@register_verifier("block")
class BlockVerifier(_BackendVerifierBase):
    """Block verification: one target generate; agree on longest prefix."""

    name = "block"

    async def verify(self, draft: Proposal, req: VerifyRequest) -> VerifyResult:
        t0 = time.monotonic()
        draft_len = max(1, draft.draft_len or approx_tokens(draft.text))
        result = await self._generate(req, max_tokens=draft_len)
        text = result.text or ""
        prefix_len, agreement = _token_agreement(draft.text, text)
        quality = text_quality_score(text, self._quality_cfg)
        entropy = float(result.metrics.get("entropy", 1.0 - agreement))
        elapsed = (time.monotonic() - t0) * 1000.0
        return VerifyResult(
            accepted_prefix_len=prefix_len,
            rejected=prefix_len == 0,
            agreement=agreement,
            entropy=entropy,
            text=text,
            mode=VerifyMode.BLOCK,
            logits_available=False,
            quality_score=quality,
            latency_ms=result.latency_ms or elapsed,
            backend=result.backend or self.backend_name,
            model=result.model,
            tier_used=req.verifier_tier,
            metrics={
                "draft_len": float(draft_len),
                "prefix_len": float(prefix_len),
                "agreement": agreement,
                "accept_mode": 0.0,
            },
            raw=dict(result.raw),
        )


def _raw_has_logprobs(raw: dict[str, Any]) -> bool:
    choices = raw.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return False
    c0 = choices[0]
    if c0.get("logprobs") or c0.get("completion_probabilities") or c0.get("probs"):
        return True
    return False


@register_verifier("single_token")
class SingleTokenVerifier(BlockVerifier):
    name = "single_token"

    async def verify(self, draft: Proposal, req: VerifyRequest) -> VerifyResult:
        first = draft.tokens[0].text if draft.tokens else (
            draft.text.split()[0] if draft.text.split() else ""
        )
        slim = Proposal.from_text(
            first,
            strategy=draft.strategy,
            source_tier=draft.source_tier,
            confidence=draft.confidence,
        )
        out = await super().verify(slim, req)
        out.mode = VerifyMode.SINGLE
        return out


@register_verifier("batched")
class BatchedVerifier(BlockVerifier):
    name = "batched"

    async def verify(self, draft: Proposal, req: VerifyRequest) -> VerifyResult:
        # Parallelism approximated by one block pass sized to batch*draft;
        # true parallel verify needs multi-slot backends.
        batch = max(1, int(req.batch_size))
        req.batch_size = batch
        out = await super().verify(draft, req)
        out.mode = VerifyMode.BATCHED
        out.metrics["batch_size"] = float(batch)
        return out


@register_verifier("quality")
class QualityVerifier(VerifierStrategy):
    """Quality-cascade verifier: score draft text heuristically (no target forward)."""

    name = "quality"

    def __init__(self) -> None:
        self._quality_cfg: dict[str, Any] = {}

    async def initialize(self, ctx: ASCRInitContext) -> None:
        self._quality_cfg = dict((ctx.config or {}).get("confidence") or {})

    async def verify(self, draft: Proposal, req: VerifyRequest) -> VerifyResult:
        quality = text_quality_score(draft.text, self._quality_cfg)
        accepted = draft.draft_len if quality >= req.accept_threshold else 0
        return VerifyResult(
            accepted_prefix_len=accepted,
            rejected=accepted == 0,
            agreement=quality,
            entropy=1.0 - quality,
            text=draft.text,
            mode=VerifyMode.QUALITY,
            logits_available=False,
            quality_score=quality,
            latency_ms=0.0,
            tier_used=req.verifier_tier,
            metrics={"quality": quality},
        )
