"""In-memory token stream buffer."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..interfaces.types import TokenChunk


@dataclass
class TokenStream:
    """Append-only buffer of :class:`TokenChunk` values for one session."""

    session_id: str = ""
    max_chunks: int = 256
    _chunks: deque[TokenChunk] = field(default_factory=deque, init=False, repr=False)
    _closed: bool = field(default=False, init=False)
    _error: str | None = field(default=None, init=False)
    _index: int = field(default=0, init=False)

    def __len__(self) -> int:
        return len(self._chunks)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def error(self) -> str | None:
        return self._error

    def write(self, text: str, *, finished: bool = False, token_id: int | None = None) -> TokenChunk:
        if self._closed:
            raise RuntimeError("token stream is closed")
        chunk = TokenChunk(
            text=text,
            token_id=token_id,
            index=self._index,
            finished=finished,
        )
        self._index += 1
        self._chunks.append(chunk)
        while len(self._chunks) > self.max_chunks:
            self._chunks.popleft()
        if finished:
            self._closed = True
        return chunk

    def push(self, chunk: TokenChunk) -> None:
        if self._closed:
            raise RuntimeError("token stream is closed")
        self._chunks.append(chunk)
        while len(self._chunks) > self.max_chunks:
            self._chunks.popleft()
        if chunk.finished:
            self._closed = True

    def read_all(self) -> list[TokenChunk]:
        return list(self._chunks)

    def text(self) -> str:
        return "".join(c.text for c in self._chunks)

    def close(self, *, error: str | None = None) -> None:
        self._error = error
        self._closed = True

    def clear(self) -> None:
        self._chunks.clear()
        self._index = 0
        self._closed = False
        self._error = None
