from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NavNode:
    id: str
    title: str
    path: str
    children: list[str]
    summary: str = ""


class Navigator:
    def __init__(self, loader: Any):
        self.loader = loader

    def navigate(self, path_or_id: str, depth: int = 1) -> NavNode:
        alias = self.loader.alias_map
        doc_id = alias.get(path_or_id, path_or_id)
        meta = self.loader.document_index.get(doc_id) or {}
        children: list[str] = []
        nav = self.loader.navigation_index
        path = meta.get("path") or path_or_id
        entry = nav.get(path) or {}
        children = list(entry.get("children") or [])
        if depth > 1:
            # one-hop graph neighbors
            for e in self.loader.graph.get("edges") or []:
                if e.get("src") == doc_id and e.get("dst") not in children:
                    children.append(e["dst"])
        summary = (self.loader.summary_index.get(doc_id) or {}).get("description", "")
        return NavNode(
            id=doc_id,
            title=str(meta.get("title") or doc_id),
            path=str(path),
            children=children,
            summary=str(summary),
        )
