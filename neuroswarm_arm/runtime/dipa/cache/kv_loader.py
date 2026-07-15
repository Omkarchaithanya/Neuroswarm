"""KV load helper."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .kv_connector import KVConnector


class KVLoader:
    def __init__(self, connector: KVConnector) -> None:
        self.connector = connector

    async def load(self, session_id: str, agent_id: str = "") -> str | None:
        return await self.connector.load(session_id, agent_id)

    def load_sync(self, session_id: str, agent_id: str = "") -> str | None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.load(session_id, agent_id))
        # Already in async context — schedule carefully via new loop thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                lambda: asyncio.run(self.load(session_id, agent_id))
            ).result()
