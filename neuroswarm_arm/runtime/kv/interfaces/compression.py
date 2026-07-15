"""IKVCompression contract."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IKVCompression(ABC):
    """Pluggable block compression codec."""

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

    def ratio_hint(self, original_size: int, compressed_size: int) -> float:
        if compressed_size <= 0:
            return 0.0
        return float(original_size) / float(compressed_size)
