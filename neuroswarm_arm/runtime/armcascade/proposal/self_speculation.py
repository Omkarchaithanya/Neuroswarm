"""N-gram self-speculation proposer (no draft model)."""

from __future__ import annotations

import os

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import ProposalStrategy
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    Proposal,
    ProposalRequest,
)
from neuroswarm_arm.runtime.armcascade.proposal.ngram_cache import NgramCache
from neuroswarm_arm.runtime.armcascade.proposal.registry import register_proposer


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _linear_scan_next(words: list[str], seed: list[str]) -> list[str]:
    """O(N) Prompt Lookup: collect tokens that follow each seed occurrence."""
    if not seed or len(words) <= len(seed):
        return []
    k = len(seed)
    found: list[str] = []
    # Search history excluding the trailing seed itself.
    limit = len(words) - k
    for i in range(limit):
        if words[i : i + k] == seed:
            found.append(words[i + k])
    return found


def _echo_seed(seed: list[str], draft_len: int) -> list[str]:
    draft_tokens: list[str] = []
    while len(draft_tokens) < draft_len and seed:
        remaining = draft_len - len(draft_tokens)
        draft_tokens.extend(seed[:remaining])
        if remaining <= len(seed):
            break
    return draft_tokens


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
        self._cache_enabled = False
        self._cache: NgramCache | None = None
        self._cache_n = 3
        self._cache_max_entries = 1_000_000
        self._context_shift_k = 8
        self._prev_words: list[str] = []

    async def initialize(self, ctx: ASCRInitContext) -> None:
        strategies = dict((ctx.config or {}).get("strategies") or {})
        body = dict(strategies.get("self_speculation") or {})
        if body:
            self.ngram_size = int(body.get("ngram_size", self.ngram_size))
            self.draft_min = int(body.get("draft_min", self.draft_min))
            self.draft_max = int(body.get("draft_max", self.draft_max))

        cache_cfg = dict(strategies.get("ngram_cache") or {})
        enabled = bool(cache_cfg.get("enabled", False))
        if os.getenv("NSA_NGRAM_CACHE") is not None:
            enabled = _env_bool("NSA_NGRAM_CACHE", enabled)
        self._cache_enabled = enabled
        self._cache_n = int(cache_cfg.get("n", self._cache_n))
        self._cache_max_entries = int(
            cache_cfg.get("max_entries", self._cache_max_entries)
        )
        self._context_shift_k = _env_int(
            "NSA_NGRAM_CONTEXT_SHIFT_K",
            int(cache_cfg.get("context_shift_k", self._context_shift_k)),
        )
        if self._cache_enabled:
            self._cache = NgramCache(n=self._cache_n, max_entries=self._cache_max_entries)
        else:
            self._cache = None
        self._prev_words = []

    def _context_shifted(self, words: list[str]) -> bool:
        k = max(1, self._context_shift_k)
        prev = self._prev_words
        if not prev:
            return True
        if abs(len(words) - len(prev)) > k:
            return True
        tail_w = words[-k:] if len(words) >= k else words
        tail_p = prev[-k:] if len(prev) >= k else prev
        return tail_w != tail_p

    def _ensure_cache(self, words: list[str], text: str) -> None:
        if not self._cache_enabled or self._cache is None:
            return
        if self._context_shifted(words) or len(self._cache) == 0:
            self._cache.clear()
            self._cache.add(text)
        self._prev_words = list(words)

    def _chain_from_cache(
        self, words: list[str], draft_len: int
    ) -> tuple[list[str], bool]:
        assert self._cache is not None
        n = self._cache.n
        seed_len = n - 1
        if len(words) < seed_len:
            return [], False
        draft: list[str] = []
        window = list(words[-seed_len:])
        hit = False
        while len(draft) < draft_len:
            nxts = self._cache.lookup(window)
            if not nxts:
                break
            hit = True
            tok = nxts[0]
            draft.append(tok)
            window = window[1:] + [tok]
        return draft, hit

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

        lookup_path = "echo"
        cache_hit = False
        cache_bytes = 0
        draft_tokens: list[str] = []

        if self._cache_enabled and self._cache is not None:
            self._ensure_cache(words, text)
            cache_bytes = self._cache.__sizeof__()
            draft_tokens, cache_hit = self._chain_from_cache(words, draft_len)
            if cache_hit and draft_tokens:
                lookup_path = "cache"
            else:
                seed_len = self._cache.n - 1
                seed = words[-seed_len:] if len(words) >= seed_len else words
                scanned = _linear_scan_next(words, seed)
                if scanned:
                    draft_tokens = scanned[:draft_len]
                    # Extend by re-scanning with sliding seed when possible.
                    while len(draft_tokens) < draft_len:
                        win = (words + draft_tokens)[-seed_len:]
                        more = _linear_scan_next(words + draft_tokens, win)
                        if not more:
                            break
                        draft_tokens.append(more[0])
                    lookup_path = "scan"
                else:
                    n = min(self.ngram_size, len(words))
                    seed = words[-n:]
                    draft_tokens = _echo_seed(seed, draft_len)
                    lookup_path = "echo"
        else:
            n = min(self.ngram_size, len(words))
            seed = words[-n:]
            # Cache off: still try linear scan when seed appears earlier.
            scanned = _linear_scan_next(words, seed)
            if scanned:
                draft_tokens = scanned[:draft_len]
                lookup_path = "scan"
            else:
                draft_tokens = _echo_seed(seed, draft_len)
                lookup_path = "echo"

        draft = " ".join(draft_tokens)
        conf = min(0.9, 0.4 + 0.01 * min(50, len(words)))
        n_meta = min(self.ngram_size, len(words))
        return Proposal.from_text(
            draft,
            strategy=self.name,
            source_tier=1,
            confidence=conf,
            metadata={
                "ngram_size": n_meta,
                "seed_len": n_meta if lookup_path == "echo" else max(1, (self._cache.n - 1) if self._cache else n_meta),
                "cache_hit": cache_hit,
                "cache_bytes": cache_bytes,
                "lookup_path": lookup_path,
            },
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
