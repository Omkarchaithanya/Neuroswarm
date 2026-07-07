from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass
class MemoryRecord:
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


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

