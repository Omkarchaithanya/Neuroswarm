"""Future CXL provider stub — architecture only, no implementation."""

from __future__ import annotations

from ..interfaces.provider import IKVProvider
from ..interfaces.types import StorageTier


class CXLProvider(IKVProvider):
    """Placeholder for future CXL 3.0 / emulated CXL backends.

    Do not instantiate for production traffic on Axion today.
    """

    @property
    def name(self) -> str:
        return "cxl"

    @property
    def tier(self) -> StorageTier:
        return StorageTier.FUTURE_CXL

    async def put(self, key: str, data: bytes) -> None:
        raise NotImplementedError("CXLProvider is a future backend stub; not available on Axion")

    async def get(self, key: str) -> bytes:
        raise NotImplementedError("CXLProvider is a future backend stub; not available on Axion")

    async def delete(self, key: str) -> None:
        raise NotImplementedError("CXLProvider is a future backend stub; not available on Axion")

    async def exists(self, key: str) -> bool:
        raise NotImplementedError("CXLProvider is a future backend stub; not available on Axion")

    def usage_bytes(self) -> int:
        return 0
