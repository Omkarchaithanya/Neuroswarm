"""In-process adjacency index — DEPRECATED as Mem0 graph substitute.

Official Mem0 v3 provides built-in entity linking inside the vector store
(``{collection}_entities``). Do NOT use this module as primary graph memory.

Kept only for optional local relationship bookkeeping on MemoryRecord.uuid links.
Prefer Mem0 hybrid search entity boost.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable
import warnings

from neuroswarm_arm.runtime.memory.schemas import MemoryRecord

_WARNED = False


class MemoryGraph:
    """Deprecated local graph. Prefer Mem0 entity linking."""

    def __init__(self) -> None:
        global _WARNED
        if not _WARNED:
            warnings.warn(
                "MemoryGraph is deprecated; use Mem0 entity linking via Mem0Adapter.search",
                DeprecationWarning,
                stacklevel=2,
            )
            _WARNED = True
        self._adj: dict[str, set[str]] = defaultdict(set)
        self._entities: dict[str, set[str]] = defaultdict(set)

    def index(self, record: MemoryRecord) -> None:
        for rel in record.relationships:
            self._adj[record.uuid].add(rel)
            self._adj[rel].add(record.uuid)
        for tag in record.tags:
            self._entities[tag.lower()].add(record.uuid)

    def expand(self, memory_ids: Iterable[str], *, depth: int = 1) -> set[str]:
        frontier = set(memory_ids)
        seen = set(frontier)
        for _ in range(max(0, depth)):
            nxt: set[str] = set()
            for mid in frontier:
                nxt |= self._adj.get(mid, set())
            nxt -= seen
            seen |= nxt
            frontier = nxt
            if not frontier:
                break
        return seen

    def by_entity(self, entity: str) -> set[str]:
        return set(self._entities.get(entity.lower(), set()))
