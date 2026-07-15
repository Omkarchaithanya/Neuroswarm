"""Server-Sent Events streaming transport."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

from ..interfaces.streamer import IStreamer
from ..interfaces.types import TokenChunk
from .token_stream import TokenStream


class SSEStreamer(IStreamer):
    """Buffer chunks and render them as ``text/event-stream`` frames."""

    name = "sse"

    def __init__(self, *, max_chunks: int = 256) -> None:
        self._stream = TokenStream(max_chunks=max_chunks)
        self._session_id = ""
        self._cancelled = False
        self._frames: list[str] = []

    def open(self, session_id: str, **kwargs: Any) -> None:
        self._session_id = session_id
        self._stream = TokenStream(session_id=session_id, max_chunks=self._stream.max_chunks)
        self._cancelled = False
        self._frames = []
        _ = kwargs

    def write(self, chunk: TokenChunk) -> None:
        if self._cancelled:
            return
        self._stream.push(chunk)
        payload = {
            "text": chunk.text,
            "index": chunk.index,
            "finished": chunk.finished,
            "session_id": self._session_id,
        }
        if chunk.token_id is not None:
            payload["token_id"] = chunk.token_id
        self._frames.append(f"data: {json.dumps(payload, separators=(',', ':'))}\n\n")
        if chunk.finished:
            self._frames.append("data: [DONE]\n\n")

    def close(self, *, error: str | None = None) -> None:
        if error:
            err = {"error": error, "session_id": self._session_id}
            self._frames.append(f"event: error\ndata: {json.dumps(err)}\n\n")
        self._stream.close(error=error)

    def cancel(self) -> None:
        self._cancelled = True
        self._stream.close(error="cancelled")

    def iter_sync(self) -> Iterator[TokenChunk]:
        yield from self._stream.read_all()

    async def iter_async(self) -> AsyncIterator[TokenChunk]:
        for chunk in self._stream.read_all():
            yield chunk

    def frames(self) -> list[str]:
        return list(self._frames)

    def render(self) -> str:
        return "".join(self._frames)
