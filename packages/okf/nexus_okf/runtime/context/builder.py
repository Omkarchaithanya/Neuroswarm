from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ContextSection:
    path: str
    id: str
    section_id: str
    text: str
    score: float
    tokens: int


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


class ContextBuilder:
    def __init__(self, loader: Any):
        self.loader = loader

    def progressive_sections(
        self,
        ranked: list[tuple[str, float]],
        *,
        soft_budget: int,
        hard_budget: int,
        expand_refs: int = 0,
    ) -> list[ContextSection]:
        sections: list[ContextSection] = []
        used = 0
        section_index = self.loader.section_index
        summary_index = self.loader.summary_index
        doc_index = self.loader.document_index

        for doc_id, score in ranked:
            if used >= soft_budget:
                break
            meta = doc_index.get(doc_id) or {}
            # progressive: summary first
            summary = (summary_index.get(doc_id) or {}).get("description") or ""
            if summary:
                tok = estimate_tokens(summary)
                if used + tok > hard_budget:
                    break
                sections.append(
                    ContextSection(
                        path=str(meta.get("path") or ""),
                        id=doc_id,
                        section_id="summary",
                        text=f"# {meta.get('title', doc_id)}\n{summary}",
                        score=score,
                        tokens=tok,
                    )
                )
                used += tok
            for sec in section_index.get(doc_id) or []:
                text = str(sec.get("text") or "")
                tok = int(sec.get("tokens") or estimate_tokens(text))
                if used + tok > soft_budget:
                    continue
                if used + tok > hard_budget:
                    break
                sections.append(
                    ContextSection(
                        path=str(meta.get("path") or ""),
                        id=doc_id,
                        section_id=str(sec.get("id") or "body"),
                        text=text,
                        score=score,
                        tokens=tok,
                    )
                )
                used += tok
        if expand_refs:
            # already included via ranking expansion; no-op placeholder
            pass
        return self.compress(sections)

    def compress(self, sections: list[ContextSection]) -> list[ContextSection]:
        seen: set[str] = set()
        out: list[ContextSection] = []
        for s in sections:
            key = f"{s.id}:{s.section_id}"
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out

    def stitch(self, sections: list[ContextSection]) -> str:
        blocks = []
        for s in sections:
            blocks.append(f"<!-- okf:{s.path}#{s.section_id} score={s.score:.3f} -->\n{s.text}")
        return "\n\n".join(blocks)
