"""KV write helper."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .kv_connector import KVConnector


class KVWriter:
    def __init__(self, connector: KVConnector) -> None:
        self.connector = connector

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

    def save_sync(
        self,
        session_id: str,
        payload: bytes,
        *,
        agent_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.save(session_id, payload, agent_id=agent_id, metadata=metadata)
            )
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                lambda: asyncio.run(
                    self.save(
                        session_id, payload, agent_id=agent_id, metadata=metadata
                    )
                )
            ).result()
