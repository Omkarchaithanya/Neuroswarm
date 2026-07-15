"""Shared unavailable backend base for future HAL plugins."""

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

from ..execution.execution_context import ExecutionContext


class UnavailableBackend(InferenceBackend):
    """HAL-compliant stub: registers cleanly, health=UNAVAILABLE until wired."""

    def __init__(
        self,
        name: str,
        *,
        feature: str,
        tier: int = 0,
        device_classes: tuple[DeviceClass, ...] = (DeviceClass.CPU,),
        continuous_batching: bool = False,
        streaming: bool = False,
    ) -> None:
        self.name = name
        self.tier = tier
        self.feature = feature
        self.capabilities = BackendCapabilities(
            streaming=streaming,
            batching=False,
            continuous_batching=continuous_batching,
            prefill_decode_split=False,
            device_classes=device_classes,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(
            state=HealthState.UNHEALTHY,
            message=f"{self.feature} unavailable (adapter stub)",
            details={"feature": "UNAVAILABLE", "backend": self.name},
        )

    async def prefill(self, req: PrefillRequest, ctx: ExecutionContext) -> PrefillResult:
        raise RuntimeError(f"{self.feature} not wired")

    async def decode(
        self, req: DecodeRequest, ctx: ExecutionContext
    ) -> AsyncIterator[TokenChunk]:
        raise RuntimeError(f"{self.feature} not wired")
        yield  # pragma: no cover

    async def generate(
        self, req: GenerateRequest, ctx: ExecutionContext
    ) -> GenerateResult:
        raise RuntimeError(f"{self.feature} not wired")

    async def cancel(self, session_id: str) -> None:
        return None
