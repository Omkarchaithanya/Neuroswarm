"""Prefill / decode admission scheduler (DIPA-local, not HAOE)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from ..interfaces.types import PoolKind

T = TypeVar("T")


@dataclass
class PhaseScheduler:
    """Software prefill/decode worker pools for Axion CPU execution."""

    prefill_workers: int = 2
    decode_workers: int = 4
    _prefill: ThreadPoolExecutor | None = field(default=None, init=False, repr=False)
    _decode: ThreadPoolExecutor | None = field(default=None, init=False, repr=False)
    _started: bool = field(default=False, init=False)

    def start(self) -> None:
        if self._started:
            return
        self._prefill = ThreadPoolExecutor(
            max_workers=max(1, self.prefill_workers), thread_name_prefix="dipa-prefill"
        )
        self._decode = ThreadPoolExecutor(
            max_workers=max(1, self.decode_workers), thread_name_prefix="dipa-decode"
        )
        self._started = True

    def shutdown(self, wait: bool = True) -> None:
        if self._prefill is not None:
            self._prefill.shutdown(wait=wait, cancel_futures=True)
            self._prefill = None
        if self._decode is not None:
            self._decode.shutdown(wait=wait, cancel_futures=True)
            self._decode = None
        self._started = False

    def _pool(self, kind: PoolKind) -> ThreadPoolExecutor:
        if not self._started:
            self.start()
        assert self._prefill is not None and self._decode is not None
        if kind == PoolKind.PREFILL:
            return self._prefill
        return self._decode

    def submit_sync(self, kind: PoolKind, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        fut = self._pool(kind).submit(fn, *args, **kwargs)
        return fut.result()

    async def submit(
        self, kind: PoolKind, fn: Callable[..., T], *args: Any, **kwargs: Any
    ) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._pool(kind), lambda: fn(*args, **kwargs)
        )

    def status(self) -> dict[str, Any]:
        return {
            "started": self._started,
            "prefill_workers": self.prefill_workers,
            "decode_workers": self.decode_workers,
        }
