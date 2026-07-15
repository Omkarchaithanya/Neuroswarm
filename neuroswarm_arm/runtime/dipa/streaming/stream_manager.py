"""Stream manager — open transports and publish completed generations."""

from __future__ import annotations

from typing import Any, Mapping

from ..interfaces.streamer import IStreamer
from ..interfaces.types import TokenChunk
from .chunk_scheduler import ChunkScheduler
from .grpc_stream import GRPCStreamer
from .sse_stream import SSEStreamer
from .stream_buffer import StreamBuffer
from .token_stream import TokenStream
from .websocket_stream import WebSocketStreamer


class StreamManager:
    """Registry of stream transports keyed by session / transport name."""

    def __init__(
        self,
        *,
        default_transport: str = "sse",
        buffer_max_chunks: int = 256,
        high_watermark: int = 200,
        low_watermark: int = 50,
        chunk_schedule_ms: float = 5.0,
    ) -> None:
        self.default_transport = default_transport
        self.buffer_max_chunks = buffer_max_chunks
        self.high_watermark = high_watermark
        self.low_watermark = low_watermark
        self.scheduler = ChunkScheduler(delay_ms=chunk_schedule_ms)
        self._sessions: dict[str, IStreamer] = {}
        self._completed: dict[str, str] = {}
        self._factories: dict[str, type[IStreamer]] = {
            "sse": SSEStreamer,
            "websocket": WebSocketStreamer,
            "ws": WebSocketStreamer,
            "grpc": GRPCStreamer,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> StreamManager:
        raw = dict(data or {})
        return cls(
            default_transport=str(raw.get("default_transport", "sse")),
            buffer_max_chunks=int(raw.get("buffer_max_chunks", 256)),
            high_watermark=int(raw.get("backpressure_high_watermark", 200)),
            low_watermark=int(raw.get("backpressure_low_watermark", 50)),
            chunk_schedule_ms=float(raw.get("chunk_schedule_ms", 5)),
        )

    def register_transport(self, name: str, factory: type[IStreamer]) -> None:
        self._factories[name.lower()] = factory

    def open(
        self,
        session_id: str,
        transport: str | None = None,
        **kwargs: Any,
    ) -> IStreamer:
        """Open (or replace) a transport for *session_id*."""
        name = (transport or self.default_transport).lower()
        factory = self._factories.get(name)
        if factory is None:
            raise KeyError(f"unknown stream transport: {name}")
        streamer = factory(max_chunks=self.buffer_max_chunks)  # type: ignore[call-arg]
        streamer.open(session_id, **kwargs)
        self._sessions[session_id] = streamer
        return streamer

    def get(self, session_id: str) -> IStreamer | None:
        return self._sessions.get(session_id)

    def close(self, session_id: str, *, error: str | None = None) -> None:
        streamer = self._sessions.pop(session_id, None)
        if streamer is not None:
            streamer.close(error=error)

    def publish_complete(self, session_id: str, text: str) -> None:
        """Publish a finished generation to the session transport (if any).

        Always records *text* for later retrieval. When a transport is open,
        writes a single finished :class:`TokenChunk` and closes the stream.
        """
        self._completed[session_id] = text
        streamer = self._sessions.get(session_id)
        if streamer is None:
            # Lazily open default transport so publish works without prior open().
            streamer = self.open(session_id)
        streamer.write(
            TokenChunk(text=text, index=0, finished=True)
        )
        streamer.close()

    def completed_text(self, session_id: str) -> str | None:
        return self._completed.get(session_id)

    def make_buffer(self) -> StreamBuffer:
        return StreamBuffer(
            high_watermark=self.high_watermark,
            low_watermark=self.low_watermark,
        )

    def make_token_stream(self, session_id: str = "") -> TokenStream:
        return TokenStream(session_id=session_id, max_chunks=self.buffer_max_chunks)
