"""Compressed RAM (L2) provider — compresses cold-bound payloads in memory."""

from __future__ import annotations

from threading import RLock

from ..compression import IKVCompression, NoneCompression
from ..interfaces.provider import IKVProvider
from ..interfaces.types import StorageTier


class CompressedRAMProvider(IKVProvider):
    def __init__(self, compression: IKVCompression | None = None) -> None:
        self._compression = compression or NoneCompression()
        self._store: dict[str, bytes] = {}
        self._raw_sizes: dict[str, int] = {}
        self._lock = RLock()
        self._bytes = 0

    @property
    def name(self) -> str:
        return "compressed_ram"

    @property
    def tier(self) -> StorageTier:
        return StorageTier.L2_COMPRESSED_RAM

    @property
    def compression_name(self) -> str:
        return self._compression.name

    async def put(self, key: str, data: bytes) -> None:
        compressed = self._compression.compress(data)
        with self._lock:
            old = self._store.get(key)
            if old is not None:
                self._bytes -= len(old)
            self._store[key] = compressed
            self._raw_sizes[key] = len(data)
            self._bytes += len(compressed)

    async def get(self, key: str) -> bytes:
        with self._lock:
            if key not in self._store:
                raise KeyError(key)
            compressed = self._store[key]
        return self._compression.decompress(compressed)

    async def delete(self, key: str) -> None:
        with self._lock:
            old = self._store.pop(key, None)
            self._raw_sizes.pop(key, None)
            if old is not None:
                self._bytes -= len(old)

    async def exists(self, key: str) -> bool:
        with self._lock:
            return key in self._store

    def usage_bytes(self) -> int:
        with self._lock:
            return self._bytes

    def compression_ratio(self) -> float:
        with self._lock:
            raw = sum(self._raw_sizes.values()) or 1
            return float(raw) / float(max(1, self._bytes))
