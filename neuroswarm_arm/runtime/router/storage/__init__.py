"""Snapshot store helpers."""

from __future__ import annotations

from pathlib import Path
import json
import time


class SnapshotStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "snapshots_index.json"
        self._index: dict[str, dict] = {}
        if self._index_path.exists():
            try:
                self._index = json.loads(self._index_path.read_text(encoding="utf-8"))
            except Exception:
                self._index = {}

    def remember(self, name: str, path: Path) -> None:
        self._index[name] = {"path": str(path), "ts": time.time()}
        self._flush()

    def forget(self, name: str) -> None:
        self._index.pop(name, None)
        self._flush()

    def list(self) -> list[dict[str, object]]:
        items = []
        for name, meta in sorted(self._index.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True):
            items.append({"name": name, **meta})
        # Also discover directories
        for child in self.root.iterdir():
            if child.is_dir() and (child / "meta.json").exists() and child.name not in self._index:
                items.append({"name": child.name, "path": str(child), "ts": child.stat().st_mtime})
        return items

    def _flush(self) -> None:
        self._index_path.write_text(json.dumps(self._index, indent=2), encoding="utf-8")
