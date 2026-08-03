"""Verification strategies."""

from __future__ import annotations

import asyncio
import os
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
from neuroswarm_arm.runtime.dipa.backends.llama_cpp.slot_client import SlotKVError


def _env_slot_kv_reuse() -> bool:
    return os.getenv("NSA_LLAMA_SLOT_KV_REUSE", "1").strip() not in {
        "0",
        "false",
        "False",
        "no",
        "NO",
    }


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
        self._ascr_config: dict[str, Any] = {}

    async def initialize(self, ctx: ASCRInitContext) -> None:
        self._registry = ctx.registry
        self._ascr_config = dict(ctx.config or {})
        self._quality_cfg = dict(self._ascr_config.get("confidence") or {})
        for t in (self._ascr_config.get("tiers") or []):
            if isinstance(t, dict) and t.get("role") == "verify":
                self.backend_name = str(t.get("backend", self.backend_name))

    def bind_execution_context(self, exec_ctx: Any) -> None:
        self._ctx_exec = exec_ctx

    def set_backend(self, name: str) -> None:
        self.backend_name = name

    def _slot_kv_enabled(self) -> bool:
        strategies = dict(self._ascr_config.get("strategies") or {})
        flag = strategies.get("slot_kv_reuse") or {}
        if isinstance(flag, dict) and not flag.get("enabled", True):
            return False
        return _env_slot_kv_reuse()

    async def _generate(
        self,
        req: VerifyRequest,
        max_tokens: int,
        *,
        id_slot: int | None = None,
        top_logprobs: int = 0,
    ) -> Any:
        if self._registry is None:
            raise RuntimeError(f"{self.name} not initialized")
        backend = self._registry.require(self.backend_name)
        messages = build_messages(req.messages)
        effective_slot = id_slot if id_slot is not None else req.id_slot
        if top_logprobs > 0 and hasattr(backend, "generate_with_logits"):
            slots = getattr(backend, "_slots", None)
            slot_file: str | None = None
            if self._slot_kv_enabled() and req.kv_handle and slots is not None:
                slot_file = slots.resolve_filename(req.kv_handle)
                sid = int(effective_slot) if effective_slot is not None else 0
                try:
                    await asyncio.to_thread(slots.kv_import, sid, slot_file)
                except SlotKVError:
                    # Missing/incompatible KV → full prefill this round.
                    pass
            result = await backend.generate_with_logits(
                messages=messages,
                max_tokens=max(1, int(max_tokens)),
                temperature=float(req.temperature),
                top_logprobs=int(top_logprobs),
                session_id=req.session_id,
                quant=req.quant,
                kv_handle=req.kv_handle,
                id_slot=effective_slot,
                ctx=self._ctx_exec,
            )
            if self._slot_kv_enabled() and req.kv_handle and slots is not None and slot_file:
                sid = int(
                    result.metrics.get(
                        "slot_id", effective_slot if effective_slot is not None else 0
                    )
                )
                try:
                    await asyncio.to_thread(slots.kv_export, sid, slot_file)
                except SlotKVError:
                    # Export failure must not fail the verified generation.
                    pass
            return result
        from neuroswarm_arm.runtime.dipa.interfaces.types import GenerateRequest

        gen = GenerateRequest(
            messages=messages,
            max_tokens=max(1, int(max_tokens)),
            temperature=float(req.temperature),
            session_id=req.session_id,
            quant=req.quant,
            stream=False,
            kv_handle=req.kv_handle,
            id_slot=effective_slot,
            speculative=True,
        )
        slots = getattr(backend, "_slots", None)
        slot_file: str | None = None
        if self._slot_kv_enabled() and req.kv_handle and slots is not None:
            slot_file = slots.resolve_filename(req.kv_handle)
            sid = int(effective_slot) if effective_slot is not None else 0
            try:
                await asyncio.to_thread(slots.kv_import, sid, slot_file)
            except SlotKVError:
                # Missing/incompatible KV → full prefill this round.
                pass
        result = await backend.generate(gen, self._ctx_exec)
        if self._slot_kv_enabled() and req.kv_handle and slots is not None and slot_file:
            sid = int(
                result.metrics.get("slot_id", effective_slot if effective_slot is not None else 0)
            )
            try:
                await asyncio.to_thread(slots.kv_export, sid, slot_file)
            except SlotKVError:
                # Export failure must not fail the verified generation.
                pass
        return result


def _accept_prefix_from_logprobs(
    draft: str,
    verified: str,
    raw: dict[str, Any],
) -> tuple[int, float] | None:
    """When llama returns completion_probabilities, accept matching draft prefix."""
    choices = raw.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return None
    c0 = choices[0]
    probs = c0.get("completion_probabilities") or c0.get("probs")
    if not isinstance(probs, list) or not probs:
        return None
    draft_words = draft.split()
    if not draft_words:
        return None
    verified_words = verified.split()
    accepted = 0
    for i, entry in enumerate(probs):
        if i >= len(draft_words):
            break
        token_text = ""
        if isinstance(entry, dict):
            token_text = str(
                entry.get("token")
                or entry.get("text")
                or entry.get("content")
                or ""
            ).strip()
        elif isinstance(entry, str):
            token_text = entry.strip()
        if not token_text:
            if i < len(verified_words) and verified_words[i] == draft_words[i]:
                accepted += 1
                continue
            break
        if token_text == draft_words[i]:
            accepted += 1
        else:
            break
    if accepted == 0:
        return None
    agreement = accepted / max(1, len(draft_words))
    return accepted, agreement


@register_verifier("block")
class BlockVerifier(_BackendVerifierBase):
    """Block verification: one target generate; agree on longest prefix."""

    name = "block"

    async def verify(self, draft: Proposal, req: VerifyRequest) -> VerifyResult:
        t0 = time.monotonic()
        draft_len = max(1, draft.draft_len or approx_tokens(draft.text))
        result = await self._generate(req, max_tokens=draft_len, id_slot=req.id_slot)
        text = result.text or ""
        prefix_len, agreement = _token_agreement(draft.text, text)
        quality = text_quality_score(text, self._quality_cfg)
        # Block verifier is text-agreement only; ignore logprobs (honest proxy).
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
