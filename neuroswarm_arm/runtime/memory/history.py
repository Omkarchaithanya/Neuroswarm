"""Local metadata history index (side-car to provider store)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from neuroswarm_arm.runtime.memory.schemas import MemoryRecord


class HistoryIndex:
    """Persists lightweight metadata for lifecycle ops independent of Mem0 ADD-only store."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._rows: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._rows = data
        except (OSError, json.JSONDecodeError):
            self._rows = {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._rows, indent=2), encoding="utf-8")

    def upsert(self, record: MemoryRecord) -> None:
        with self._lock:
            self._rows[record.uuid] = {
                "uuid": record.uuid,
                "owner": record.owner,
                "namespace": record.namespace,
                "type": record.type.value,
                "importance": record.importance,
                "archived": record.archived,
                "ttl_seconds": record.ttl_seconds,
                "provider_id": record.provider_id,
                "timestamp": record.timestamp.isoformat(),
                "access_count": record.access_count,
            }
            self._save()

    def mark_archived(self, memory_id: str) -> None:
        with self._lock:
            if memory_id in self._rows:
                self._rows[memory_id]["archived"] = True
                self._save()

    def get(self, memory_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._rows.get(memory_id)

    def all_for_owner(self, owner: str) -> list[dict[str, Any]]:
        with self._lock:
            return [r for r in self._rows.values() if r.get("owner") == owner]
