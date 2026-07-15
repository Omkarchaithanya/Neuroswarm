"""ChunkExecutor — run planned chunks through PrefillManager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from neuroswarm_arm.runtime.dipa.interfaces.pd import PromptChunk
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    KVTransferMode,
    PrefillRequest,
    PrefillResult,
)

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext

    from .prefill_manager import PrefillManager


class ChunkExecutor:
    def __init__(self, prefill_manager: PrefillManager) -> None:
        self.prefill_manager = prefill_manager

    async def run(
        self,
        chunks: Sequence[PromptChunk],
        *,
        ctx: ExecutionContext,
        session_id: str = "",
        quant: str = "",
        kv_handle: str | None = None,
        transfer_mode: KVTransferMode = KVTransferMode.RECOMPUTE,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> list[PrefillResult]:
        results: list[PrefillResult] = []
        for chunk in chunks:
            req = PrefillRequest(
                messages=chunk.messages,
                max_tokens=max_tokens,
                temperature=temperature,
                session_id=session_id,
                quant=quant,
                kv_handle=kv_handle,
                chunk_id=chunk.index,
                chunk_total=chunk.total,
                transfer_mode=transfer_mode,
            )
            results.append(await self.prefill_manager.prefill(req, ctx))
        return results
