"""Query / selection / metadata cache with invalidation."""

from __future__ import annotations

import threading
import time
from typing import Any, Hashable


class RegistryCache:
    """Simple TTL + explicit-invalidation cache for registry queries."""

    def __init__(self, *, default_ttl_s: float | None = 30.0, max_entries: int = 2048) -> None:
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
            ttl = self._default_ttl if ttl_s is None else ttl_s
            expires = None if ttl is None else time.monotonic() + ttl
            if len(self._store) >= self._max_entries:
                # drop arbitrary oldest-ish: first key
                try:
                    first = next(iter(self._store))
                    del self._store[first]
                except StopIteration:
                    pass
            self._store[self._key(namespace, key)] = (value, expires)

    def invalidate(self, namespace: str | None = None) -> int:
        """Invalidate one namespace or entire cache. Returns removed count."""
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

    def invalidate_all(self) -> int:
        return self.invalidate(None)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
            }

    def clear_stats(self) -> None:
        with self._lock:
            self._hits = 0
            self._misses = 0
