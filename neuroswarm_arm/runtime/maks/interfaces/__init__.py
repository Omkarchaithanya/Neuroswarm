"""MAKS protocol / ABC surfaces (Memory OS interfaces package)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from ..models import (
    ARMORAPolicySnapshot,
    KVHandle,
    KVIdentity,
    KVRegistryRecord,
    LocalityHint,
    PrefetchRequest,
    ProviderStats,
)


class IKVProvider(ABC):
    """Storage backend abstraction — future MTE/CXL plug in here."""

    AVAILABLE: bool = True

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def allocate(self, kv_id: str, size: int, *, hint: LocalityHint | None = None) -> str:
        raise NotImplementedError

    @abstractmethod
    async def store(self, kv_id: str, data: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    async def load(self, kv_id: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def share(self, kv_id: str, consumer_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, kv_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def migrate(self, kv_id: str, target: "IKVProvider") -> str:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, kv_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def stats(self) -> ProviderStats:
        raise NotImplementedError

    @abstractmethod
    async def pin(self, kv_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def unpin(self, kv_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def warm(self, kv_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def cold(self, kv_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def flush(self) -> None:
        raise NotImplementedError


KVProvider = IKVProvider


class IRegistryStore(ABC):
    @abstractmethod
    async def put(self, record: KVRegistryRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get(self, kv_id: str) -> KVRegistryRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, kv_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_ids(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def find_by_dedup(self, dedup_key: str) -> KVRegistryRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def find_by_prefix(self, prompt_hash: str) -> list[KVRegistryRecord]:
        raise NotImplementedError


class IEvictionPolicy(ABC):
    @abstractmethod
    def select_victims(
        self,
        records: list[KVRegistryRecord],
        *,
        bytes_needed: int = 0,
        count: int = 1,
    ) -> list[str]:
        raise NotImplementedError


class IARMORAPolicy(ABC):
    """ARMORA policy port."""

    @abstractmethod
    def snapshot(self) -> ARMORAPolicySnapshot:
        raise NotImplementedError

    @abstractmethod
    def admit(self, size_bytes: int, priority: int = 0) -> bool:
        raise NotImplementedError


@runtime_checkable
class SupportsMAKSRuntime(Protocol):
    async def create(
        self,
        payload: bytes,
        *,
        agent_id: str = "",
        session_id: str = "",
        identity: KVIdentity | None = None,
        prompt_hash: str = "",
    ) -> KVHandle: ...

    async def lookup(
        self,
        *,
        kv_id: str = "",
        prompt_hash: str = "",
        identity: KVIdentity | None = None,
    ) -> KVHandle | None: ...

    async def share(self, kv_id: str, consumer_id: str) -> str: ...

    async def release(self, kv_id: str, agent_id: str = "") -> None: ...

    async def prefetch(self, req: PrefetchRequest) -> KVHandle | None: ...

    async def pin(self, kv_id: str) -> None: ...

    async def unpin(self, kv_id: str) -> None: ...

    async def warm(self, kv_id: str) -> None: ...


@runtime_checkable
class SupportsKVSharing(Protocol):
    async def store(self, key: str, data: bytes) -> None: ...

    async def load(self, key: str) -> bytes: ...

    async def share(self, key: str, consumer_id: str) -> str: ...

    async def release(self, key: str, consumer_id: str) -> None: ...


class ICompression(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def compress(self, data: bytes) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def decompress(self, data: bytes) -> bytes:
        raise NotImplementedError


class IHasher(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def hash(self, data: bytes) -> str:
        raise NotImplementedError

    @abstractmethod
    def hash_identity(
        self,
        identity: KVIdentity,
        *,
        prompt_prefix: bytes | str = b"",
    ) -> str:
        raise NotImplementedError


class IMigrationEngine(ABC):
    @abstractmethod
    async def migrate(self, kv_id: str, target: str, *, reason: str = "") -> str:
        raise NotImplementedError


class IAllocator(ABC):
    @abstractmethod
    async def allocate(self, kv_id: str, size: int, *, hint: LocalityHint | None = None) -> tuple:
        raise NotImplementedError


class ICacheLookup(ABC):
    @abstractmethod
    async def lookup(self, **kwargs) -> KVHandle | None:
        raise NotImplementedError


class ISecurityPolicy(ABC):
    @abstractmethod
    def authorize_share(self, kv_id: str, owner: str, consumer: str) -> bool:
        raise NotImplementedError


__all__ = [
    "IKVProvider",
    "KVProvider",
    "IRegistryStore",
    "IEvictionPolicy",
    "IARMORAPolicy",
    "SupportsMAKSRuntime",
    "SupportsKVSharing",
    "ICompression",
    "IHasher",
    "IMigrationEngine",
    "IAllocator",
    "ICacheLookup",
    "ISecurityPolicy",
]
