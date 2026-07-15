"""LiteRT inference backend stub."""

from __future__ import annotations

from collections.abc import AsyncIterator

from neuroswarm_arm.runtime.dipa.interfaces.backend import InferenceBackend
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    BackendCapabilities,
    DecodeRequest,
    DeviceClass,
    GenerateRequest,
    GenerateResult,
    HealthState,
    HealthStatus,
    PrefillRequest,
    PrefillResult,
    TokenChunk,
)

from ...execution.execution_context import ExecutionContext


class LiteRTBackend(InferenceBackend):
    """Placeholder LiteRT backend — not wired in this build."""

    def __init__(
        self,
        name: str = "litert",
        base_url: str = "",
        tier: int = 0,
    ) -> None:
        self.name = name
        self.base_url = base_url
        self.tier = tier
        self.capabilities = BackendCapabilities(
            streaming=False,
            batching=False,
            prefill_decode_split=False,
            device_classes=(DeviceClass.CPU, DeviceClass.NPU),
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(
            state=HealthState.UNHEALTHY,
            message="litert unavailable (not wired)",
            details={"feature": "UNAVAILABLE", "base_url": self.base_url},
        )

    async def prefill(self, req: PrefillRequest, ctx: ExecutionContext) -> PrefillResult:
        raise RuntimeError("litert not wired")

    async def decode(
        self, req: DecodeRequest, ctx: ExecutionContext
    ) -> AsyncIterator[TokenChunk]:
        raise RuntimeError("litert not wired")
        yield  # pragma: no cover — async generator marker

    async def generate(
        self, req: GenerateRequest, ctx: ExecutionContext
    ) -> GenerateResult:
        raise RuntimeError("litert not wired")

    async def cancel(self, session_id: str) -> None:
        return None
