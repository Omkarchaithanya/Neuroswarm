"""gRPC streaming transport stub."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from ..interfaces.streamer import IStreamer
from ..interfaces.types import TokenChunk
from .token_stream import TokenStream


class GRPCStreamer(IStreamer):
    """Stub gRPC adapter — buffers chunks; wire transport later."""

    name = "grpc"

    def __init__(self, *, max_chunks: int = 256) -> None:
        self._stream = TokenStream(max_chunks=max_chunks)
        self._session_id = ""
        self._cancelled = False
        self._opened = False

    def open(self, session_id: str, **kwargs: Any) -> None:
        self._session_id = session_id
        self._stream = TokenStream(session_id=session_id, max_chunks=self._stream.max_chunks)
        self._cancelled = False
        self._opened = True
        _ = kwargs

    def write(self, chunk: TokenChunk) -> None:
        if self._cancelled or not self._opened:
            return
        self._stream.push(chunk)

    def close(self, *, error: str | None = None) -> None:
        self._stream.close(error=error)
        self._opened = False

    def cancel(self) -> None:
        self._cancelled = True
        self.close(error="cancelled")

    def iter_sync(self) -> Iterator[TokenChunk]:
        yield from self._stream.read_all()

    async def iter_async(self) -> AsyncIterator[TokenChunk]:
        for chunk in self._stream.read_all():
            yield chunk
