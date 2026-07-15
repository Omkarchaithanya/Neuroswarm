"""Redis backend — distributed metadata / sharing / cross-process lookup."""

from __future__ import annotations

from neuroswarm_arm.runtime.kv.providers.redis_provider import RedisProvider

from ..models import ProviderStats
from ._adapter import Plane2ProviderAdapter


class RedisBackend(Plane2ProviderAdapter):
    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        self._redis = RedisProvider(url, prefix="maks:kv:")
        super().__init__(self._redis, name="redis")
        self.url = url

    async def stats(self) -> ProviderStats:
        st = await super().stats()
        available = getattr(self._redis, "_available", True)
        st.available = bool(available)
        return st


def build_redis_backend(url: str) -> RedisBackend:
    return RedisBackend(url)
