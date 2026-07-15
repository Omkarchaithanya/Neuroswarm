"""IKVSharingBackend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IKVSharingBackend(ABC):
    """Cross-agent KV block sharing backend (MAKS replacement without MTE)."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def store(self, key: str, data: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    async def load(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def share(self, key: str, consumer_id: str) -> str:
        """Grant read access to consumer; returns share token."""
        raise NotImplementedError

    @abstractmethod
    async def release(self, key: str, consumer_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def reference_count(self, key: str) -> int:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        raise NotImplementedError
