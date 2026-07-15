from __future__ import annotations

from typing import Any

from nexus_okf.compiler.ast import DocumentNode


def build_graph(docs: list[DocumentNode], alias_map: dict[str, str]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    by_rel = {d.rel_path: d for d in docs}

    for doc in docs:
        nodes.append(
            {
                "id": doc.id,
                "path": doc.rel_path,
                "type": doc.doc_type,
                "title": doc.title,
                "priority": doc.frontmatter.get("priority", 50),
                "tags": list(doc.frontmatter.get("tags") or []),
                "visibility": doc.frontmatter.get("visibility", "internal"),
                "namespace": doc.frontmatter.get("namespace"),
                "token_budget": doc.frontmatter.get("token_budget"),
            }
        )
        # hierarchy edges
        parent = str(__import__("pathlib").Path(doc.rel_path).parent.as_posix())
        if parent != ".":
            parent_index = f"{parent}/index.md"
            if parent_index in by_rel:
                edges.append({"src": by_rel[parent_index].id, "dst": doc.id, "pred": "contains", "weight": 1.0})
        for link in doc.links:
            dst_id = _resolve_target(doc, link.target, alias_map, by_rel)
            if dst_id:
                edges.append({"src": doc.id, "dst": dst_id, "pred": "see_also", "weight": 0.8, "kind": link.kind})
        for rel in (doc.frontmatter.get("ontology") or {}).get("relations") or []:
            obj = rel.get("obj")
            pred = rel.get("pred", "depends_on")
            if obj:
                dst = alias_map.get(str(obj), str(obj))
                edges.append({"src": doc.id, "dst": dst, "pred": pred, "weight": 1.0, "kind": "ontology"})

    return {"nodes": nodes, "edges": edges}


def _resolve_target(doc: DocumentNode, target: str, alias_map: dict[str, str], by_rel: dict[str, DocumentNode]) -> str | None:
    if target in alias_map:
        return alias_map[target]
    from pathlib import Path

    base = Path(doc.rel_path).parent
    cand = (base / target).as_posix()
    if cand in by_rel:
        return by_rel[cand].id
    if target in by_rel:
        return by_rel[target].id
    return None


def detect_cycles(graph: dict[str, Any]) -> list[list[str]]:
    adj: dict[str, list[str]] = {}
    for e in graph.get("edges") or []:
        if e.get("pred") in {"depends_on", "extends"}:
            adj.setdefault(e["src"], []).append(e["dst"])
    cycles: list[list[str]] = []
    visited: set[str] = set()
    stack: set[str] = set()
    path: list[str] = []

    def dfs(n: str) -> None:
        if n in stack:
            if n in path:
                cycles.append(path[path.index(n) :] + [n])
            return
        if n in visited:
            return
        visited.add(n)
        stack.add(n)
        path.append(n)
        for nxt in adj.get(n, []):
            dfs(nxt)
        path.pop()
        stack.remove(n)

    for node in list(adj):
        dfs(node)
    return cycles
