"""Multi-pass Context Compression Engine — measurable, no fixed % targets."""

from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict

from neuroswarm_arm.runtime.acr.ir.bundles import KnowledgeBundle, KnowledgeItem, MemoryBundle, MemoryItem
from neuroswarm_arm.runtime.acr.ir.plan import CompressionPass, CompressionPlan
from neuroswarm_arm.runtime.acr.ir.requirement import ContextRequirementGraph
from neuroswarm_arm.runtime.acr.ir.stats import CompressionMetrics


def _tokens(text: str) -> int:
    return max(1, len((text or "").split()))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _fingerprint(text: str) -> str:
    return hashlib.sha1(_norm(text).encode("utf-8")).hexdigest()[:16]


class CompressionEngine:
    """Ordered compression passes. Each pass skippable via CompressionPlan."""

    def compress(
        self,
        memory: MemoryBundle,
        knowledge: KnowledgeBundle,
        plan: CompressionPlan,
        graph: ContextRequirementGraph,
    ) -> tuple[MemoryBundle, KnowledgeBundle, CompressionMetrics]:
        t0 = time.perf_counter()
        in_tok = memory.total_tokens + knowledge.total_tokens
        metrics = CompressionMetrics(input_tokens=in_tok)
        mem_items = list(memory.items)
        know_items = list(knowledge.items)

        for pass_name in plan.passes:
            if pass_name == CompressionPass.SEMANTIC_DEDUP:
                mem_items = self._dedup_memory(mem_items)
                know_items = self._dedup_knowledge(know_items)
            elif pass_name == CompressionPass.IMPORTANCE_FILTER:
                mem_items = [i for i in mem_items if i.score >= plan.min_importance or i.importance >= plan.min_importance]
            elif pass_name == CompressionPass.TEMPORAL:
                mem_items = self._temporal_compress(mem_items)
            elif pass_name == CompressionPass.HIERARCHICAL:
                mem_items = self._hierarchical(mem_items)
                know_items = self._hierarchical_know(know_items)
            elif pass_name == CompressionPass.CONFLICT_RESOLVE:
                mem_items = self._conflict_resolve(mem_items)
            elif pass_name in (CompressionPass.REFERENCE, CompressionPass.POINTER):
                mem_items = self._pointer_compress(mem_items)
                know_items = self._pointer_know(know_items)
            elif pass_name == CompressionPass.SECTION_FOLD:
                know_items = self._section_fold(know_items)
            elif pass_name == CompressionPass.RELATIONSHIP:
                mem_items = self._relationship_compress(mem_items)
            elif pass_name == CompressionPass.PACK:
                mem_items, know_items = self._pack(mem_items, know_items, plan.token_budget)
            elif pass_name == CompressionPass.CHUNK_MERGE:
                mem_items = self._chunk_merge(mem_items)
            elif pass_name == CompressionPass.PROGRESSIVE:
                mem_items, know_items = self._progressive(mem_items, know_items, plan.token_budget, graph)
            metrics.passes_applied.append(pass_name.value)

        out_mem = MemoryBundle(request_id=memory.request_id, items=mem_items, source_step_ids=memory.source_step_ids)
        out_know = KnowledgeBundle(
            request_id=knowledge.request_id, items=know_items, source_step_ids=knowledge.source_step_ids
        )
        metrics.output_tokens = out_mem.total_tokens + out_know.total_tokens
        metrics.latency_ms = (time.perf_counter() - t0) * 1000.0
        metrics.information_retained = self._retention_proxy(graph, out_mem, out_know)
        metrics.confidence = min(1.0, 0.5 + 0.5 * metrics.information_retained)
        metrics.finalize()
        return out_mem, out_know, metrics

    def _dedup_memory(self, items: list[MemoryItem]) -> list[MemoryItem]:
        seen: set[str] = set()
        out: list[MemoryItem] = []
        for i in sorted(items, key=lambda x: -x.score):
            fp = _fingerprint(i.content)
            if fp in seen:
                continue
            seen.add(fp)
            out.append(i)
        return out

    def _dedup_knowledge(self, items: list[KnowledgeItem]) -> list[KnowledgeItem]:
        seen: set[str] = set()
        out: list[KnowledgeItem] = []
        for i in sorted(items, key=lambda x: -x.score):
            fp = _fingerprint(i.content[:500])
            if fp in seen:
                continue
            seen.add(fp)
            out.append(i)
        return out

    def _temporal_compress(self, items: list[MemoryItem]) -> list[MemoryItem]:
        # Keep highest score per approximate topic cluster (first 4 tokens)
        best: dict[str, MemoryItem] = {}
        for i in items:
            key = " ".join(_norm(i.content).split()[:4]) or i.content[:32]
            prev = best.get(key)
            if prev is None or i.score > prev.score:
                best[key] = i
        return list(best.values())

    def _hierarchical(self, items: list[MemoryItem]) -> list[MemoryItem]:
        if len(items) <= 4:
            return items
        # Summarize bottom half into one extractive line
        top = items[: max(2, len(items) // 2)]
        bottom = items[len(top) :]
        if not bottom:
            return top
        summary = MemoryItem(
            content="Summary: " + "; ".join(i.content[:80] for i in bottom[:5]),
            memory_type="summary",
            score=min(i.score for i in bottom),
            importance=0.4,
            tokens=0,
            metadata={"compressed_from": len(bottom)},
        )
        summary.tokens = _tokens(summary.content)
        return top + [summary]

    def _hierarchical_know(self, items: list[KnowledgeItem]) -> list[KnowledgeItem]:
        if len(items) <= 3:
            return items
        top = items[:3]
        rest = items[3:]
        folded = KnowledgeItem(
            content="[Folded knowledge] " + " | ".join(i.content[:60] for i in rest[:4]),
            kind="knowledge",
            score=min(i.score for i in rest),
            tokens=0,
            metadata={"folded": len(rest)},
        )
        folded.tokens = _tokens(folded.content)
        return top + [folded]

    def _conflict_resolve(self, items: list[MemoryItem]) -> list[MemoryItem]:
        # Prefer higher confidence/score when contents contradict via negation words
        by_entity: dict[str, list[MemoryItem]] = defaultdict(list)
        for i in items:
            key = " ".join(_norm(i.content).split()[:3])
            by_entity[key].append(i)
        out: list[MemoryItem] = []
        for group in by_entity.values():
            group.sort(key=lambda x: (-x.confidence, -x.score))
            out.append(group[0])
        return out

    def _pointer_compress(self, items: list[MemoryItem]) -> list[MemoryItem]:
        out: list[MemoryItem] = []
        for i in items:
            if len(i.content) > 400 and i.memory_id:
                short = MemoryItem(
                    content=f"[mem:{i.memory_id}] {i.content[:160]}…",
                    memory_id=i.memory_id,
                    namespace=i.namespace,
                    memory_type=i.memory_type,
                    score=i.score,
                    importance=i.importance,
                    confidence=i.confidence,
                    signals=i.signals,
                    metadata={**i.metadata, "pointer": True},
                )
                short.tokens = _tokens(short.content)
                out.append(short)
            else:
                out.append(i)
        return out

    def _pointer_know(self, items: list[KnowledgeItem]) -> list[KnowledgeItem]:
        out: list[KnowledgeItem] = []
        for i in items:
            if i.path and len(i.content) > 500:
                short = KnowledgeItem(
                    content=f"[okf:{i.path}#{i.section_id}] {i.content[:200]}…",
                    path=i.path,
                    section_id=i.section_id,
                    score=i.score,
                    kind=i.kind,
                    metadata={**i.metadata, "pointer": True},
                )
                short.tokens = _tokens(short.content)
                out.append(short)
            else:
                out.append(i)
        return out

    def _section_fold(self, items: list[KnowledgeItem]) -> list[KnowledgeItem]:
        by_path: dict[str, list[KnowledgeItem]] = defaultdict(list)
        for i in items:
            by_path[i.path or i.kind].append(i)
        out: list[KnowledgeItem] = []
        for path, group in by_path.items():
            if len(group) == 1:
                out.extend(group)
                continue
            group.sort(key=lambda x: -x.score)
            head = group[0]
            extras = " ¶ ".join(g.content[:80] for g in group[1:3])
            folded = KnowledgeItem(
                content=f"{head.content}\n…({path}: {extras})",
                path=head.path,
                section_id=head.section_id,
                score=head.score,
                kind=head.kind,
                metadata={**head.metadata, "section_folded": len(group)},
            )
            folded.tokens = _tokens(folded.content)
            out.append(folded)
        return out

    def _relationship_compress(self, items: list[MemoryItem]) -> list[MemoryItem]:
        return items  # graph linking reserved for MemoryGraph integration

    def _pack(
        self, mem: list[MemoryItem], know: list[KnowledgeItem], budget: int
    ) -> tuple[list[MemoryItem], list[KnowledgeItem]]:
        # Greedy pack by score until budget
        combined: list[tuple[str, float, object]] = []
        for i in mem:
            combined.append(("m", i.score, i))
        for i in know:
            combined.append(("k", i.score, i))
        combined.sort(key=lambda x: -x[1])
        used = 0
        out_m: list[MemoryItem] = []
        out_k: list[KnowledgeItem] = []
        for kind, _, obj in combined:
            tok = getattr(obj, "tokens", 0) or _tokens(getattr(obj, "content", ""))
            if used + tok > budget and (out_m or out_k):
                continue
            used += tok
            if kind == "m":
                out_m.append(obj)  # type: ignore[arg-type]
            else:
                out_k.append(obj)  # type: ignore[arg-type]
        return out_m, out_k

    def _chunk_merge(self, items: list[MemoryItem]) -> list[MemoryItem]:
        if len(items) < 2:
            return items
        # Merge tiny adjacent same-namespace items
        out: list[MemoryItem] = []
        buf: MemoryItem | None = None
        for i in items:
            if i.tokens < 20 and buf is not None and buf.namespace == i.namespace:
                buf = MemoryItem(
                    content=buf.content + " | " + i.content,
                    namespace=buf.namespace,
                    memory_type=buf.memory_type,
                    score=max(buf.score, i.score),
                    importance=max(buf.importance, i.importance),
                    confidence=(buf.confidence + i.confidence) / 2,
                    metadata={"merged": True},
                )
                buf.tokens = _tokens(buf.content)
            else:
                if buf is not None:
                    out.append(buf)
                buf = i
        if buf is not None:
            out.append(buf)
        return out

    def _progressive(
        self,
        mem: list[MemoryItem],
        know: list[KnowledgeItem],
        budget: int,
        graph: ContextRequirementGraph,
    ) -> tuple[list[MemoryItem], list[KnowledgeItem]]:
        # Ensure must-have coverage first: keep items matching entities/topics
        must = set(e.lower() for e in graph.entities + graph.topics)
        if not must:
            return self._pack(mem, know, budget)

        def covers(text: str) -> bool:
            low = text.lower()
            return any(m in low for m in must)

        priority_m = [i for i in mem if covers(i.content)] + [i for i in mem if not covers(i.content)]
        priority_k = [i for i in know if covers(i.content)] + [i for i in know if not covers(i.content)]
        return self._pack(priority_m, priority_k, budget)

    def _retention_proxy(
        self, graph: ContextRequirementGraph, mem: MemoryBundle, know: KnowledgeBundle
    ) -> float:
        must = [n for n in graph.nodes if n.must_have]
        if not must:
            return 1.0 if (mem.items or know.items) else 0.0
        blob = " ".join(i.content for i in mem.items) + " " + " ".join(i.content for i in know.items)
        blob_l = blob.lower()
        hits = 0
        for n in must:
            labels = [n.label] + n.entities + n.namespaces
            if any(str(x).lower() in blob_l for x in labels if x):
                hits += 1
            elif n.kind.value in blob_l or mem.items or know.items:
                hits += 0.5
        # Entity retention
        ents = graph.entities[:8]
        if ents:
            ent_hits = sum(1 for e in ents if e.lower() in blob_l) / len(ents)
        else:
            ent_hits = 1.0
        return min(1.0, 0.6 * (hits / len(must)) + 0.4 * ent_hits)
