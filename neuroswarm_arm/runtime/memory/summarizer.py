"""Summarization helpers for memory content."""

from __future__ import annotations

from neuroswarm_arm.runtime.memory.schemas import MemoryRecord


class Summarizer:
    def summarize(self, text: str, *, max_chars: int = 240) -> str:
        cleaned = " ".join((text or "").split())
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[: max_chars - 3].rstrip() + "..."

    def summarize_record(self, record: MemoryRecord, *, max_chars: int = 240) -> MemoryRecord:
        record.summary = self.summarize(record.content, max_chars=max_chars)
        return record

    def hierarchical(self, texts: list[str], *, max_chars: int = 400) -> str:
        parts = [self.summarize(t, max_chars=120) for t in texts if t]
        return self.summarize(" | ".join(parts), max_chars=max_chars)
