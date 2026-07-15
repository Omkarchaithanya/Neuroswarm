"""In-memory L1 RAM provider."""

from __future__ import annotations

from threading import RLock

from ..interfaces.provider import IKVProvider
from ..interfaces.types import StorageTier


class RAMProvider(IKVProvider):
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self._lock = RLock()
        self._bytes = 0

    @property
    def name(self) -> str:
        return "ram"

    @property
    def tier(self) -> StorageTier:
        return StorageTier.L1_RAM

    async def put(self, key: str, data: bytes) -> None:
        with self._lock:
            old = self._store.get(key)
            if old is not None:
                self._bytes -= len(old)
            self._store[key] = data
            self._bytes += len(data)

    async def get(self, key: str) -> bytes:
        with self._lock:
            if key not in self._store:
                raise KeyError(key)
            return self._store[key]

    async def delete(self, key: str) -> None:
        with self._lock:
            old = self._store.pop(key, None)
            if old is not None:
                self._bytes -= len(old)

    async def exists(self, key: str) -> bool:
        with self._lock:
            return key in self._store

    def usage_bytes(self) -> int:
        with self._lock:
            return self._bytes
