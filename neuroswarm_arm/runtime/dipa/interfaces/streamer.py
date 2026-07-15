"""Streaming transport contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from typing import Any

from .types import TokenChunk


class IStreamer(ABC):
    """Backend-independent token delivery adapter."""

    name: str

    @abstractmethod
    def open(self, session_id: str, **kwargs: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def write(self, chunk: TokenChunk) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self, *, error: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def cancel(self) -> None:
        raise NotImplementedError

    def iter_sync(self) -> Iterator[TokenChunk]:
        raise NotImplementedError

    async def iter_async(self) -> AsyncIterator[TokenChunk]:
        raise NotImplementedError
        yield  # pragma: no cover
