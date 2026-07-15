"""IKVProvider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import StorageTier


class IKVProvider(ABC):
    """Storage backend for opaque KV block payloads."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def tier(self) -> StorageTier:
        raise NotImplementedError

    @abstractmethod
    async def put(self, key: str, data: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def usage_bytes(self) -> int:
        raise NotImplementedError

    def put_sync(self, key: str, data: bytes) -> None:
        import anyio

        anyio.run(self.put, key, data)

    def get_sync(self, key: str) -> bytes:
        import anyio

        return anyio.run(self.get, key)

    def delete_sync(self, key: str) -> None:
        import anyio

        anyio.run(self.delete, key)
