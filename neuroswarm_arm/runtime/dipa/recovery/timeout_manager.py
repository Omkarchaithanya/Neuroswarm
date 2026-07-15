"""Default wall-clock timeouts for DIPA inference calls."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass
class TimeoutManager:
    """Apply a default timeout to awaitables."""

    default_timeout_s: float = 120.0

    def timeout_for(self, override_s: float | None = None) -> float:
        value = self.default_timeout_s if override_s is None else float(override_s)
        return max(0.0, value)

    async def run(
        self,
        awaitable: Awaitable[T],
        *,
        timeout_s: float | None = None,
    ) -> T:
        """Await *awaitable* under the configured timeout."""
        limit = self.timeout_for(timeout_s)
        if limit <= 0:
            return await awaitable
        return await asyncio.wait_for(awaitable, timeout=limit)

    def wrap(
        self,
        fn: Callable[..., Awaitable[T]],
        *,
        timeout_s: float | None = None,
    ) -> Callable[..., Awaitable[T]]:
        manager = self

        async def _wrapped(*args: object, **kwargs: object) -> T:
            return await manager.run(fn(*args, **kwargs), timeout_s=timeout_s)

        return _wrapped
