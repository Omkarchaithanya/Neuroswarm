"""Future ARM MTE provider — interface only (unavailable on GCP Axion today)."""

from __future__ import annotations

from ..exceptions import KVProviderUnavailableError
from ..models import LocalityHint, ProviderStats
from ..provider import BaseKVProvider


class FutureMTEBackend(BaseKVProvider):
    """Placeholder for Memory Tagging Extension zero-copy sharing."""

    AVAILABLE = False

    @property
    def name(self) -> str:
        return "future_mte"

    def _raise(self) -> None:
        raise KVProviderUnavailableError(
            "ARM MTE not exposed in user-space on GCP Axion; use ram/mmap/redis/nvme"
        )

    async def allocate(self, kv_id: str, size: int, *, hint: LocalityHint | None = None) -> str:
        self._raise()
        return ""  # pragma: no cover

    async def store(self, kv_id: str, data: bytes) -> None:
        self._raise()

    async def load(self, kv_id: str) -> bytes:
        self._raise()
        return b""  # pragma: no cover

    async def delete(self, kv_id: str) -> None:
        self._raise()

    async def exists(self, kv_id: str) -> bool:
        return False

    async def stats(self) -> ProviderStats:
        return ProviderStats(name=self.name, available=False, extra={"reason": "mte_unavailable"})

    async def migrate(self, kv_id: str, target) -> str:  # type: ignore[no-untyped-def]
        self._raise()
        return ""  # pragma: no cover
