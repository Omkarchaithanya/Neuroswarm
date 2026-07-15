"""IKVCheckpointStore contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IKVCheckpointStore(ABC):
    """Persist session metadata separately from tensor payloads."""

    @abstractmethod
    async def save_meta(self, session_id: str, meta: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def load_meta(self, session_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def save_payload(self, session_id: str, block_id: str, data: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    async def load_payload(self, session_id: str, block_id: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_sessions(self) -> list[str]:
        raise NotImplementedError
