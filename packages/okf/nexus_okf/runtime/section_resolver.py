from __future__ import annotations

from typing import Any


class SectionResolver:
    def __init__(self, loader: Any):
        self.loader = loader

    def resolve(self, doc_id: str, section_id: str | None = None) -> list[dict[str, Any]]:
        sections = list(self.loader.section_index.get(doc_id) or [])
        if section_id:
            return [s for s in sections if s.get("id") == section_id]
        return sections
