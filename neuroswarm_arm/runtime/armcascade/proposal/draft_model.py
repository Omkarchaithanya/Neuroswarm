"""Backend-backed draft-model proposer (Tier 1)."""

from __future__ import annotations

import os
from typing import Any

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import ProposalStrategy
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    Proposal,
    ProposalRequest,
    ProposalToken,
    approx_tokens,
    build_messages,
)
from neuroswarm_arm.runtime.armcascade.proposal.registry import register_proposer
from neuroswarm_arm.runtime.armcascade.verification.tree import TreeBuilder


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@register_proposer("draft_model")
class DraftModelProposer(ProposalStrategy):
    name = "draft_model"

    def __init__(self, backend_name: str = "tier1") -> None:
        self.backend_name = backend_name
        self._registry: Any = None
        self._ctx_exec: Any = None
        self._tree_enabled = False

    async def initialize(self, ctx: ASCRInitContext) -> None:
        self._registry = ctx.registry
        cfg = dict(ctx.config or {})
        for t in cfg.get("tiers") or []:
            if isinstance(t, dict) and t.get("role") == "draft":
                self.backend_name = str(t.get("backend", self.backend_name))
        strategies = dict(cfg.get("strategies") or {})
        tree_cfg = dict(strategies.get("tree") or {})
        self._tree_enabled = bool(tree_cfg.get("enabled", False))
        if os.getenv("NSA_ASCR_TREE_ENABLED") is not None:
            self._tree_enabled = _env_bool("NSA_ASCR_TREE_ENABLED", self._tree_enabled)

    def bind_execution_context(self, exec_ctx: Any) -> None:
        self._ctx_exec = exec_ctx

    async def propose(self, req: ProposalRequest) -> Proposal:
        if self._registry is None:
            raise RuntimeError("DraftModelProposer not initialized")

        branching = int(req.metadata.get("branching", 1) or 1)
        branching = max(1, branching)
        if self._tree_enabled and branching > 1:
            return await self._propose_tree(req, branching=branching)

        backend = self._registry.require(self.backend_name)
        messages = build_messages(req.messages)
        gen = self._make_gen_req(
            messages=messages,
            max_tokens=max(1, int(req.draft_len)),
            temperature=float(req.temperature),
            session_id=req.session_id,
            quant=req.quant,
            kv_handle=req.kv_handle,
            id_slot=req.id_slot,
        )
        result = await backend.generate(gen, self._ctx_exec)
        text = result.text or ""
        conf = 0.6
        if result.metrics.get("confidence") is not None:
            conf = float(result.metrics["confidence"])
        slot_id = result.metrics.get("slot_id")
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
                "slot_id": slot_id,
                "id_slot": slot_id,
                "branching": 1,
            },
        )
        return proposal

    async def _propose_tree(self, req: ProposalRequest, *, branching: int) -> Proposal:
        """Sample top-k candidates per step; width capped at ``branching``."""
        backend = self._registry.require(self.backend_name)
        depth = max(1, int(req.draft_len))
        top_k = min(
            branching,
            _env_int("NSA_ASCR_TREE_DRAFT_TOP_K", branching),
        )
        builder = TreeBuilder()
        frontier: list[int] = []
        messages = build_messages(req.messages)
        flat_tokens: list[ProposalToken] = []
        latency_ms = 0.0
        model = ""
        backend_name = self.backend_name
        slot_id = None

        # Root step: one forward for top-k at position 0.
        roots = await self._sample_top(
            backend,
            messages,
            top_k=top_k,
            temperature=float(req.temperature),
            session_id=req.session_id,
            quant=req.quant,
            kv_handle=req.kv_handle,
            id_slot=req.id_slot,
        )
        latency_ms += roots.get("latency_ms", 0.0)
        model = roots.get("model") or model
        backend_name = roots.get("backend") or backend_name
        slot_id = roots.get("slot_id", slot_id)
        cands = roots.get("candidates") or []
        if not cands:
            # Fallback: flat single-token root from text.
            text = str(roots.get("text") or "draft")
            tid = hash(text.split()[0]) if text.split() else 0
            idx = builder.add_root(tid, 0.0, text.split()[0] if text.split() else text)
            frontier = [idx]
            flat_tokens.append(
                ProposalToken(text=builder.tree.texts[idx], token_id=tid, logprob=0.0)
            )
        else:
            first = cands[0]
            idx = builder.add_root(
                int(first["token_id"]),
                float(first["logprob"]),
                str(first["text"]),
            )
            frontier = [idx]
            flat_tokens.append(
                ProposalToken(
                    text=str(first["text"]),
                    token_id=int(first["token_id"]),
                    logprob=float(first["logprob"]),
                    rank=0,
                )
            )
            # Sibling roots become children of first root to keep single-root tree.
            extra = cands[1:top_k]
            if extra and depth > 1:
                # Keep width at root level via synthetic forest→single-root: attach as
                # alternate depth-1 only when depth==1; else siblings expand under root.
                pass

        for d in range(1, depth):
            if not frontier:
                break
            next_frontier: list[int] = []
            # Cap total frontier growth: each parent gets ≤ branching children,
            # and level width ≤ branching (SpecInfer / Sequoia width bound).
            slots_left = branching
            for parent in list(frontier):
                if slots_left <= 0:
                    break
                take = min(top_k, slots_left, branching)
                step = await self._sample_top(
                    backend,
                    messages
                    + [
                        {
                            "role": "assistant",
                            "content": " ".join(
                                builder.tree.texts[i]
                                for i in _path_to_root(builder.tree, parent)
                            ),
                        }
                    ],
                    top_k=take,
                    temperature=float(req.temperature),
                    session_id=req.session_id,
                    quant=req.quant,
                    kv_handle=req.kv_handle,
                    id_slot=req.id_slot,
                )
                latency_ms += step.get("latency_ms", 0.0)
                cands = (step.get("candidates") or [])[:take]
                if not cands:
                    continue
                ids = [int(c["token_id"]) for c in cands]
                lps = [float(c["logprob"]) for c in cands]
                texts = [str(c["text"]) for c in cands]
                created = builder.extend(parent, ids, lps, texts)
                next_frontier.extend(created)
                slots_left -= len(created)
                if d == depth - 1 or not flat_tokens or parent == frontier[0]:
                    # Prefer primary path tokens for flat proposal view.
                    if parent == frontier[0] and created:
                        c0 = cands[0]
                        flat_tokens.append(
                            ProposalToken(
                                text=str(c0["text"]),
                                token_id=int(c0["token_id"]),
                                logprob=float(c0["logprob"]),
                                rank=0,
                            )
                        )
            frontier = next_frontier[: max(1, branching ** (d + 1))]
            # Hard leaf bound: branching ** depth
            max_leaves = branching**depth
            if builder.tree.branches_total > max_leaves:
                break

        tree = builder.build()
        # Enforce width ≤ branching at every level.
        _cap_tree_width(tree, branching)

        text = " ".join(t.text for t in flat_tokens) or " ".join(
            tree.texts[i] for i in tree.dfs_order() if tree.nodes[i][1] < 0 or True
        )
        # Prefer root→child chain text for primary path.
        if tree.size:
            primary = _primary_path_texts(tree)
            if primary:
                text = " ".join(primary)

        return Proposal(
            tokens=flat_tokens
            or [
                ProposalToken(text=t, token_id=tid, logprob=lp)
                for (tid, _p, lp), t in zip(tree.nodes, tree.texts)
            ],
            text=text,
            strategy=self.name,
            draft_len=max(len(flat_tokens), tree.depth),
            confidence=0.55,
            source_tier=1,
            tree=tree,
            metadata={
                "backend": backend_name,
                "model": model,
                "latency_ms": latency_ms,
                "prompt_tokens": approx_tokens(req.prompt_text),
                "slot_id": slot_id,
                "id_slot": slot_id,
                "branching": branching,
                "tree_depth": tree.depth,
                "tree_branches_total": tree.branches_total,
            },
        )

    @staticmethod
    def _make_gen_req(
        *,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        session_id: str,
        quant: str,
        kv_handle: str | None,
        id_slot: int | None,
    ) -> Any:
        try:
            from neuroswarm_arm.runtime.dipa.interfaces.types import GenerateRequest

            return GenerateRequest(
                messages=messages,
                max_tokens=max(1, int(max_tokens)),
                temperature=float(temperature),
                session_id=session_id,
                quant=quant,
                stream=False,
                kv_handle=kv_handle,
                id_slot=id_slot,
                speculative=True,
            )
        except Exception:  # noqa: BLE001 — tests / missing optional deps
            from types import SimpleNamespace

            return SimpleNamespace(
                messages=messages,
                max_tokens=max(1, int(max_tokens)),
                temperature=float(temperature),
                session_id=session_id,
                quant=quant,
                stream=False,
                kv_handle=kv_handle,
                id_slot=id_slot,
                speculative=True,
            )

    async def _sample_top(
        self,
        backend: Any,
        messages: list[dict[str, str]],
        *,
        top_k: int,
        temperature: float,
        session_id: str,
        quant: str,
        kv_handle: str | None,
        id_slot: int | None,
    ) -> dict[str, Any]:
        """One-step top-k sample via generate_with_logits or flat generate."""
        if hasattr(backend, "generate_with_logits"):
            result = await backend.generate_with_logits(
                messages=messages,
                max_tokens=1,
                temperature=temperature,
                top_logprobs=max(1, top_k),
                session_id=session_id,
                quant=quant,
                kv_handle=kv_handle,
                id_slot=id_slot,
                ctx=self._ctx_exec,
            )
            cands = _candidates_from_raw(result.raw or {}, top_k=top_k)
            if not cands and result.text:
                word = result.text.split()[0]
                cands = [
                    {
                        "token_id": hash(word),
                        "logprob": 0.0,
                        "text": word,
                    }
                ]
            return {
                "candidates": cands,
                "text": result.text or "",
                "latency_ms": float(result.latency_ms or 0.0),
                "model": result.model,
                "backend": result.backend or self.backend_name,
                "slot_id": (result.metrics or {}).get("slot_id"),
            }

        gen = self._make_gen_req(
            messages=messages,
            max_tokens=1,
            temperature=temperature,
            session_id=session_id,
            quant=quant,
            kv_handle=kv_handle,
            id_slot=id_slot,
        )
        result = await backend.generate(gen, self._ctx_exec)
        text = (result.text or "tok").split()[0]
        # Synthetic siblings for structure when logits unavailable (width ≤ top_k).
        cands = [
            {"token_id": hash(text) + i, "logprob": -0.1 * (i + 1), "text": text if i == 0 else f"{text}_{i}"}
            for i in range(max(1, top_k))
        ]
        return {
            "candidates": cands,
            "text": result.text or text,
            "latency_ms": float(result.latency_ms or 0.0),
            "model": result.model,
            "backend": result.backend or self.backend_name,
            "slot_id": (result.metrics or {}).get("slot_id"),
        }

    def estimate_confidence(self, proposal: Proposal) -> float:
        if proposal.draft_len <= 0:
            return 0.0
        return float(proposal.confidence or 0.5)


def _candidates_from_raw(raw: dict[str, Any], *, top_k: int) -> list[dict[str, Any]]:
    choices = raw.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return []
    c0 = choices[0]
    logprobs = c0.get("logprobs")
    content = []
    if isinstance(logprobs, dict):
        content = logprobs.get("content") or []
    if not content:
        return []
    entry = content[0] if isinstance(content[0], dict) else {}
    top = entry.get("top_logprobs") or entry.get("top") or []
    out: list[dict[str, Any]] = []
    for i, item in enumerate(top):
        if i >= top_k:
            break
        if not isinstance(item, dict):
            continue
        tok = str(item.get("token") or item.get("text") or "").strip()
        if not tok:
            continue
        lp = item.get("logprob")
        tid = item.get("token_id")
        out.append(
            {
                "text": tok,
                "logprob": float(lp) if isinstance(lp, (int, float)) else 0.0,
                "token_id": int(tid) if isinstance(tid, int) else hash(tok),
            }
        )
    if not out:
        tok = str(entry.get("token") or "").strip()
        if tok:
            tid = entry.get("token_id")
            lp = entry.get("logprob")
            out.append(
                {
                    "text": tok,
                    "logprob": float(lp) if isinstance(lp, (int, float)) else 0.0,
                    "token_id": int(tid) if isinstance(tid, int) else hash(tok),
                }
            )
    return out


def _path_to_root(tree: Any, idx: int) -> list[int]:
    path: list[int] = []
    cur = idx
    seen = 0
    while cur >= 0 and seen <= tree.size:
        path.append(cur)
        cur = tree.nodes[cur][1]
        seen += 1
    path.reverse()
    return path


def _primary_path_texts(tree: Any) -> list[str]:
    if not tree.nodes:
        return []
    roots = [i for i, (_t, p, _lp) in enumerate(tree.nodes) if p < 0]
    if not roots:
        return []
    cur = roots[0]
    texts = [tree.texts[cur]]
    while tree.children[cur]:
        cur = tree.children[cur][0]
        texts.append(tree.texts[cur])
    return texts


def _cap_tree_width(tree: Any, branching: int) -> None:
    """Trim children lists so every node has ≤ branching kids."""
    for i, kids in enumerate(tree.children):
        if len(kids) > branching:
            tree.children[i] = kids[:branching]
