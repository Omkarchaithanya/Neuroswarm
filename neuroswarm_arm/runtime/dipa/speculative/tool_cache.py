"""Speculative Tool Cache — Nichols et al. 2025, Section 3.

Maps to the paper's "Speculative Tool Cache": JSON-encoded MCP tool results
are keyed by ``sha256(tool_name + ':' + canonical_json(args))[:32]`` so a
later agent step (or a parallel speculative call) can reuse a prior result
without re-invoking the tool. Hit/miss counters and size/hit-rate gauges are
published through the RMF facade (``neuroswarm_arm.metrics``) as
``neuroswarm_tool_cache_{hits,misses,size,hit_rate}``.

Concurrency: ``asyncio.Lock`` serializes get/set on the shared FastAPI event
loop; the cache is safe to hang on ``app.state.tool_cache``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from typing import Any

from neuroswarm_arm.metrics import metrics as _metrics

_METRIC_HITS = "neuroswarm_tool_cache_hits"
_METRIC_MISSES = "neuroswarm_tool_cache_misses"
_METRIC_SIZE = "neuroswarm_tool_cache_size"
_METRIC_HIT_RATE = "neuroswarm_tool_cache_hit_rate"

_HELP = {
    _METRIC_HITS: "Speculative tool-cache hits.",
    _METRIC_MISSES: "Speculative tool-cache misses.",
    _METRIC_SIZE: "Current speculative tool-cache entry count.",
    _METRIC_HIT_RATE: "Speculative tool-cache hit rate (hits / (hits + misses)).",
}


class ToolOutputCache:
    """Bounded LRU+TTL cache for speculative MCP tool outputs."""

    def __init__(self, max_size: int = 1024, ttl_seconds: int = 300) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._store: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
        self._register_metrics()
        self._publish_gauges()

    def _register_metrics(self) -> None:
        _metrics.describe(_METRIC_HITS, "counter", _HELP[_METRIC_HITS])
        _metrics.describe(_METRIC_MISSES, "counter", _HELP[_METRIC_MISSES])
        _metrics.describe(_METRIC_SIZE, "gauge", _HELP[_METRIC_SIZE])
        _metrics.describe(_METRIC_HIT_RATE, "gauge", _HELP[_METRIC_HIT_RATE])
        # Materialize zero-value series so /metrics exposes all four names.
        _metrics.inc(_METRIC_HITS, 0.0)
        _metrics.inc(_METRIC_MISSES, 0.0)

    def _hit_rate(self) -> float:
        total = self._hits + self._misses
        return (self._hits / total) if total else 0.0

    def _publish_gauges(self) -> None:
        _metrics.set(_METRIC_SIZE, float(len(self._store)))
        _metrics.set(_METRIC_HIT_RATE, self._hit_rate())

    def make_key(self, tool_name: str, args: dict) -> str:
        canonical = json.dumps(
            args,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        digest = hashlib.sha256(f"{tool_name}:{canonical}".encode("utf-8")).hexdigest()
        return digest[:32]

    async def get(self, key: str) -> str | None:
        async with self._lock:
            item = self._store.get(key)
            if item is None:
                self._misses += 1
                _metrics.inc(_METRIC_MISSES)
                self._publish_gauges()
                return None
            expires_at, value = item
            if expires_at < time.time():
                self._store.pop(key, None)
                self._misses += 1
                _metrics.inc(_METRIC_MISSES)
                self._publish_gauges()
                return None
            self._store.move_to_end(key)
            self._hits += 1
            _metrics.inc(_METRIC_HITS)
            self._publish_gauges()
            return value

    async def set(self, key: str, value: str) -> None:
        async with self._lock:
            expires_at = time.time() + self._ttl_seconds
            self._store[key] = (expires_at, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)
            self._publish_gauges()

    def metrics(self) -> dict[str, Any]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._store),
            "hit_rate": self._hit_rate(),
        }

    def top_keys(self, limit: int = 20) -> list[str]:
        """MRU-first key list for debug endpoints."""
        keys = list(self._store.keys())
        keys.reverse()
        return keys[: max(0, int(limit))]

    def snapshot(self, *, top_n: int = 20) -> dict[str, Any]:
        out = self.metrics()
        out["top_keys"] = self.top_keys(limit=top_n)
        return out

    async def invalidate(
        self,
        tool: str | None = None,
        args: dict[str, Any] | None = None,
        *,
        all_entries: bool = False,
    ) -> int:
        """Drop one key (tool+args) or clear entire cache. Returns count removed."""
        async with self._lock:
            if all_entries:
                n = len(self._store)
                self._store.clear()
                self._publish_gauges()
                return n
            if not tool:
                return 0
            key = self.make_key(tool, dict(args or {}))
            if key in self._store:
                del self._store[key]
                self._publish_gauges()
                return 1
            return 0
