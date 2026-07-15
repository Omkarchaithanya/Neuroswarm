"""Deterministic mock inference backend for tests and local dry-runs."""

from __future__ import annotations

from collections.abc import AsyncIterator

from neuroswarm_arm.runtime.dipa.interfaces.backend import InferenceBackend
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    BackendCapabilities,
    DecodeRequest,
    GenerateRequest,
    GenerateResult,
    HealthState,
    HealthStatus,
    PrefillRequest,
    PrefillResult,
    TokenChunk,
)

from ...execution.execution_context import ExecutionContext


class MockBackend(InferenceBackend):
    """Always-healthy backend that echoes the last user message."""

    def __init__(self, name: str = "mock", tier: int = 0) -> None:
        self.name = name
        self.tier = tier
        self.capabilities = BackendCapabilities(
            streaming=True,
            batching=True,
            continuous_batching=True,
            prefill_decode_split=True,
            prefix_caching=True,
            chunked_prefill=True,
            radix_attention=True,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(state=HealthState.HEALTHY, message="mock ready")

    async def prefill(self, req: PrefillRequest, ctx: ExecutionContext) -> PrefillResult:
        prompt = _last_user_content(req.messages)
        tokens = max(1, len(prompt.split()))
        hit = max(0, tokens // 3)
        return PrefillResult(
            prefix_tokens=tokens,
            kv_handle=req.kv_handle or f"mock-kv:{req.session_id or 'anon'}",
            latency_ms=0.5,
            backend=self.name,
            prefix_hit_tokens=hit,
            chunk_id=req.chunk_id,
            transfer_mode=req.transfer_mode,
            messages=list(req.messages),
        )

    async def decode(
        self, req: DecodeRequest, ctx: ExecutionContext
    ) -> AsyncIterator[TokenChunk]:
        text = f"mock-ok: {_last_user_content(req.messages)}"
        words = text.split()
        if not words:
            yield TokenChunk(text="", index=0, finished=True)
            return
        for i, word in enumerate(words):
            piece = word if i == 0 else f" {word}"
            yield TokenChunk(
                text=piece,
                index=i,
                finished=i == len(words) - 1,
            )

    async def generate(
        self, req: GenerateRequest, ctx: ExecutionContext
    ) -> GenerateResult:
        prompt = _last_user_content(req.messages)
        text = f"mock-ok: {prompt}"
        return GenerateResult(
            text=text,
            prompt_tokens=max(1, len(prompt.split())) if prompt else 0,
            completion_tokens=max(1, len(text.split())),
            latency_ms=0.0,
            ttft_ms=0.0,
            backend=self.name,
            quant=req.quant,
            tier_used=self.tier,
        )

    async def cancel(self, session_id: str) -> None:
        return None


def _last_user_content(messages: list[dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return str(msg.get("content", ""))
    if not messages:
        return ""
    return str(messages[-1].get("content", ""))
