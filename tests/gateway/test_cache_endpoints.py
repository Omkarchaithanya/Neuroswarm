"""Cache debug endpoint shape + invalidate."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from neuroswarm_arm.runtime.dipa.speculative.tool_cache import ToolOutputCache


class _InvalidateBody(BaseModel):
    tool: str | None = None
    args: dict = Field(default_factory=dict)
    all: bool = False


@pytest.fixture
def cache_app() -> tuple[FastAPI, ToolOutputCache]:
    cache = ToolOutputCache(max_size=64, ttl_seconds=300)
    app = FastAPI()
    app.state.tool_cache = cache

    @app.get("/v1/tools/cache")
    async def tools_cache_status():
        snap = cache.snapshot()
        snap.setdefault("top_keys", [])
        return snap

    @app.post("/v1/tools/cache/invalidate")
    async def tools_cache_invalidate(body: _InvalidateBody):
        if body.all:
            n = await cache.invalidate(all_entries=True)
        else:
            n = await cache.invalidate(body.tool, body.args, all_entries=False)
        return {"invalidated": int(n)}

    return app, cache


@pytest.mark.asyncio
async def test_get_cache_shape(cache_app: tuple[FastAPI, ToolOutputCache]) -> None:
    app, cache = cache_app
    key = cache.make_key("echo", {"q": "hi"})
    await cache.set(key, '{"ok":true}')
    await cache.get(key)

    client = TestClient(app)
    res = client.get("/v1/tools/cache")
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) >= {"size", "hits", "misses", "hit_rate", "top_keys"}
    assert body["size"] == 1
    assert body["hits"] >= 1
    assert isinstance(body["top_keys"], list)
    assert key in body["top_keys"]


@pytest.mark.asyncio
async def test_invalidate_all_clears_cache(
    cache_app: tuple[FastAPI, ToolOutputCache],
) -> None:
    app, cache = cache_app
    await cache.set(cache.make_key("a", {"x": 1}), "1")
    await cache.set(cache.make_key("b", {"x": 2}), "2")
    assert cache.metrics()["size"] == 2

    client = TestClient(app)
    res = client.post("/v1/tools/cache/invalidate", json={"all": True})
    assert res.status_code == 200
    assert res.json() == {"invalidated": 2}
    assert cache.metrics()["size"] == 0


@pytest.mark.asyncio
async def test_invalidate_one_key(cache_app: tuple[FastAPI, ToolOutputCache]) -> None:
    app, cache = cache_app
    await cache.set(cache.make_key("echo", {"q": "a"}), "A")
    await cache.set(cache.make_key("echo", {"q": "b"}), "B")

    client = TestClient(app)
    res = client.post(
        "/v1/tools/cache/invalidate",
        json={"tool": "echo", "args": {"q": "a"}},
    )
    assert res.status_code == 200
    assert res.json()["invalidated"] == 1
    assert cache.metrics()["size"] == 1
