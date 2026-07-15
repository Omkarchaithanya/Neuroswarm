"""Memory-mapped file provider (L3)."""

from __future__ import annotations

import os
from pathlib import Path
from threading import RLock

import anyio

from ..interfaces.provider import IKVProvider
from ..interfaces.types import StorageTier


class MemoryMappedProvider(IKVProvider):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._index: dict[str, Path] = {}
        self._bytes = 0
        self._hydrate()

    def _path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("\\", "_")
        return self.root / f"{safe}.kvbin"

    def _hydrate(self) -> None:
        for path in self.root.glob("*.kvbin"):
            key = path.stem
            self._index[key] = path
            self._bytes += path.stat().st_size

    @property
    def name(self) -> str:
        return "mmap"

    @property
    def tier(self) -> StorageTier:
        return StorageTier.L3_MEMORY_MAPPED

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)

        def _write() -> None:
            with self._lock:
                old = self._index.get(key)
                if old is not None and old.exists():
                    self._bytes -= old.stat().st_size
                path.write_bytes(data)
                self._index[key] = path
                self._bytes += len(data)

        await anyio.to_thread.run_sync(_write)

    async def get(self, key: str) -> bytes:
        path = self._path(key)

        def _read() -> bytes:
            with self._lock:
                if not path.exists():
                    raise KeyError(key)
                # Prefer mmap for large files; still return bytes to callers.
                import mmap

                with path.open("rb") as fh:
                    size = os.path.getsize(path)
                    if size == 0:
                        return b""
                    with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                        return bytes(mm)

        return await anyio.to_thread.run_sync(_read)

    async def delete(self, key: str) -> None:
        path = self._path(key)

        def _delete() -> None:
            with self._lock:
                if path.exists():
                    self._bytes -= path.stat().st_size
                    path.unlink(missing_ok=True)
                self._index.pop(key, None)

        await anyio.to_thread.run_sync(_delete)

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def usage_bytes(self) -> int:
        with self._lock:
            return self._bytes
