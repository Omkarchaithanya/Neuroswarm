"""Prefetch / warm API for AWPP integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable

from .models import KVHandle, PrefetchRequest

if TYPE_CHECKING:
    from .manager import KVManager


PrefetchHook = Callable[[PrefetchRequest], Awaitable[KVHandle | None]]


class PrefetchEngine:
    def __init__(self, manager: KVManager | None = None) -> None:
        self._manager = manager
        self._hooks: list[PrefetchHook] = []
        self.prefetch_count = 0

    def bind(self, manager: KVManager) -> None:
        self._manager = manager

    def add_hook(self, hook: PrefetchHook) -> None:
        self._hooks.append(hook)

    async def prefetch(self, req: PrefetchRequest) -> KVHandle | None:
        self.prefetch_count += 1
        for hook in self._hooks:
            handle = await hook(req)
            if handle is not None:
                return handle
        if self._manager is None:
            return None
        # Lookup existing by prompt/identity; warm + optional pin
        handle = await self._manager.lookup(
            kv_id=req.kv_id,
            prompt_hash=req.prompt_hash,
            identity=req.identity,
        )
        if handle is None:
            return None
        await self._manager.warm(handle.kv_id)
        if req.pin:
            await self._manager.pin(handle.kv_id)
        return handle
