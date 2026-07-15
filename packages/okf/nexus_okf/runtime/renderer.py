from __future__ import annotations

from nexus_okf.runtime.context import ContextSection


class Renderer:
    def render(self, sections: list[ContextSection]) -> str:
        return "\n\n".join(f"## {s.id}/{s.section_id}\n{s.text}" for s in sections)
