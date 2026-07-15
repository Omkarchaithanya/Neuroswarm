from __future__ import annotations

from typing import Any


class GraphEngine:
    def __init__(self, loader: Any):
        self.loader = loader
        self._adj: dict[str, list[tuple[str, float]]] | None = None

    def _ensure(self) -> dict[str, list[tuple[str, float]]]:
        if self._adj is None:
            adj: dict[str, list[tuple[str, float]]] = {}
            for e in self.loader.graph.get("edges") or []:
                adj.setdefault(e["src"], []).append((e["dst"], float(e.get("weight", 1.0))))
            self._adj = adj
        return self._adj

    def expand(self, seeds: list[str], depth: int = 1) -> list[tuple[str, float, int]]:
        adj = self._ensure()
        seen: dict[str, tuple[float, int]] = {s: (1.0, 0) for s in seeds}
        frontier = list(seeds)
        for d in range(1, max(1, depth) + 1):
            nxt: list[str] = []
            for node in frontier:
                for neigh, w in adj.get(node, []):
                    score = seen[node][0] * w * (0.85**d)
                    if neigh not in seen or score > seen[neigh][0]:
                        seen[neigh] = (score, d)
                        nxt.append(neigh)
            frontier = nxt
        return [(n, sc, dist) for n, (sc, dist) in seen.items()]


class AliasResolver:
    def __init__(self, loader: Any):
        self.loader = loader

    def resolve(self, term: str) -> str:
        return self.loader.alias_map.get(term, term)

    def expand_terms(self, terms: list[str]) -> list[str]:
        out: list[str] = []
        for t in terms:
            out.append(t)
            rid = self.resolve(t)
            if rid not in out:
                out.append(rid)
        return out


class OntologyResolver:
    def __init__(self, loader: Any):
        self.loader = loader

    def map_intent_types(self, kinds: list[str]) -> list[str]:
        ontology = self.loader.get("ontology.json") or {}
        type_map = ontology.get("type_map") or {}
        # kinds may already be document types
        return [type_map.get(k, k) for k in kinds]


class ReferenceResolver:
    def __init__(self, loader: Any):
        self.loader = loader

    def neighbors(self, doc_id: str) -> list[str]:
        refs = self.loader.reference_index
        return list((refs.get("outbound") or {}).get(doc_id) or [])
