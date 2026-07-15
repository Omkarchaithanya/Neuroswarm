# Origin: NEXUS Extension
"""NEXUS knowledge validator — extension rules only (not Google §9)."""

from __future__ import annotations

from typing import Any

from nexus_okf.compiler.ast import DocumentNode
from nexus_okf.compiler.diagnostics import Diagnostics
from nexus_okf.compiler.graph_builder import detect_cycles


def validate_bundle(
    docs: list[DocumentNode],
    graph: dict[str, Any],
    alias_map: dict[str, str],
    diag: Diagnostics,
    *,
    strict: bool = True,
) -> Diagnostics:
    ids = [d.id for d in docs]
    if len(ids) != len(set(ids)):
        diag.error("DUP_ID", "Duplicate official concept ids present")

    seen_aliases: dict[str, str] = {}
    for doc in docs:
        candidates: list[str] = []
        for key in ("nexus_id", "id"):
            val = doc.frontmatter.get(key)
            if val and str(val) != doc.id:
                candidates.append(str(val))
        for a in doc.frontmatter.get("aliases") or []:
            candidates.append(str(a))
        for a in candidates:
            if a in seen_aliases and seen_aliases[a] != doc.id:
                diag.error(
                    "DUP_ID",
                    f"Duplicate NEXUS alias {a} for {seen_aliases[a]} and {doc.id}",
                    doc.rel_path,
                )
            seen_aliases[a] = doc.id

    referenced: set[str] = set()
    for e in graph.get("edges") or []:
        referenced.add(e["dst"])
        node_ids = {n["id"] for n in graph.get("nodes") or []}
        if e["dst"] not in node_ids and e["dst"] not in alias_map:
            diag.warning("DEAD_REF", f"Edge to missing node {e['dst']}")

    for doc in docs:
        if doc.reserved:
            continue
        if not doc.frontmatter.get("type") and not doc.doc_type:
            diag.error("MISSING_META", "Missing type", doc.rel_path)
        tb = doc.frontmatter.get("token_budget")
        th = doc.frontmatter.get("token_budget_hard")
        if tb is not None and th is not None and int(tb) > int(th):
            diag.error("TOKEN_BUDGET", "token_budget exceeds token_budget_hard", doc.rel_path)
        vis = doc.frontmatter.get("visibility", "internal")
        if vis == "restricted" and not doc.frontmatter.get("permissions"):
            diag.warning("VISIBILITY", "restricted doc without permissions", doc.rel_path)

    for doc in docs:
        if doc.reserved or doc.rel_path == "index.md":
            continue
        if doc.id not in referenced and doc.doc_type not in {"domain", "ontology"}:
            if "/" not in doc.rel_path:
                diag.warning("ORPHAN", f"Possibly orphan document {doc.id}", doc.rel_path)

    for cycle in detect_cycles(graph):
        diag.error("GRAPH_CYCLE", f"Cycle detected: {' -> '.join(cycle)}")

    _ = strict
    return diag
