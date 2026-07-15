<<<<<<< HEAD
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
=======
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84


@dataclass
class MemoryRecord:
<<<<<<< HEAD
    """Legacy record shape retained for older callers."""

=======
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


<<<<<<< HEAD
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
=======
@dataclass
class Mem0Fallback:
    root: Path
    _store: dict[str, list[MemoryRecord]] = field(default_factory=dict)

    def add(self, agent_id: str, fact: str, metadata: dict[str, str] | None = None) -> None:
        self._store.setdefault(agent_id, []).append(MemoryRecord(fact, metadata or {}))
        self._persist(agent_id)

    def search(self, agent_id: str, query: str, limit: int = 5) -> list[str]:
        records = self._store.get(agent_id, [])
        tokens = set(query.lower().split())
        scored = []
        for rec in records:
            score = sum(1 for t in tokens if t in rec.text.lower())
            scored.append((score, rec.text))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for score, text in scored[:limit] if score >= 0]

    def _persist(self, agent_id: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = [r.__dict__ for r in self._store.get(agent_id, [])]
        (self.root / f"{agent_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_memory(root: Path) -> Mem0Fallback:
    mem = Mem0Fallback(root=root)
    for file in root.glob("*.json"):
        data = json.loads(file.read_text(encoding="utf-8"))
        agent_id = file.stem
        mem._store[agent_id] = [MemoryRecord(**item) for item in data]
    return mem

>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
