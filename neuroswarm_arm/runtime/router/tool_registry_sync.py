"""OKF filesystem watch + hot reload + MCP metadata sync."""

from __future__ import annotations

from pathlib import Path
import hashlib
import threading
import time
from typing import Callable

from .incremental_index import IncrementalIndexer
from .registry import ToolRegistry
from .registry_loader import RegistryLoader
from .router_events import RouterEventBus, RouterEventKind
from .router_exceptions import RegistrySyncError


class ToolRegistrySync:
    def __init__(
        self,
        registry: ToolRegistry,
        indexer: IncrementalIndexer,
        *,
        roots: list[Path],
        events: RouterEventBus | None = None,
        interval_s: float = 5.0,
        enabled: bool = True,
    ) -> None:
        self.registry = registry
        self.indexer = indexer
        self.roots = [Path(r) for r in roots]
        self.events = events or registry.events
        self.interval_s = interval_s
        self.enabled = enabled
        self.loader = RegistryLoader()
        self._fingerprints: dict[str, str] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._on_change: list[Callable[[], None]] = []

    def on_change(self, callback: Callable[[], None]) -> None:
        self._on_change.append(callback)

    def fingerprint(self, path: Path) -> str:
        try:
            data = path.read_bytes()
            stat = path.stat()
            return hashlib.sha256(data).hexdigest() + f":{stat.st_mtime_ns}"
        except Exception as exc:
            raise RegistrySyncError(str(exc)) from exc

    def scan(self) -> dict[str, object]:
        loaded = 0
        updated = 0
        removed = 0
        seen_ids: set[str] = set()
        current_files: dict[str, Path] = {}
        for root in self.roots:
            if not root.exists():
                continue
            for path in list(root.rglob("okf-metadata.yaml")) + list(root.rglob("*.tool.yaml")) + list(
                root.rglob("*.tool.json")
            ) + list(root.rglob("*.tool.md")):
                current_files[str(path)] = path
        for path_str, path in current_files.items():
            fp = self.fingerprint(path)
            tool = self.loader.load_file(path)
            seen_ids.add(tool.id)
            prev = self._fingerprints.get(path_str)
            if prev != fp:
                self.registry.register(tool)
                self.indexer.upsert(tool)
                self._fingerprints[path_str] = fp
                if prev is None:
                    loaded += 1
                else:
                    updated += 1
        # Remove tools that disappeared from watched roots (only those with okf_path)
        for tool in list(self.registry.as_list()):
            if tool.okf_path and tool.okf_path not in current_files and tool.id not in seen_ids:
                # only auto-remove if path was under a watched root
                under_root = any(str(tool.okf_path).startswith(str(r)) for r in self.roots)
                if under_root:
                    try:
                        self.registry.remove(tool.id)
                        self.indexer.remove(tool.id)
                        removed += 1
                    except Exception:
                        pass
        # Drop fingerprints for deleted files
        for path_str in list(self._fingerprints):
            if path_str not in current_files:
                self._fingerprints.pop(path_str, None)
        result = {"loaded": loaded, "updated": updated, "removed": removed, "tracked_files": len(current_files)}
        if loaded or updated or removed:
            self.events.emit(RouterEventKind.RELOAD, **result)
            for cb in self._on_change:
                try:
                    cb()
                except Exception:
                    pass
        return result

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="router-okf-sync", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan()
            except Exception:
                pass
            self._stop.wait(self.interval_s)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
