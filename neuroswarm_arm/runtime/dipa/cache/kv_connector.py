"""KV connector facade used by pipeline."""

from __future__ import annotations

from typing import Any, Mapping

from ..interfaces.kv_cache import IKVCacheConnector
from .maks_connector import MAKSConnector


class KVConnector:
    """Sync/async helpers over IKVCacheConnector."""

    def __init__(self, connector: IKVCacheConnector | None = None) -> None:
        self.connector: IKVCacheConnector = connector or MAKSConnector()

    async def load(self, session_id: str, agent_id: str = "") -> str | None:
        return await self.connector.load(session_id, agent_id)

    async def save(
        self,
        session_id: str,
        payload: bytes,
        *,
        agent_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        return await self.connector.save(
            session_id, payload, agent_id=agent_id, metadata=metadata
        )
