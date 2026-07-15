"""Memory-mapped file sharing backend."""

from __future__ import annotations

from pathlib import Path
from threading import RLock

import anyio

from ..interfaces.sharing import IKVSharingBackend
from ..utils.locks import RefCountedLock


class MemoryMappedSharingBackend(IKVSharingBackend):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._refs: dict[str, RefCountedLock] = {}
        self._consumers: dict[str, set[str]] = {}

    def _path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("\\", "_")
        return self.root / f"{safe}.share"

    @property
    def name(self) -> str:
        return "mmap"

    async def store(self, key: str, data: bytes) -> None:
        path = self._path(key)

        def _write() -> None:
            with self._lock:
                path.write_bytes(data)
                self._refs[key] = RefCountedLock(1)
                self._consumers[key] = set()

        await anyio.to_thread.run_sync(_write)

    async def load(self, key: str) -> bytes:
        path = self._path(key)

        def _read() -> bytes:
            if not path.exists():
                raise KeyError(key)
            return path.read_bytes()

        return await anyio.to_thread.run_sync(_read)

    async def share(self, key: str, consumer_id: str) -> str:
        with self._lock:
            if key not in self._refs:
                if not self._path(key).exists():
                    raise KeyError(key)
                self._refs[key] = RefCountedLock(1)
            self._refs[key].acquire_ref()
            self._consumers.setdefault(key, set()).add(consumer_id)
            return f"share:{key}:{consumer_id}"

    async def release(self, key: str, consumer_id: str) -> None:
        with self._lock:
            if key not in self._refs:
                return
            self._consumers.get(key, set()).discard(consumer_id)
            remaining = self._refs[key].release_ref()
            if remaining == 0:
                self._path(key).unlink(missing_ok=True)
                self._refs.pop(key, None)
                self._consumers.pop(key, None)

    async def reference_count(self, key: str) -> int:
        with self._lock:
            return self._refs[key].count if key in self._refs else 0

    async def delete(self, key: str) -> None:
        with self._lock:
            self._path(key).unlink(missing_ok=True)
            self._refs.pop(key, None)
            self._consumers.pop(key, None)
