"""In-process / shared-memory sharing backend."""

from __future__ import annotations

from multiprocessing import shared_memory
from threading import RLock
from typing import Any

import anyio

from ..interfaces.sharing import IKVSharingBackend
from ..utils.hashing import stable_id
from ..utils.locks import RefCountedLock


class SharedMemoryBackend(IKVSharingBackend):
    """Uses multiprocessing.shared_memory when available; falls back to process RAM."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._meta: dict[str, dict[str, Any]] = {}
        self._fallback: dict[str, bytes] = {}
        self._refs: dict[str, RefCountedLock] = {}
        self._consumers: dict[str, set[str]] = {}

    @property
    def name(self) -> str:
        return "shm"

    async def store(self, key: str, data: bytes) -> None:
        def _store() -> None:
            with self._lock:
                self._cleanup_key(key)
                name = f"nsa_kv_{stable_id('shm')}"
                try:
                    shm = shared_memory.SharedMemory(create=True, size=max(1, len(data)), name=name)
                    shm.buf[: len(data)] = data
                    self._meta[key] = {"name": name, "size": len(data), "shm": shm}
                except Exception:
                    self._fallback[key] = data
                    self._meta[key] = {"name": None, "size": len(data), "shm": None}
                self._refs[key] = RefCountedLock(1)
                self._consumers[key] = set()

        await anyio.to_thread.run_sync(_store)

    async def load(self, key: str) -> bytes:
        def _load() -> bytes:
            with self._lock:
                if key not in self._meta:
                    raise KeyError(key)
                meta = self._meta[key]
                shm = meta.get("shm")
                if shm is not None:
                    return bytes(shm.buf[: meta["size"]])
                if key in self._fallback:
                    return self._fallback[key]
                raise KeyError(key)

        return await anyio.to_thread.run_sync(_load)

    async def share(self, key: str, consumer_id: str) -> str:
        with self._lock:
            if key not in self._refs:
                raise KeyError(key)
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
                self._cleanup_key(key)

    async def reference_count(self, key: str) -> int:
        with self._lock:
            if key not in self._refs:
                return 0
            return self._refs[key].count

    async def delete(self, key: str) -> None:
        with self._lock:
            self._cleanup_key(key)

    def _cleanup_key(self, key: str) -> None:
        meta = self._meta.pop(key, None)
        self._fallback.pop(key, None)
        self._refs.pop(key, None)
        self._consumers.pop(key, None)
        if meta and meta.get("shm") is not None:
            shm = meta["shm"]
            try:
                shm.close()
                shm.unlink()
            except Exception:
                pass
