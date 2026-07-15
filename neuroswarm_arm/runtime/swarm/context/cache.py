"""Snapshot / metadata / diff / merge caches."""

from __future__ import annotations

import threading
import time
from typing import Any, Hashable

from .exceptions import CacheError


class ContextCache:
    """Bounded TTL cache for snapshot, metadata, diff, and merge results."""

    NS_SNAPSHOT = "snapshot"
    NS_METADATA = "metadata"
    NS_DIFF = "diff"
    NS_MERGE = "merge"

    def __init__(self, *, default_ttl_s: float | None = 60.0, max_entries: int = 2048) -> None:
        self._default_ttl = default_ttl_s
        self._max_entries = max_entries
        self._lock = threading.RLock()
        self._store: dict[str, tuple[Any, float | None]] = {}
        self._hits = 0
        self._misses = 0

    def _key(self, namespace: str, key: Hashable) -> str:
        return f"{namespace}:{key}"

    def get(self, namespace: str, key: Hashable) -> Any | None:
        with self._lock:
            k = self._key(namespace, key)
            item = self._store.get(k)
            if item is None:
                self._misses += 1
                return None
            value, expires = item
            if expires is not None and time.monotonic() > expires:
                del self._store[k]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(
        self,
        namespace: str,
        key: Hashable,
        value: Any,
        *,
        ttl_s: float | None = None,
    ) -> None:
        with self._lock:
            if self._max_entries < 1:
                raise CacheError("max_entries must be >= 1")
            ttl = self._default_ttl if ttl_s is None else ttl_s
            expires = None if ttl is None else time.monotonic() + ttl
            if len(self._store) >= self._max_entries:
                try:
                    first = next(iter(self._store))
                    del self._store[first]
                except StopIteration:
                    pass
            self._store[self._key(namespace, key)] = (value, expires)

    def invalidate(self, namespace: str | None = None) -> int:
        with self._lock:
            if namespace is None:
                n = len(self._store)
                self._store.clear()
                return n
            prefix = f"{namespace}:"
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
            return len(keys)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
            }
