"""Redis sharing backend."""

from __future__ import annotations

from threading import RLock

import anyio

from ..interfaces.sharing import IKVSharingBackend


class RedisSharingBackend(IKVSharingBackend):
    def __init__(self, url: str = "redis://localhost:6379/0", *, prefix: str = "kvshare:") -> None:
        self.url = url
        self.prefix = prefix
        self._lock = RLock()
        self._client = None
        self._available = False
        try:
            import redis

            client = redis.Redis.from_url(url, decode_responses=False)
            client.ping()
            self._client = client
            self._available = True
        except Exception:
            self._client = None
            self._available = False

    @property
    def name(self) -> str:
        return "redis"

    def _require(self):
        if not self._available or self._client is None:
            raise RuntimeError(f"Redis sharing backend unavailable at {self.url}")
        return self._client

    def _data(self, key: str) -> bytes:
        return f"{self.prefix}data:{key}".encode("utf-8")

    def _rc(self, key: str) -> bytes:
        return f"{self.prefix}rc:{key}".encode("utf-8")

    def _cons(self, key: str) -> bytes:
        return f"{self.prefix}cons:{key}".encode("utf-8")

    async def store(self, key: str, data: bytes) -> None:
        def _write() -> None:
            client = self._require()
            with self._lock:
                client.set(self._data(key), data)
                client.set(self._rc(key), b"1")
                client.delete(self._cons(key))

        await anyio.to_thread.run_sync(_write)

    async def load(self, key: str) -> bytes:
        def _read() -> bytes:
            client = self._require()
            with self._lock:
                val = client.get(self._data(key))
                if val is None:
                    raise KeyError(key)
                return bytes(val)

        return await anyio.to_thread.run_sync(_read)

    async def share(self, key: str, consumer_id: str) -> str:
        def _share() -> str:
            client = self._require()
            with self._lock:
                if client.get(self._data(key)) is None:
                    raise KeyError(key)
                client.incr(self._rc(key))
                client.sadd(self._cons(key), consumer_id.encode("utf-8"))
                return f"share:{key}:{consumer_id}"

        return await anyio.to_thread.run_sync(_share)

    async def release(self, key: str, consumer_id: str) -> None:
        def _release() -> None:
            client = self._require()
            with self._lock:
                client.srem(self._cons(key), consumer_id.encode("utf-8"))
                remaining = int(client.decr(self._rc(key)))
                if remaining <= 0:
                    client.delete(self._data(key), self._rc(key), self._cons(key))

        await anyio.to_thread.run_sync(_release)

    async def reference_count(self, key: str) -> int:
        def _rc() -> int:
            client = self._require()
            with self._lock:
                val = client.get(self._rc(key))
                return int(val) if val else 0

        return await anyio.to_thread.run_sync(_rc)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            client = self._require()
            with self._lock:
                client.delete(self._data(key), self._rc(key), self._cons(key))

        await anyio.to_thread.run_sync(_delete)
