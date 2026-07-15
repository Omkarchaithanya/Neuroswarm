"""StreamingEngine — normalize token chunks for ARMORA / SSE."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.interfaces.backend import InferenceBackend
from neuroswarm_arm.runtime.dipa.interfaces.types import DecodeRequest, TokenChunk
from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext


class StreamingEngine:
    """Bridge backend decode/generate into consistent chunk dicts."""

    def chunk_dict(self, chunk: TokenChunk, *, request_id: str = "") -> dict[str, Any]:
        return {
            "text": chunk.text,
            "index": chunk.index,
            "finished": chunk.finished,
            "request_id": request_id,
            "token_id": chunk.token_id,
            "metrics": dict(chunk.metrics),
        }

    async def astream_backend(
        self,
        backend: InferenceBackend,
        req: DecodeRequest,
        ctx: ExecutionContext,
        *,
        request_id: str = "",
    ) -> AsyncIterator[dict[str, Any]]:
        async for chunk in backend.decode(req, ctx):
            yield self.chunk_dict(chunk, request_id=request_id)

    def stream_sync(
        self,
        backend: InferenceBackend,
        req: DecodeRequest,
        ctx: ExecutionContext,
        *,
        request_id: str = "",
    ) -> Iterator[dict[str, Any]]:
        async def _collect() -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            async for c in self.astream_backend(
                backend, req, ctx, request_id=request_id
            ):
                out.append(c)
            return out

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            chunks = asyncio.run(_collect())
        else:
            # Nested loop: run in fresh loop via thread is caller's problem;
            # fall back to generate-then-split.
            from neuroswarm_arm.runtime.dipa.interfaces.types import GenerateRequest

            result = asyncio.get_event_loop().run_until_complete(  # type: ignore[attr-defined]
                backend.generate(
                    GenerateRequest(
                        messages=req.messages,
                        max_tokens=req.max_tokens,
                        temperature=req.temperature,
                        session_id=req.session_id,
                        quant=req.quant,
                    ),
                    ctx,
                )
            )
            text = result.text or ""
            if not text:
                yield {"text": "", "index": 0, "finished": True, "request_id": request_id}
                return
            words = text.split()
            for i, w in enumerate(words):
                piece = w if i == 0 else f" {w}"
                yield {
                    "text": piece,
                    "index": i,
                    "finished": i == len(words) - 1,
                    "request_id": request_id,
                }
            return
        for c in chunks:
            yield c

    def from_text(self, text: str, *, request_id: str = "") -> Iterator[Mapping[str, Any]]:
        words = (text or "").split()
        if not words:
            yield {"text": "", "index": 0, "finished": True, "request_id": request_id}
            return
        for i, w in enumerate(words):
            piece = w if i == 0 else f" {w}"
            yield {
                "text": piece,
                "index": i,
                "finished": i == len(words) - 1,
                "request_id": request_id,
            }
