"""Deprecated Mem0Fallback shim → Cognitive Memory Runtime.

Prefer ``neuroswarm_arm.runtime.memory.build_memory_runtime``.
``mem0ai`` is never imported here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neuroswarm_arm.runtime.memory.api import NeuroMemory
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig, load_memory_config
from neuroswarm_arm.runtime.memory.factory import build_memory_runtime


@dataclass
class MemoryRecord:
    """Legacy record shape retained for older callers."""

    text: str
    metadata: dict[str, str] = field(default_factory=dict)


class Mem0Fallback:
    """Back-compat adapter: ``add`` / ``search`` delegate to ``NeuroMemory``."""

    def __init__(self, root: Path, memory: NeuroMemory | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._memory = memory or build_memory_runtime(self.root)

    @property
    def neuro(self) -> NeuroMemory:
        return self._memory

    def add(self, agent_id: str, fact: str, metadata: dict[str, str] | None = None) -> None:
        self._memory.add(agent_id, fact, metadata)

    def search(self, agent_id: str, query: str, limit: int = 5) -> list[str]:
        return self._memory.search_texts(agent_id, query, limit=limit)


def build_memory(
    root: Path,
    *,
    config: MemoryRuntimeConfig | None = None,
) -> Mem0Fallback:
    """Legacy factory used by ``main.py`` / HistoryRanker."""
    cfg = config or load_memory_config(Path(root))
    neuro = build_memory_runtime(config=cfg)
    return Mem0Fallback(root=Path(root), memory=neuro)
