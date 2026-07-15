"""IKVAllocator contract."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IKVAllocator(ABC):
    """NUMA-aware local memory allocator for hot KV payloads."""

    @property
    @abstractmethod
    def node_id(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def allocate(self, size: int) -> memoryview:
        raise NotImplementedError

    @abstractmethod
    def free(self, buf: memoryview) -> None:
        raise NotImplementedError

    @abstractmethod
    def available_bytes(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def used_bytes(self) -> int:
        raise NotImplementedError
