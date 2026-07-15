"""MAKS / KV-cache connector — DIPA never owns KV storage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping


class IKVCacheConnector(ABC):
    """Port to Multi-Agent KV Sharing (Layer 5) / KV runtime."""

    @abstractmethod
    async def load(self, session_id: str, agent_id: str = "") -> str | None:
        """Return KV handle if present."""
        raise NotImplementedError

    @abstractmethod
    async def save(
        self,
        session_id: str,
        payload: bytes,
        *,
        agent_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def share(self, key: str, consumer_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def release(self, key: str, consumer_id: str = "") -> None:
        raise NotImplementedError

    def supports_prefix_reuse(self) -> bool:
        return True

    def supports_shared_kv(self) -> bool:
        return True

    def supports_paged_kv(self) -> bool:
        return False

    def supports_speculative_kv(self) -> bool:
        return False

    def supports_cross_session_reuse(self) -> bool:
        return True

    def supports_cross_model_reuse(self) -> bool:
        return False

    def capability_matrix(self) -> dict[str, dict[str, bool]]:
        return {}
