"""MemoryBundle / KnowledgeBundle IRs — retrieval outputs before compression."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MemoryItem:
    content: str
    memory_id: str = ""
    namespace: str = ""
    memory_type: str = ""
    score: float = 0.0
    importance: float = 0.5
    confidence: float = 0.8
    signals: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    tokens: int = 0


@dataclass(slots=True)
class KnowledgeItem:
    content: str
    path: str = ""
    section_id: str = ""
    score: float = 0.0
    kind: str = "knowledge"  # knowledge | tool_docs | policy
    tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MemoryBundle:
    request_id: str = ""
    items: list[MemoryItem] = field(default_factory=list)
    source_step_ids: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return sum(i.tokens or max(1, len(i.content.split())) for i in self.items)


@dataclass(slots=True)
class KnowledgeBundle:
    request_id: str = ""
    items: list[KnowledgeItem] = field(default_factory=list)
    source_step_ids: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return sum(i.tokens or max(1, len(i.content.split())) for i in self.items)
