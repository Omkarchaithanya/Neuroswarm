"""Redis provider (L5)."""

from __future__ import annotations

from threading import RLock

import anyio

from ..interfaces.provider import IKVProvider
from ..interfaces.types import StorageTier


class RedisProvider(IKVProvider):
    def __init__(self, url: str = "redis://localhost:6379/0", *, prefix: str = "kv:") -> None:
        self.url = url
        self.prefix = prefix
        self._lock = RLock()
        self._bytes = 0
        self._client = None
        self._available = False
        self._connect()

    def _connect(self) -> None:
        try:
            import redis
        except ImportError:
            self._client = None
            self._available = False
            return
        try:
            client = redis.Redis.from_url(self.url, decode_responses=False)
            client.ping()
            self._client = client
            self._available = True
        except Exception:
            # Offline / no Redis: keep provider registered but operations raise clearly.
            self._client = None
            self._available = False

    def _key(self, key: str) -> bytes:
        return f"{self.prefix}{key}".encode("utf-8")

    @property
    def name(self) -> str:
        return "redis"

    @property
    def tier(self) -> StorageTier:
        return StorageTier.L5_REDIS

    @property
    def available(self) -> bool:
        return self._available

    def _require(self) -> object:
        if not self._available or self._client is None:
            raise RuntimeError(
                f"Redis provider unavailable at {self.url}; start Redis or choose another tier"
            )
        return self._client

    async def put(self, key: str, data: bytes) -> None:
        def _write() -> None:
            client = self._require()
            with self._lock:
                rkey = self._key(key)
                old = client.get(rkey)
                if old is not None:
                    self._bytes -= len(old)
                client.set(rkey, data)
                self._bytes += len(data)

        await anyio.to_thread.run_sync(_write)

    async def get(self, key: str) -> bytes:
        def _read() -> bytes:
            client = self._require()
            with self._lock:
                val = client.get(self._key(key))
                if val is None:
                    raise KeyError(key)
                return bytes(val)

        return await anyio.to_thread.run_sync(_read)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            client = self._require()
            with self._lock:
                rkey = self._key(key)
                old = client.get(rkey)
                if old is not None:
                    self._bytes -= len(old)
                client.delete(rkey)

        await anyio.to_thread.run_sync(_delete)

    async def exists(self, key: str) -> bool:
        def _exists() -> bool:
            client = self._require()
            with self._lock:
                return bool(client.exists(self._key(key)))

        return await anyio.to_thread.run_sync(_exists)

    def usage_bytes(self) -> int:
        with self._lock:
            return self._bytes
