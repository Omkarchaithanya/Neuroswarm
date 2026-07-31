"""Hierarchical stub + SpecInfer TreeVerifier."""

from __future__ import annotations

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
)
from neuroswarm_arm.runtime.armcascade.proposal.registry import register_verifier
from neuroswarm_arm.runtime.armcascade.verification.logits_verifier import (
    parse_logits_bundle,
)
from neuroswarm_arm.runtime.armcascade.verification.strategies import _BackendVerifierBase
from neuroswarm_arm.runtime.armcascade.verification.tree import (
    TokenTree,
    TreeAcceptor,
    linear_tree_from_tokens,
)


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


@register_verifier("hierarchical")
class HierarchicalVerifier(VerifierStrategy):
    name = "hierarchical"

    async def initialize(self, ctx: ASCRInitContext) -> None:
        return None

    async def verify(self, draft: Proposal, req: VerifyRequest) -> VerifyResult:
        raise NotImplementedError(
            "hierarchical verification stub — needs multi-tier logits path"
        )


def _resolve_tree(draft: Proposal) -> TokenTree:
    tree = getattr(draft, "tree", None)
    if isinstance(tree, TokenTree) and tree.size > 0:
        return tree
    meta_tree = (draft.metadata or {}).get("tree")
    if isinstance(meta_tree, TokenTree) and meta_tree.size > 0:
        return meta_tree
    ids: list[int] = []
    lps: list[float] = []
    texts: list[str] = []
    if draft.tokens:
        for tok in draft.tokens:
            ids.append(int(tok.token_id if tok.token_id is not None else hash(tok.text)))
            lps.append(float(tok.logprob or 0.0))
            texts.append(tok.text)
    else:
        words = draft.text.split() if draft.text.strip() else []
        ids = [hash(w) for w in words]
        lps = [0.0 for _ in words]
        texts = list(words)
    return linear_tree_from_tokens(ids, lps, texts)


def _topn_from_bundle(
    bundle: Any,
) -> list[list[tuple[int, float, str]]]:
    """Convert LogitsBundle steps → per-position [(token_id, logprob, text)]."""
    out: list[list[tuple[int, float, str]]] = []
    for step in bundle.steps:
        row: list[tuple[int, float, str]] = []
        for entry in step.top:
            tid = entry.token_id if entry.token_id is not None else hash(entry.token)
            row.append((int(tid), float(entry.logprob), str(entry.token)))
        if not row and step.token:
            tid = step.token_id if step.token_id is not None else hash(step.token)
            row.append((int(tid), float(step.logprob), str(step.token)))
        out.append(row)
    return out


@register_verifier("tree")
class TreeVerifier(_BackendVerifierBase):
    """One target forward verifies multiple draft branches (SpecInfer)."""

    name = "tree"

    def __init__(
        self,
        backend_name: str = "tier2",
        max_branching: int = 4,
        top_k_per_branch: int = 8,
    ) -> None:
        super().__init__(backend_name=backend_name)
        self.max_branching = max_branching
        self.top_k_per_branch = top_k_per_branch
        self._enabled = True
        self._acceptor = TreeAcceptor()

    async def initialize(self, ctx: ASCRInitContext) -> None:
        await super().initialize(ctx)
        cfg = dict(ctx.config or {})
        strategies = dict(cfg.get("strategies") or {})
        tree_cfg = dict(strategies.get("tree") or {})
        self._enabled = bool(tree_cfg.get("enabled", False))
        if os.getenv("NSA_ASCR_TREE_ENABLED") is not None:
            self._enabled = _env_bool("NSA_ASCR_TREE_ENABLED", self._enabled)
        self.max_branching = _env_int(
            "NSA_ASCR_TREE_MAX_BRANCHING",
            int(tree_cfg.get("max_branching", self.max_branching)),
        )
        self.top_k_per_branch = _env_int(
            "NSA_ASCR_TREE_TOP_K",
            int(tree_cfg.get("top_k_per_branch", self.top_k_per_branch)),
        )

    async def verify(self, draft: Proposal, req: VerifyRequest) -> VerifyResult:
        if not self._enabled:
            raise NotImplementedError(
                "tree verifier disabled (strategies.tree.enabled=false)"
            )

        t0 = time.monotonic()
        tree = _resolve_tree(draft)
        if tree.size == 0:
            return VerifyResult(
                accepted_prefix_len=0,
                rejected=True,
                agreement=0.0,
                mode=VerifyMode.TREE,
                metrics={
                    "tree_depth": 0.0,
                    "tree_width_avg": 0.0,
                    "tree_branches_total": 0.0,
                },
            )

        depth = tree.depth
        top_n = max(1, int(self.max_branching) * int(self.top_k_per_branch))
        result = await self._generate(
            req,
            max_tokens=depth + 1,
            id_slot=req.id_slot,
            top_logprobs=top_n,
        )
        raw = dict(result.raw) if result.raw else {}
        text = result.text or ""
        bundle = parse_logits_bundle(raw, draft, completion_text=text, top_n=top_n)
        target_topn = _topn_from_bundle(bundle)

        # Unit-test / offline inject: req.metadata["tree_target_topn"]
        injected = (req.metadata or {}).get("tree_target_topn")
        if isinstance(injected, list) and injected:
            target_topn = injected  # type: ignore[assignment]

        greedy = float(req.temperature) == 0.0
        accept = self._acceptor.accept(tree, target_topn, greedy=greedy)
        path = accept.path
        prefix_len = int(path.depth)
        draft_len = max(1, draft.draft_len or approx_tokens(draft.text) or depth)
        agreement = prefix_len / float(draft_len)
        quality = text_quality_score(text or " ".join(path.texts), self._quality_cfg)
        elapsed = (time.monotonic() - t0) * 1000.0

        return VerifyResult(
            accepted_prefix_len=prefix_len,
            rejected=prefix_len == 0,
            agreement=agreement,
            entropy=1.0 - agreement,
            text=text or " ".join(path.texts),
            mode=VerifyMode.TREE,
            logits_available=bool(target_topn),
            quality_score=quality,
            latency_ms=result.latency_ms or elapsed,
            backend=result.backend or self.backend_name,
            model=result.model,
            tier_used=req.verifier_tier,
            bonus_token=accept.bonus,
            metrics={
                "draft_len": float(draft_len),
                "prefix_len": float(prefix_len),
                "agreement": agreement,
                "accept_mode": 3.0,
                "tree_depth": float(depth),
                "tree_width_avg": float(tree.width_avg),
                "tree_branches_total": float(tree.branches_total),
            },
            raw=raw,
        )
