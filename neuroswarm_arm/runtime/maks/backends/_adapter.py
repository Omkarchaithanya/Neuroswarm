"""Adapter wrapping Plane-2 IKVProvider as MAKS KVProvider."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..exceptions import KVNotFoundError, KVProviderError
from ..models import LocalityHint, ProviderStats
from ..provider import BaseKVProvider

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.kv.interfaces.provider import IKVProvider as Plane2Provider


class Plane2ProviderAdapter(BaseKVProvider):
    """Thin adapter: MAKS API → Plane-2 put/get/delete/exists."""

    def __init__(self, inner: Plane2Provider, *, name: str | None = None) -> None:
        super().__init__()
        self._inner = inner
        self._name = name or inner.name
        self._latency_ema = 0.0

    @property
    def name(self) -> str:
        return self._name

    def _note_latency(self, ms: float) -> None:
        if self._latency_ema <= 0:
            self._latency_ema = ms
        else:
            self._latency_ema = 0.8 * self._latency_ema + 0.2 * ms

    async def store(self, kv_id: str, data: bytes) -> None:
        t0 = time.monotonic()
        try:
            await self._inner.put(kv_id, data)
        except Exception as exc:  # noqa: BLE001
            raise KVProviderError(str(exc)) from exc
        self._locations[kv_id] = f"{self.name}://{kv_id}"
        self._note_latency((time.monotonic() - t0) * 1000.0)

    async def load(self, kv_id: str) -> bytes:
        t0 = time.monotonic()
        try:
            data = await self._inner.get(kv_id)
        except KeyError as exc:
            raise KVNotFoundError(kv_id) from exc
        except Exception as exc:  # noqa: BLE001
            raise KVProviderError(str(exc)) from exc
        self._note_latency((time.monotonic() - t0) * 1000.0)
        return data

    async def delete(self, kv_id: str) -> None:
        try:
            await self._inner.delete(kv_id)
        except Exception as exc:  # noqa: BLE001
            raise KVProviderError(str(exc)) from exc
        self._locations.pop(kv_id, None)
        self._pinned.discard(kv_id)
        self._warm.discard(kv_id)
        self._cold.discard(kv_id)

    async def exists(self, kv_id: str) -> bool:
        return await self._inner.exists(kv_id)

    async def stats(self) -> ProviderStats:
        usage = 0
        try:
            usage = int(self._inner.usage_bytes())
        except Exception:
            usage = 0
        return ProviderStats(
            name=self.name,
            available=True,
            usage_bytes=usage,
            entry_count=len(self._locations),
            latency_ms_ema=self._latency_ema,
        )
