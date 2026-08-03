"""Tests for ToolOutputCache (Speculative Tool Calling Layer 2)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from neuroswarm_arm.runtime.dipa.speculative.tool_cache import ToolOutputCache


@pytest.fixture
def cache() -> ToolOutputCache:
    return ToolOutputCache(max_size=4, ttl_seconds=60)


def test_canonical_key_sorted_json_unicode_nested() -> None:
    cache = ToolOutputCache()
    args_a = {"z": 1, "a": {"nested": "café", "b": 2}, "m": [3, 1]}
    args_b = {"m": [3, 1], "a": {"b": 2, "nested": "café"}, "z": 1}
    key_a = cache.make_key("search", args_a)
    key_b = cache.make_key("search", args_b)
    assert key_a == key_b
    assert len(key_a) == 32
    assert all(c in "0123456789abcdef" for c in key_a)

    # Different tool name → different key
    assert cache.make_key("other", args_a) != key_a

    # Key order independence for top-level only when values equal
    assert cache.make_key("t", {"x": 1, "y": 2}) == cache.make_key("t", {"y": 2, "x": 1})


@pytest.mark.asyncio
async def test_ttl_expiry_via_monkeypatch_time() -> None:
    cache = ToolOutputCache(max_size=8, ttl_seconds=10)
    key = cache.make_key("echo", {"n": 1})

    with patch(
        "neuroswarm_arm.runtime.dipa.speculative.tool_cache.time.time",
        return_value=1_000.0,
    ):
        await cache.set(key, '{"ok":true}')
        assert await cache.get(key) == '{"ok":true}'

    with patch(
        "neuroswarm_arm.runtime.dipa.speculative.tool_cache.time.time",
        return_value=1_011.0,
    ):
        assert await cache.get(key) is None

    m = cache.metrics()
    assert m["hits"] == 1
    assert m["misses"] == 1


@pytest.mark.asyncio
async def test_lru_eviction_at_max_size() -> None:
    cache = ToolOutputCache(max_size=2, ttl_seconds=300)
    k1 = cache.make_key("t", {"i": 1})
    k2 = cache.make_key("t", {"i": 2})
    k3 = cache.make_key("t", {"i": 3})

    await cache.set(k1, "v1")
    await cache.set(k2, "v2")
    # Touch k1 so k2 is LRU
    assert await cache.get(k1) == "v1"
    await cache.set(k3, "v3")

    assert await cache.get(k2) is None  # evicted
    assert await cache.get(k1) == "v1"
    assert await cache.get(k3) == "v3"
    assert cache.metrics()["size"] == 2


@pytest.mark.asyncio
async def test_concurrent_get_set() -> None:
    cache = ToolOutputCache(max_size=64, ttl_seconds=300)
    keys = [cache.make_key("op", {"i": i}) for i in range(20)]

    async def mixed(i: int) -> None:
        key = keys[i % len(keys)]
        if i % 2 == 0:
            await cache.set(key, f"v{i}")
        else:
            await cache.get(key)

    await asyncio.gather(*(mixed(i) for i in range(100)))
    m = cache.metrics()
    assert m["hits"] + m["misses"] == 50  # 50 gets
    assert 0 <= m["size"] <= 64
    assert 0.0 <= m["hit_rate"] <= 1.0


@pytest.mark.asyncio
async def test_hit_miss_counters() -> None:
    cache = ToolOutputCache(max_size=8, ttl_seconds=300)
    key = cache.make_key("calc", {"x": 42})

    assert await cache.get(key) is None
    await cache.set(key, "42")
    assert await cache.get(key) == "42"
    assert await cache.get(key) == "42"
    assert await cache.get("missing") is None

    m = cache.metrics()
    assert m["hits"] == 2
    assert m["misses"] == 2
    assert m["hit_rate"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_metrics_shape(cache: ToolOutputCache) -> None:
    await cache.set("k", "v")
    await cache.get("k")
    await cache.get("nope")
    m = cache.metrics()
    assert set(m.keys()) == {"hits", "misses", "size", "hit_rate"}
    assert isinstance(m["hits"], int)
    assert isinstance(m["misses"], int)
    assert isinstance(m["size"], int)
    assert isinstance(m["hit_rate"], float)
    assert m["hits"] == 1
    assert m["misses"] == 1
    assert m["size"] == 1
    assert m["hit_rate"] == pytest.approx(0.5)
