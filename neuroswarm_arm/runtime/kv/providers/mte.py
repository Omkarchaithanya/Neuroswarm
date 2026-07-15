"""Future MTE provider stub — architecture only, no implementation."""

from __future__ import annotations

from ..interfaces.provider import IKVProvider
from ..interfaces.types import StorageTier


class MTEProvider(IKVProvider):
    """Placeholder for future Memory Tagging Extension secured KV pages.

    Explicitly out of scope for the Axion production path.
    """

    @property
    def name(self) -> str:
        return "mte"

    @property
    def tier(self) -> StorageTier:
        return StorageTier.FUTURE_MTE

    async def put(self, key: str, data: bytes) -> None:
        raise NotImplementedError("MTEProvider is a future backend stub; MTE not implemented")

    async def get(self, key: str) -> bytes:
        raise NotImplementedError("MTEProvider is a future backend stub; MTE not implemented")

    async def delete(self, key: str) -> None:
        raise NotImplementedError("MTEProvider is a future backend stub; MTE not implemented")

    async def exists(self, key: str) -> bool:
        raise NotImplementedError("MTEProvider is a future backend stub; MTE not implemented")

    def usage_bytes(self) -> int:
        return 0
