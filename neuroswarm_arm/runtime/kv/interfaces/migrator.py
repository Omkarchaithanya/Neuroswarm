"""IKVMigrator contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import StorageTier


class IKVMigrator(ABC):
    """Background migration controller."""

    @abstractmethod
    def enqueue(
        self,
        physical_id: str,
        target_tier: StorageTier,
        *,
        priority: int = 0,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def should_migrate(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def run_once(self) -> int:
        """Process pending migrations; returns count completed."""
        raise NotImplementedError
