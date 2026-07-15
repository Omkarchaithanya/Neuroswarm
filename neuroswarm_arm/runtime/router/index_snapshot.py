"""Index snapshot / restore persistence."""

from __future__ import annotations

from pathlib import Path
import json
import shutil
import time
from typing import Any

from .registry import ToolRegistry
from .router_events import RouterEventBus, RouterEventKind
from .router_exceptions import SnapshotError
from .storage import SnapshotStore


class IndexSnapshotManager:
    def __init__(
        self,
        registry: ToolRegistry,
        index: Any,
        *,
        snapshot_dir: Path,
        events: RouterEventBus | None = None,
    ) -> None:
        self.registry = registry
        self.index = index
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.events = events
        self.store = SnapshotStore(self.snapshot_dir)

    def snapshot(self, name: str | None = None) -> Path:
        stamp = name or time.strftime("%Y%m%dT%H%M%S")
        target = self.snapshot_dir / stamp
        try:
            target.mkdir(parents=True, exist_ok=True)
            (target / "registry.json").write_text(
                json.dumps(self.registry.to_dict(), indent=2),
                encoding="utf-8",
            )
            self.index.snapshot(target / "index")
            meta = {
                "name": stamp,
                "tools": self.registry.size(),
                "index_size": self.index.size(),
                "backend": getattr(self.index, "backend_name", "unknown"),
                "created_at": time.time(),
            }
            (target / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            self.store.remember(stamp, target)
            if self.events:
                self.events.emit(RouterEventKind.SNAPSHOT, path=str(target), **meta)
            return target
        except Exception as exc:
            raise SnapshotError(str(exc)) from exc

    def restore(self, name_or_path: str) -> dict[str, object]:
        path = Path(name_or_path)
        if not path.exists():
            path = self.snapshot_dir / name_or_path
        if not path.exists():
            raise SnapshotError(f"snapshot not found: {name_or_path}")
        try:
            registry_data = json.loads((path / "registry.json").read_text(encoding="utf-8"))
            self.registry.clear()
            from .models import ToolRecord

            for item in registry_data.values():
                self.registry.register(ToolRecord.from_dict(item))
            self.index.restore(path / "index")
            meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
            if self.events:
                self.events.emit(RouterEventKind.RESTORE, path=str(path), tools=self.registry.size())
            return {"path": str(path), "tools": self.registry.size(), "meta": meta}
        except Exception as exc:
            raise SnapshotError(str(exc)) from exc

    def list_snapshots(self) -> list[dict[str, object]]:
        return self.store.list()

    def delete_snapshot(self, name: str) -> bool:
        path = self.snapshot_dir / name
        if not path.exists():
            return False
        shutil.rmtree(path, ignore_errors=True)
        self.store.forget(name)
        return True
