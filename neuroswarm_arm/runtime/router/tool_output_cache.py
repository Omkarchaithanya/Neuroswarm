"""Tool-output cache for the speculative tool-calling layer.

Key: ``sha256(f"{tool_id}|{canonical_json(args)}")[:32]``.
Backend: in-process LRU+TTL by default; ``redis.asyncio`` when
``NSA_TOOL_CACHE_REDIS_URL`` / ``redis_url`` is set.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any

try:
    from cachetools import LRUCache as _LRUCache
except ImportError:  # pragma: no cover
    _LRUCache = None  # type: ignore[misc, assignment]

try:
    from neuroswarm_arm.metrics.bridges import PlaneMetricBridge as _PlaneMetricBridge
except Exception:  # pragma: no cover
    _PlaneMetricBridge = None  # type: ignore[misc, assignment]

_DEFAULT_MAX = int(os.getenv("NSA_TOOL_CACHE_MAX", "10000") or "10000")
_DEFAULT_TTL = float(os.getenv("NSA_TOOL_CACHE_TTL", "600") or "600")
_DEFAULT_NEG_TTL = float(os.getenv("NSA_TOOL_CACHE_NEG_TTL", "30") or "30")
_DEFAULT_REDIS = (os.getenv("NSA_TOOL_CACHE_REDIS_URL", "") or "").strip() or None

_METRIC_HITS = "neuroswarm_tool_output_cache_hits_total"
_METRIC_MISSES = "neuroswarm_tool_output_cache_misses_total"
_METRIC_EVICTIONS = "neuroswarm_tool_output_cache_evictions_total"


def canonical_json(value: Any) -> str:
    """Sort keys recursively; raise ValueError on non-JSON-serializable values."""

    def _normalize(obj: Any) -> Any:
        if obj is None or isinstance(obj, bool):
            return obj
        if isinstance(obj, (int, str)):
            return obj
        if isinstance(obj, float):
            if obj != obj or obj in (float("inf"), float("-inf")):  # NaN / Inf
                raise ValueError(f"non-JSON-serializable float: {obj!r}")
            return obj
        if isinstance(obj, dict):
            try:
                keys = sorted(obj.keys(), key=lambda k: k if isinstance(k, str) else json.dumps(k))
            except TypeError as exc:
                raise ValueError(f"non-JSON-serializable dict key: {exc}") from exc
            out: dict[Any, Any] = {}
            for key in keys:
                if not isinstance(key, (str, int, float, bool)) and key is not None:
                    raise ValueError(f"non-JSON-serializable dict key type: {type(key)!r}")
                out[key] = _normalize(obj[key])
            return out
        if isinstance(obj, (list, tuple)):
            return [_normalize(item) for item in obj]
        raise ValueError(f"non-JSON-serializable value of type {type(obj)!r}")

    normalized = _normalize(value)
    try:
        return json.dumps(normalized, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-JSON-serializable value: {exc}") from exc


def _is_negative_result(result: dict[str, Any]) -> bool:
    if result.get("ok") is False:
        return True
    err = result.get("error")
    return bool(err)


def _make_key(tool_id: str, args: Any) -> str:
    digest = hashlib.sha256(f"{tool_id}|{canonical_json(args)}".encode("utf-8")).hexdigest()
    return digest[:32]


class _OrderedLRU(OrderedDict):
    """OrderedDict stand-in when cachetools is unavailable (eviction owned by put)."""

    def __init__(self, maxsize: int) -> None:
        super().__init__()
        self.maxsize = maxsize

    def __setitem__(self, key: Any, value: Any) -> None:  # type: ignore[override]
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)


def _new_lru(max_entries: int) -> Any:
    if _LRUCache is not None:
        return _LRUCache(maxsize=max_entries)
    return _OrderedLRU(max_entries)


def _run_coro(coro: Any) -> Any:
    """Run an async coroutine from sync code (redis.asyncio bridge)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # Already inside an event loop — run on a private loop in a worker thread.
    result: dict[str, Any] = {}
    error: list[BaseException] = []

    def _target() -> None:
        loop = asyncio.new_event_loop()
        try:
            result["value"] = loop.run_until_complete(coro)
        except BaseException as exc:  # noqa: BLE001 — re-raise in caller
            error.append(exc)
        finally:
            loop.close()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join()
    if error:
        raise error[0]
    return result.get("value")


class _RedisStore:
    """Thin sync facade over redis.asyncio JSON values + per-tool index sets."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis_async

        self._redis = redis_async.from_url(url, decode_responses=True)
        self._prefix = "nsa:toc:"
        self._idx = "nsa:toc:idx:"

    def _k(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def _ik(self, tool_id: str) -> str:
        return f"{self._idx}{tool_id}"

    async def _aget(self, key: str) -> dict[str, Any] | None:
        raw = await self._redis.get(self._k(key))
        if raw is None:
            return None
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None
        return payload

    async def _aput(self, tool_id: str, key: str, result: dict[str, Any], ttl_s: float) -> None:
        # Integer seconds via EX; sub-second via PX.
        body = json.dumps(result, separators=(",", ":"), ensure_ascii=False)
        pipe = self._redis.pipeline()
        if ttl_s < 1.0:
            pipe.set(self._k(key), body, px=max(1, int(ttl_s * 1000)))
        else:
            pipe.set(self._k(key), body, ex=max(1, int(ttl_s)))
        pipe.sadd(self._ik(tool_id), key)
        await pipe.execute()

    async def _ainvalidate(self, tool_id: str) -> int:
        idx = self._ik(tool_id)
        keys = await self._redis.smembers(idx)
        n = 0
        if keys:
            await self._redis.delete(*(self._k(k) for k in keys))
            n = len(keys)
        await self._redis.delete(idx)
        return n

    async def _asize(self) -> int:
        n = 0
        async for _ in self._redis.scan_iter(match=f"{self._prefix}*", count=200):
            n += 1
        return n

    async def _aclose(self) -> None:
        await self._redis.aclose()

    def get(self, key: str) -> dict[str, Any] | None:
        return _run_coro(self._aget(key))

    def put(self, tool_id: str, key: str, result: dict[str, Any], ttl_s: float) -> None:
        _run_coro(self._aput(tool_id, key, result, ttl_s))

    def invalidate(self, tool_id: str) -> int:
        return int(_run_coro(self._ainvalidate(tool_id)) or 0)

    def size(self) -> int:
        return int(_run_coro(self._asize()) or 0)

    def close(self) -> None:
        try:
            _run_coro(self._aclose())
        except Exception:
            pass


class ToolOutputCache:
    """Bounded tool-output cache (in-process LRU+TTL or redis.asyncio)."""

    def __init__(
        self,
        *,
        max_entries: int = _DEFAULT_MAX,
        ttl_s: float = _DEFAULT_TTL,
        neg_ttl_s: float = _DEFAULT_NEG_TTL,
        redis_url: str | None = _DEFAULT_REDIS,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        if ttl_s < 0:
            raise ValueError("ttl_s must be >= 0")
        if neg_ttl_s < 0:
            raise ValueError("neg_ttl_s must be >= 0")

        self.max_entries = int(max_entries)
        self.ttl_s = float(ttl_s)
        self.neg_ttl_s = float(neg_ttl_s)
        self.redis_url = (redis_url or "").strip() or None

        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._lock = threading.RLock()
        self._bridge: Any = None
        self._redis: _RedisStore | None = None
        self._store: Any = None
        self._by_tool: dict[str, set[str]] = {}
        self._tool_of: dict[str, str] = {}

        if self.redis_url:
            self._redis = _RedisStore(self.redis_url)
        else:
            self._store = _new_lru(self.max_entries)

        self._wire_metrics()

    def _wire_metrics(self) -> None:
        if _PlaneMetricBridge is None:
            return
        try:
            from neuroswarm_arm.metrics.lifecycle import peek_rmf

            rmf = peek_rmf()
            if rmf is not None:
                self._bridge = _PlaneMetricBridge(rmf)
        except Exception:
            self._bridge = None

    def _inc(self, kind: str) -> None:
        if kind == "hit":
            self._hits += 1
            name = _METRIC_HITS
        elif kind == "miss":
            self._misses += 1
            name = _METRIC_MISSES
        else:
            self._evictions += 1
            name = _METRIC_EVICTIONS
        if self._bridge is not None:
            try:
                self._bridge.publish_counter(name, 1.0)
            except Exception:
                pass

    def _resolve_ttl(self, result: dict[str, Any], ttl_s: float | None) -> float:
        if ttl_s is not None:
            return float(ttl_s)
        if _is_negative_result(result):
            return self.neg_ttl_s
        return self.ttl_s

    def get(self, tool_id: str, args: Any) -> dict[str, Any] | None:
        key = _make_key(tool_id, args)
        if self._redis is not None:
            value = self._redis.get(key)
            with self._lock:
                if value is None:
                    self._inc("miss")
                    return None
                self._inc("hit")
                return value

        with self._lock:
            assert self._store is not None
            try:
                # __getitem__ touches LRU order in cachetools; .get() does not.
                item = self._store[key]
            except KeyError:
                self._inc("miss")
                return None
            expires_at, result = item
            if expires_at < time.monotonic():
                self._drop_key(key)
                self._inc("miss")
                return None
            if hasattr(self._store, "move_to_end"):
                self._store.move_to_end(key)
            self._inc("hit")
            return dict(result)

    def put(
        self,
        tool_id: str,
        args: Any,
        result: dict[str, Any],
        *,
        ttl_s: float | None = None,
    ) -> None:
        if not isinstance(result, dict):
            raise TypeError("result must be a dict")
        key = _make_key(tool_id, args)
        ttl = self._resolve_ttl(result, ttl_s)

        if self._redis is not None:
            self._redis.put(tool_id, key, dict(result), ttl)
            return

        with self._lock:
            assert self._store is not None
            # Evict before insert so tool-index stays consistent (both backends).
            while key not in self._store and len(self._store) >= self.max_entries:
                try:
                    old_key, _old_val = self._store.popitem(last=False)
                except TypeError:
                    old_key, _old_val = self._store.popitem()
                self._forget_key(old_key)
                self._inc("eviction")
            expires_at = time.monotonic() + ttl
            self._store[key] = (expires_at, dict(result))
            self._tool_of[key] = tool_id
            self._by_tool.setdefault(tool_id, set()).add(key)

    def invalidate(self, tool_id: str) -> int:
        if self._redis is not None:
            n = self._redis.invalidate(tool_id)
            with self._lock:
                for _ in range(n):
                    self._inc("eviction")
            return n

        with self._lock:
            keys = list(self._by_tool.get(tool_id, ()))
            for key in keys:
                self._drop_key(key)
                self._inc("eviction")
            return len(keys)

    def _forget_key(self, key: str) -> None:
        tool_id = self._tool_of.pop(key, None)
        if tool_id is None:
            return
        bucket = self._by_tool.get(tool_id)
        if bucket is not None:
            bucket.discard(key)
            if not bucket:
                self._by_tool.pop(tool_id, None)

    def _drop_key(self, key: str) -> None:
        if self._store is not None:
            self._store.pop(key, None)
        self._forget_key(key)

    def stats(self) -> dict[str, int]:
        with self._lock:
            if self._redis is not None:
                size = self._redis.size()
            else:
                size = len(self._store) if self._store is not None else 0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "size": size,
            }

    def close(self) -> None:
        if self._redis is not None:
            self._redis.close()


if __name__ == "__main__":
    cache = ToolOutputCache(max_entries=100, ttl_s=0.4, neg_ttl_s=0.1)

    for i in range(3):
        cache.put(f"echo", {"n": i}, {"ok": True, "n": i})

    for i in range(3):
        got = cache.get("echo", {"n": i})
        assert got == {"ok": True, "n": i}, got

    warm = cache.stats()
    assert warm["hits"] == 3 and warm["misses"] == 0, warm
    print(f"warm: {warm['hits']} hits, {warm['misses']} misses, size={warm['size']}")

    mutated = cache.get("echo", {"n": 0, "x": 1})
    assert mutated is None

    time.sleep(0.5)
    expired = cache.get("echo", {"n": 0})
    assert expired is None

    final = cache.stats()
    print(f"final: {final}")
    print(f"expect path: 3 hits, 0 misses (warm), then miss after TTL; stats={final}")
