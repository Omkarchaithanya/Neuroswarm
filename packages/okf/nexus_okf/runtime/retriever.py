from __future__ import annotations

from typing import Any

from nexus_okf.runtime.graph_engine import AliasResolver, GraphEngine, OntologyResolver


class Retriever:
    def __init__(self, loader: Any):
        self.loader = loader
        self.graph = GraphEngine(loader)
        self.aliases = AliasResolver(loader)
        self.ontology = OntologyResolver(loader)

    def keyword_candidates(self, terms: list[str], allowed: set[str] | None = None) -> list[str]:
        idx = self.loader.keyword_index
        scores: dict[str, int] = {}
        for t in terms:
            for doc_id in idx.get(t.lower(), []):
                if allowed is not None and doc_id not in allowed:
                    continue
                scores[doc_id] = scores.get(doc_id, 0) + 1
        return [d for d, _ in sorted(scores.items(), key=lambda x: -x[1])]

    def retrieve(
        self,
        terms: list[str],
        *,
        allowed: set[str] | None = None,
        expand_depth: int = 1,
        types: list[str] | None = None,
    ) -> list[str]:
        terms = self.aliases.expand_terms(terms)
        cands = self.keyword_candidates(terms, allowed)
        if not cands and allowed:
            cands = list(allowed)[:50]
        expanded = self.graph.expand(cands[:20] or list(allowed or [])[:10], depth=expand_depth)
        ids = [n for n, _, _ in sorted(expanded, key=lambda x: -x[1])]
        if types:
            di = self.loader.document_index
            ids = [i for i in ids if (di.get(i) or {}).get("type") in types]
        if allowed is not None:
            ids = [i for i in ids if i in allowed]
        return ids
