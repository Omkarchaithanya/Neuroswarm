"""Additional backend-backed proposal strategies."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import ProposalStrategy
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    Proposal,
    ProposalRequest,
    ProposalToken,
)
from neuroswarm_arm.runtime.armcascade.proposal.registry import register_proposer


@register_proposer("speculative_from_tier1")
class SpeculativeFromTier1Proposer(ProposalStrategy):
    """Generate draft tokens from the tier1 backend for target verification."""

    name = "speculative_from_tier1"

    def __init__(self, draft_backend_name: str = "tier1") -> None:
        self.draft_backend_name = draft_backend_name
        self._draft_backend: Any = None
        self._ctx_exec: Any = None

    async def initialize(self, ctx: ASCRInitContext) -> None:
        self._ctx_exec = ctx
        cfg = dict(ctx.config or {})
        strategies = dict(cfg.get("strategies") or {})
        strat_cfg = dict(strategies.get(self.name) or {})
        self.draft_backend_name = str(
            strat_cfg.get("draft_backend_name")
            or strat_cfg.get("backend")
            or cfg.get("draft_backend_name")
            or self.draft_backend_name
        )
        registry = ctx.registry
        if registry is None:
            self._draft_backend = None
            return
        try:
            self._draft_backend = registry.get(self.draft_backend_name)
        except Exception:
            self._draft_backend = None
        if self._draft_backend is None and self.draft_backend_name != "tier1":
            try:
                self._draft_backend = registry.get("tier1")
                self.draft_backend_name = "tier1"
            except Exception:
                self._draft_backend = None

    async def propose(self, req: ProposalRequest) -> Proposal:
        if self._draft_backend is None:
            return _empty_proposal(self.name)
        try:
            gen_req = _make_generate_request(req)
            result = await self._draft_backend.generate(gen_req, self._ctx_exec)
            text = str(getattr(result, "text", "") or "")
            if not text.strip():
                return _empty_proposal(self.name)
            tokens = _tokens_from_result(result, text, self._draft_backend)
            if not tokens:
                return _empty_proposal(self.name)
            metrics = getattr(result, "metrics", None) or {}
            raw = getattr(result, "raw", None) or {}
            confidence = float(metrics.get("confidence", 0.6) or 0.6)
            return Proposal(
                tokens=tokens,
                text=text,
                strategy=self.name,
                draft_len=len(tokens),
                confidence=confidence,
                source_tier=1,
                metadata={
                    "backend": getattr(result, "backend", "") or self.draft_backend_name,
                    "model": getattr(result, "model", ""),
                    "latency_ms": float(getattr(result, "latency_ms", 0.0) or 0.0),
                    "raw_has_logprobs": bool(raw),
                },
            )
        except Exception:
            return _empty_proposal(self.name)


@register_proposer("self_speculation")
class SelfSpeculationProposer(ProposalStrategy):
    """Use the target backend itself to draft a short speculative suffix."""

    name = "self_speculation"

    def __init__(self, target_backend_name: str = "tier2") -> None:
        self.target_backend_name = target_backend_name
        self._target_backend: Any = None
        self._ctx_exec: Any = None
        self._top_logprobs = 5
        self._temperature = 0.7

    async def initialize(self, ctx: ASCRInitContext) -> None:
        self._ctx_exec = ctx
        cfg = dict(ctx.config or {})
        strategies = dict(cfg.get("strategies") or {})
        body = dict(strategies.get(self.name) or {})
        self.target_backend_name = str(
            body.get("target_backend_name")
            or body.get("backend")
            or cfg.get("target_backend_name")
            or self.target_backend_name
        )
        self._top_logprobs = int(body.get("top_logprobs", self._top_logprobs))
        self._temperature = max(0.1, float(body.get("temperature", self._temperature)))
        self._target_backend = _resolve_backend(
            ctx.registry,
            self.target_backend_name,
            fallbacks=("tier2", "tier3", "llama_cpp"),
        )

    async def propose(self, req: ProposalRequest) -> Proposal:
        backend = self._target_backend
        if backend is None or not hasattr(backend, "generate_with_logits"):
            return _empty_proposal(self.name)
        try:
            result = await backend.generate_with_logits(
                [{"role": "user", "content": req.prompt_text}],
                max_tokens=max(1, int(req.draft_len)),
                temperature=max(float(req.temperature), self._temperature),
                top_logprobs=max(1, self._top_logprobs),
                session_id=req.session_id,
                quant=req.quant,
                kv_handle=req.kv_handle,
                id_slot=req.id_slot,
                ctx=self._ctx_exec,
            )
            text = str(getattr(result, "text", "") or "")
            tokens = _tokens_from_result(result, text, backend)
            if not text.strip() or not tokens:
                return _empty_proposal(self.name)
            return Proposal(
                tokens=tokens,
                text=text,
                strategy=self.name,
                draft_len=len(tokens),
                confidence=0.55,
                source_tier=int(getattr(result, "tier_used", 2) or 2),
                metadata={
                    "backend": getattr(result, "backend", "") or self.target_backend_name,
                    "model": getattr(result, "model", ""),
                    "latency_ms": float(getattr(result, "latency_ms", 0.0) or 0.0),
                    "top_logprobs": float(self._top_logprobs),
                },
            )
        except Exception:
            return _empty_proposal(self.name)


@register_proposer("ngram")
class NgramProposer(ProposalStrategy):
    """Prompt lookup proposer using only repeated n-grams from req.prompt_text."""

    name = "ngram"

    def __init__(self, ngram_size: int = 16) -> None:
        self.ngram_size = ngram_size

    async def initialize(self, ctx: ASCRInitContext) -> None:
        strategies = dict((ctx.config or {}).get("strategies") or {})
        body = dict(strategies.get(self.name) or {})
        self.ngram_size = int(body.get("ngram_size", self.ngram_size))

    async def propose(self, req: ProposalRequest) -> Proposal:
        words = (req.prompt_text or "").split()
        draft_len = max(0, int(req.draft_len))
        if draft_len <= 0:
            return _empty_proposal(self.name)
        n = max(1, min(int(self.ngram_size), len(words)))
        if len(words) <= n:
            return _empty_proposal(self.name)
        seed = words[-n:]
        draft_words: list[str] = []
        # Search only before the trailing seed, then emit tokens that followed
        # the earlier occurrence in the original prompt.
        for index in range(0, len(words) - n):
            if words[index : index + n] != seed:
                continue
            start = index + n
            end = min(len(words) - n, start + draft_len)
            draft_words = words[start:end]
            if draft_words:
                break
        text = " ".join(draft_words)
        return Proposal(
            tokens=[
                ProposalToken(text=word, token_id=hash(word), logprob=0.0, rank=0)
                for word in draft_words
            ],
            text=text,
            strategy=self.name,
            draft_len=len(draft_words),
            confidence=0.5 if draft_words else 0.0,
            source_tier=1,
            metadata={"ngram_size": n, "zero_latency": True},
        )


def _empty_proposal(strategy: str) -> Proposal:
    return Proposal(
        tokens=[],
        text="",
        strategy=strategy,
        draft_len=0,
        confidence=0.0,
        source_tier=1,
    )


def _resolve_backend(
    registry: Any,
    preferred: str,
    *,
    fallbacks: tuple[str, ...],
) -> Any:
    if registry is None:
        return None
    for name in (preferred, *fallbacks):
        try:
            backend = registry.get(name)
        except Exception:
            backend = None
        if backend is not None:
            return backend
    return None


def _make_generate_request(req: ProposalRequest) -> Any:
    messages = [{"role": "user", "content": req.prompt_text}]
    try:
        from neuroswarm_arm.runtime.dipa.interfaces.types import GenerateRequest

        return GenerateRequest(
            messages=messages,
            max_tokens=max(1, int(req.draft_len)),
            temperature=float(req.temperature),
            session_id=req.session_id,
            quant=req.quant,
            stream=False,
            kv_handle=req.kv_handle,
            id_slot=req.id_slot,
            speculative=True,
        )
    except Exception:
        from types import SimpleNamespace

        return SimpleNamespace(
            messages=messages,
            max_tokens=max(1, int(req.draft_len)),
            temperature=float(req.temperature),
            session_id=req.session_id,
            quant=req.quant,
            stream=False,
            kv_handle=req.kv_handle,
            id_slot=req.id_slot,
            speculative=True,
        )


def _tokens_from_result(result: Any, text: str, backend: Any) -> list[ProposalToken]:
    raw = getattr(result, "raw", None) or {}
    tokens = _tokens_from_logprobs(raw)
    if tokens:
        return tokens
    words = text.split()
    token_ids = _token_ids_for_text(backend, text)
    return [
        ProposalToken(
            text=word,
            token_id=token_ids[i] if i < len(token_ids) else hash(word),
            logprob=0.0,
            rank=0,
        )
        for i, word in enumerate(words)
    ]


def _tokens_from_logprobs(raw: dict[str, Any]) -> list[ProposalToken]:
    entries = _logprob_entries(raw)
    out: list[ProposalToken] = []
    for rank, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        text = str(
            entry.get("token")
            or entry.get("text")
            or entry.get("content")
            or ""
        )
        if not text:
            continue
        tid = entry.get("token_id")
        lp = entry.get("logprob")
        out.append(
            ProposalToken(
                text=text,
                token_id=int(tid) if isinstance(tid, int) else hash(text),
                logprob=float(lp) if isinstance(lp, (int, float)) else 0.0,
                rank=rank,
            )
        )
    return out


def _logprob_entries(raw: dict[str, Any]) -> list[Any]:
    choices = raw.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return []
    choice = choices[0]
    logprobs = choice.get("logprobs")
    if isinstance(logprobs, dict):
        content = logprobs.get("content") or []
        if isinstance(content, list) and content:
            return list(content)
    for key in ("completion_probabilities", "probs"):
        legacy = choice.get(key)
        if isinstance(legacy, list) and legacy:
            return list(legacy)
    return []


def _token_ids_for_text(backend: Any, text: str) -> list[int]:
    tokenize = getattr(backend, "tokenize", None)
    if not callable(tokenize):
        return []
    try:
        token_ids = tokenize(text)
    except Exception:
        return []
    if not isinstance(token_ids, list):
        return []
    out: list[int] = []
    for token_id in token_ids:
        try:
            out.append(int(token_id))
        except Exception:
            continue
    return out
