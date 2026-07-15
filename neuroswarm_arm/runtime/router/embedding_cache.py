"""Multi-tier embedding cache: memory LRU+TTL, Redis, disk."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
from typing import Any

import numpy as np

from .cache import DiskCache, MemoryLRUCache, RedisCache
from .router_metrics import RouterMetrics


def _text_key(model: str, text: str, version: str = "v1") -> str:
    digest = hashlib.sha256(f"{model}|{version}|{text}".encode("utf-8")).hexdigest()
    return digest


class EmbeddingCache:
    def __init__(
        self,
        *,
        backend: str = "memory",
        redis_url: str = "redis://localhost:6379/1",
        disk_dir: Path | None = None,
        max_entries: int = 10_000,
        ttl_s: float = 3600.0,
        metrics: RouterMetrics | None = None,
        model_version: str = "v1",
    ) -> None:
        self.backend = backend.lower()
        self.model_version = model_version
        self.ttl_s = ttl_s
        self.metrics = metrics
        self.memory = MemoryLRUCache[list[float]](max_entries=max_entries, ttl_s=ttl_s)
        self.disk = DiskCache(disk_dir or Path("work/router/cache"))
        self.redis = RedisCache(redis_url) if self.backend in {"redis", "all"} else None
        if self.redis is not None and not self.redis.available:
            self.redis = None

    def get(self, model: str, text: str) -> np.ndarray | None:
        key = _text_key(model, text, self.model_version)
        value = self.memory.get(key)
        if value is not None:
            if self.metrics:
                self.metrics.observe_cache(True)
            return np.asarray(value, dtype=np.float32)
        if self.redis is not None:
            remote = self.redis.get(key)
            if remote is not None:
                self.memory.set(key, remote, ttl_s=self.ttl_s)
                if self.metrics:
                    self.metrics.observe_cache(True)
                return np.asarray(remote, dtype=np.float32)
        if self.backend in {"disk", "all", "memory"}:
            disk_val = self.disk.get(key)
            if disk_val is not None:
                self.memory.set(key, disk_val, ttl_s=self.ttl_s)
                if self.metrics:
                    self.metrics.observe_cache(True)
                return np.asarray(disk_val, dtype=np.float32)
        if self.metrics:
            self.metrics.observe_cache(False)
        return None

    def set(self, model: str, text: str, vector: np.ndarray) -> None:
        key = _text_key(model, text, self.model_version)
        payload = np.asarray(vector, dtype=np.float32).reshape(-1).tolist()
        checksum = hashlib.sha256(json.dumps(payload).encode("utf-8")).hexdigest()[:16]
        self.memory.set(key, payload, checksum=checksum, ttl_s=self.ttl_s)
        if self.redis is not None:
            self.redis.set(key, payload, ttl_s=self.ttl_s)
        if self.backend in {"disk", "all", "memory"}:
            self.disk.set(key, payload, ttl_s=self.ttl_s, checksum=checksum)
        if self.metrics:
            self.metrics.set("router_embedding_cache_size", float(self.size()))

    def invalidate_version(self, new_version: str) -> None:
        self.model_version = new_version
        self.memory.clear()
        self.disk.clear()
        if self.redis is not None:
            self.redis.clear()

    def warm(self, items: list[tuple[str, str, np.ndarray]]) -> int:
        for model, text, vector in items:
            self.set(model, text, vector)
        return len(items)

    def size(self) -> int:
        return self.memory.size()

    def stats(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "memory_size": self.memory.size(),
            "disk_size": self.disk.size(),
            "redis_available": bool(self.redis and self.redis.available),
            "hit_ratio": self.memory.hit_ratio(),
            "model_version": self.model_version,
        }
