"""Compression — merge duplicates, prune low-importance, archive."""

from __future__ import annotations

from neuroswarm_arm.runtime.memory.embeddings import cosine, hash_embed
from neuroswarm_arm.runtime.memory.schemas import MemoryRecord
from neuroswarm_arm.runtime.memory.summarizer import Summarizer


class CompressionEngine:
    def __init__(self, summarizer: Summarizer | None = None, *, similarity_threshold: float = 0.92) -> None:
        self.summarizer = summarizer or Summarizer()
        self.similarity_threshold = similarity_threshold

    def find_duplicates(self, records: list[MemoryRecord]) -> list[tuple[MemoryRecord, MemoryRecord]]:
        pairs: list[tuple[MemoryRecord, MemoryRecord]] = []
        embeddings = [(r, r.embedding or hash_embed(r.content)) for r in records]
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                a, ea = embeddings[i]
                b, eb = embeddings[j]
                if cosine(ea, eb) >= self.similarity_threshold:
                    pairs.append((a, b))
        return pairs

    def merge(self, a: MemoryRecord, b: MemoryRecord) -> MemoryRecord:
        primary, secondary = (a, b) if a.importance >= b.importance else (b, a)
        merged_content = self.summarizer.hierarchical([primary.content, secondary.content])
        primary.content = merged_content
        primary.summary = self.summarizer.summarize(merged_content)
        primary.access_count += secondary.access_count
        primary.importance = max(primary.importance, secondary.importance)
        primary.relationships = list({*primary.relationships, secondary.uuid, *secondary.relationships})
        primary.tags = list({*primary.tags, *secondary.tags, "merged"})
        primary.version += 1
        return primary

    def prune(self, records: list[MemoryRecord], *, keep: int = 100) -> list[MemoryRecord]:
        ordered = sorted(records, key=lambda r: (r.importance, r.access_count), reverse=True)
        return ordered[:keep]
