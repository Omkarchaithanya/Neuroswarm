from __future__ import annotations

from typing import Any

from nexus_okf.compiler.ast import DocumentNode


def optimize_graph(graph: dict[str, Any], docs: list[DocumentNode]) -> dict[str, Any]:
    """Prune duplicate edges and drop self-loops."""
    seen: set[tuple[str, str, str]] = set()
    edges = []
    for e in graph.get("edges") or []:
        key = (e["src"], e["dst"], e.get("pred", ""))
        if e["src"] == e["dst"]:
            continue
        if key in seen:
            continue
        seen.add(key)
        edges.append(e)
    graph = dict(graph)
    graph["edges"] = edges
    # section merge hints
    hints = []
    for doc in docs:
        if len(doc.sections) > 12:
            hints.append({"id": doc.id, "action": "prefer_summary", "reason": "many_sections"})
    graph["optimize_hints"] = hints
    return graph
