from __future__ import annotations

# Fix resolver return type - proper helpers

from pathlib import Path
from typing import Any

from nexus_okf.compiler.ast import DocumentNode
from nexus_okf.compiler.diagnostics import Diagnostics


def resolve_documents(
    docs: list[DocumentNode], diag: Diagnostics
) -> tuple[dict[str, DocumentNode], dict[str, DocumentNode], dict[str, str]]:
    by_id: dict[str, DocumentNode] = {}
    by_rel: dict[str, DocumentNode] = {}
    alias_map: dict[str, str] = {}

    for doc in docs:
        by_rel[doc.rel_path] = doc
        if doc.id in by_id and by_id[doc.id].rel_path != doc.rel_path:
            diag.error("DUP_ID", f"Duplicate id {doc.id}", doc.rel_path)
        by_id[doc.id] = doc
        for alias in doc.frontmatter.get("aliases") or []:
            a = str(alias)
            if a in alias_map and alias_map[a] != doc.id:
                diag.error("ALIAS_CONFLICT", f"Alias {a} -> {alias_map[a]} and {doc.id}", doc.rel_path)
            alias_map[a] = doc.id

    for doc in docs:
        for link in doc.links:
            target = link.target
            if link.kind == "wiki":
                if target in by_id or target in alias_map:
                    continue
                cand = _resolve_rel(doc.rel_path, target if target.endswith(".md") else target + ".md")
                if cand not in by_rel and target not in by_rel:
                    diag.warning("UNRESOLVED_WIKI", f"Unresolved wikilink [[{target}]]", doc.rel_path)
            elif link.kind == "md":
                if target.startswith(("http://", "https://", "mcp://")):
                    continue
                cand = _resolve_rel(doc.rel_path, target)
                if cand not in by_rel:
                    diag.warning("BROKEN_REF", f"Broken reference {target}", doc.rel_path)

    return by_id, by_rel, alias_map


def _resolve_rel(from_rel: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    base = str(Path(from_rel).parent)
    if base == ".":
        return Path(target).as_posix()
    return (Path(base) / target).as_posix()


def build_alias_map(docs: list[DocumentNode]) -> dict[str, str]:
    out: dict[str, str] = {}
    for doc in docs:
        out[doc.id] = doc.id
        for alias in doc.frontmatter.get("aliases") or []:
            out[str(alias)] = doc.id
        out[doc.rel_path] = doc.id
        out[doc.rel_path.removesuffix(".md")] = doc.id
    return out
