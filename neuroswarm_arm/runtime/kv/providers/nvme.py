"""NVMe / local disk page provider."""

from __future__ import annotations

from pathlib import Path
from threading import RLock

import anyio

from ..interfaces.provider import IKVProvider
from ..interfaces.types import StorageTier


class NVMeProvider(IKVProvider):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._bytes = 0
        for path in self.root.glob("*.nvme"):
            self._bytes += path.stat().st_size

    def _path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("\\", "_")
        return self.root / f"{safe}.nvme"

    @property
    def name(self) -> str:
        return "nvme"

    @property
    def tier(self) -> StorageTier:
        return StorageTier.L3_NVME

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)

        def _write() -> None:
            with self._lock:
                if path.exists():
                    self._bytes -= path.stat().st_size
                path.write_bytes(data)
                self._bytes += len(data)

        await anyio.to_thread.run_sync(_write)

    async def get(self, key: str) -> bytes:
        path = self._path(key)

        def _read() -> bytes:
            if not path.exists():
                raise KeyError(key)
            return path.read_bytes()

        return await anyio.to_thread.run_sync(_read)

    async def delete(self, key: str) -> None:
        path = self._path(key)

        def _delete() -> None:
            with self._lock:
                if path.exists():
                    self._bytes -= path.stat().st_size
                    path.unlink(missing_ok=True)

        await anyio.to_thread.run_sync(_delete)

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def usage_bytes(self) -> int:
        with self._lock:
            return self._bytes
