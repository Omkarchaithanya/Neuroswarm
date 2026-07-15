from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from nexus_okf.runtime.budget import BudgetManager
from nexus_okf.runtime.context import ContextBuilder, ContextSection
from nexus_okf.runtime.query.intent import detect_intent
from nexus_okf.runtime.ranking import RankingEngine
from nexus_okf.runtime.retriever import Retriever
from nexus_okf.internal.hashutil import content_hash


@dataclass
class OKFQuery:
    text: str
    agent_profile: str = "architect"
    domains: list[str] | None = None
    token_budget: int = 1200
    expand_refs: int = 1
    include_types: list[str] | None = None


@dataclass
class OKFContext:
    sections: list[ContextSection] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)
    tokens_used: int = 0
    cache_hit: bool = False
    metrics: dict[str, float] = field(default_factory=dict)
    text: str = ""

    def as_prompt_block(self) -> str:
        return self.text


class QueryPipeline:
    def __init__(self, loader: Any, cache: Any, mount_resolver: Any):
        self.loader = loader
        self.cache = cache
        self.mount = mount_resolver
        self.retriever = Retriever(loader)
        self.ranker = RankingEngine(loader)
        self.context = ContextBuilder(loader)

    def run(self, req: OKFQuery, history: dict[str, float] | None = None) -> OKFContext:
        t0 = perf_counter()
        cache_key = content_hash(
            f"{req.agent_profile}|{req.text}|{req.token_budget}|{req.domains}|{req.include_types}"
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            cached.cache_hit = True
            return cached

        intent = detect_intent(req.text)
        allowed = self.mount.allowed_ids(req.agent_profile, req.domains)
        candidates = self.retriever.retrieve(
            intent.terms,
            allowed=allowed,
            expand_depth=req.expand_refs,
            types=req.include_types or (intent.kinds if intent.kinds != ["concept"] else None),
        )
        distances = {c: float(i) for i, c in enumerate(candidates)}
        ranked = self.ranker.score(
            candidates,
            query_tags=set(intent.tags),
            distances=distances,
            mount_ids=allowed,
            history=history,
        )
        budget = BudgetManager(soft=req.token_budget, hard=int(req.token_budget * 1.25))
        sections = self.context.progressive_sections(
            ranked,
            soft_budget=budget.soft,
            hard_budget=budget.hard,
            expand_refs=req.expand_refs,
        )
        text = self.context.stitch(sections)
        tokens = sum(s.tokens for s in sections)
        ctx = OKFContext(
            sections=sections,
            provenance=[s.path for s in sections],
            tokens_used=tokens,
            cache_hit=False,
            metrics={
                "latency_ms": (perf_counter() - t0) * 1000.0,
                "candidates": float(len(candidates)),
                "sections": float(len(sections)),
                "budget_util": tokens / max(1, req.token_budget),
            },
            text=text,
        )
        self.cache.put(cache_key, ctx)
        return ctx
