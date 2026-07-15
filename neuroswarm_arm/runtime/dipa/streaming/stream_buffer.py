"""Stream buffer with high/low watermark backpressure."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field

from ..interfaces.types import TokenChunk


@dataclass
class StreamBuffer:
    """Bounded chunk queue; writers block when above the high watermark."""

    high_watermark: int = 200
    low_watermark: int = 50
    _queue: deque[TokenChunk] = field(default_factory=deque, init=False, repr=False)
    _closed: bool = field(default=False, init=False)
    _pressure: bool = field(default=False, init=False)
    _space: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
    _data: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.low_watermark > self.high_watermark:
            raise ValueError("low_watermark must be <= high_watermark")
        self._space.set()

    def __len__(self) -> int:
        return len(self._queue)

    @property
    def backpressured(self) -> bool:
        return self._pressure

    @property
    def closed(self) -> bool:
        return self._closed

    def write_nowait(self, chunk: TokenChunk) -> bool:
        """Enqueue without waiting. Returns ``False`` when high watermark hit."""
        if self._closed:
            raise RuntimeError("stream buffer is closed")
        if len(self._queue) >= self.high_watermark:
            self._pressure = True
            self._space.clear()
            return False
        self._queue.append(chunk)
        self._data.set()
        if len(self._queue) >= self.high_watermark:
            self._pressure = True
            self._space.clear()
        return True

    async def write(self, chunk: TokenChunk) -> None:
        """Enqueue *chunk*, waiting while backpressured above high watermark."""
        while True:
            if self.write_nowait(chunk):
                return
            await self._space.wait()

    def read_nowait(self) -> TokenChunk | None:
        if not self._queue:
            if self._closed:
                return None
            self._data.clear()
            return None
        chunk = self._queue.popleft()
        if len(self._queue) <= self.low_watermark:
            self._pressure = False
            self._space.set()
        if not self._queue:
            self._data.clear()
        return chunk

    async def read(self) -> TokenChunk | None:
        while True:
            chunk = self.read_nowait()
            if chunk is not None:
                return chunk
            if self._closed:
                return None
            await self._data.wait()

    def close(self) -> None:
        self._closed = True
        self._space.set()
        self._data.set()
