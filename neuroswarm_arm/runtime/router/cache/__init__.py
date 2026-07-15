"""Shared cache primitives."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import threading
import time
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class CacheEntry(Generic[T]):
    value: T
    expires_at: float
    checksum: str = ""


class MemoryLRUCache(Generic[T]):
    def __init__(self, max_entries: int = 10_000, ttl_s: float = 3600.0) -> None:
        self.max_entries = max_entries
        self.ttl_s = ttl_s
        self._data: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> T | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            if entry.expires_at < time.time():
                self._data.pop(key, None)
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return entry.value

    def set(self, key: str, value: T, *, checksum: str = "", ttl_s: float | None = None) -> None:
        with self._lock:
            ttl = self.ttl_s if ttl_s is None else ttl_s
            self._data[key] = CacheEntry(value=value, expires_at=time.time() + ttl, checksum=checksum)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._data)

    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class DiskCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def get(self, key: str) -> Any | None:
        path = self._path(key)
        with self._lock:
            if not path.exists():
                return None
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("expires_at", 0) < time.time():
                    path.unlink(missing_ok=True)
                    return None
                return payload.get("value")
            except Exception:
                return None

    def set(self, key: str, value: Any, *, ttl_s: float = 3600.0, checksum: str = "") -> None:
        path = self._path(key)
        payload = {
            "value": value,
            "expires_at": time.time() + ttl_s,
            "checksum": checksum,
            "key": key,
        }
        with self._lock:
            path.write_text(json.dumps(payload), encoding="utf-8")

    def invalidate(self, key: str) -> None:
        path = self._path(key)
        with self._lock:
            path.unlink(missing_ok=True)

    def clear(self) -> None:
        with self._lock:
            for path in self.root.glob("*.json"):
                path.unlink(missing_ok=True)

    def size(self) -> int:
        return sum(1 for _ in self.root.glob("*.json"))


class RedisCache:
    def __init__(self, url: str, *, prefix: str = "nsa:router:emb:") -> None:
        self.url = url
        self.prefix = prefix
        self._client = None
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(url, decode_responses=True)
            client.ping()
            self._client = client
        except Exception:
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def get(self, key: str) -> Any | None:
        if self._client is None:
            return None
        try:
            raw = self._client.get(self.prefix + key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            return None

    def set(self, key: str, value: Any, *, ttl_s: float = 3600.0) -> None:
        if self._client is None:
            return
        try:
            self._client.setex(self.prefix + key, int(ttl_s), json.dumps(value))
        except Exception:
            pass

    def invalidate(self, key: str) -> None:
        if self._client is None:
            return
        try:
            self._client.delete(self.prefix + key)
        except Exception:
            pass

    def clear(self) -> None:
        if self._client is None:
            return
        try:
            for key in self._client.scan_iter(self.prefix + "*"):
                self._client.delete(key)
        except Exception:
            pass

    def size(self) -> int:
        if self._client is None:
            return 0
        try:
            return sum(1 for _ in self._client.scan_iter(self.prefix + "*"))
        except Exception:
            return 0
