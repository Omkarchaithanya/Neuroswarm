"""Provider protocol for Cognitive Memory Runtime backends."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from neuroswarm_arm.runtime.memory.schemas import MemoryRecord, SearchHit, SearchQuery


@runtime_checkable
class IMemoryProvider(Protocol):
    """Hexagonal port — Mem0 / JSON / future backends."""

    name: str

    def add(self, record: MemoryRecord) -> MemoryRecord:
        """Persist a memory (ADD-only semantics)."""
        ...

    def add_messages(
        self,
        messages: str | list[dict[str, str]],
        *,
        owner: str,
        agent_id: str = "",
        run_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        """Extract + store from conversation messages (provider may use LLM)."""
        ...

    def search(self, query: SearchQuery) -> list[SearchHit]:
        ...

    def get(self, memory_id: str) -> MemoryRecord | None:
        ...

    def delete(self, memory_id: str) -> bool:
        ...

    def list_ids(self, *, owner: str = "", namespace: str = "") -> list[str]:
        ...

    def health(self) -> dict[str, Any]:
        ...
