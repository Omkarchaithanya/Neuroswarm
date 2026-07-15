"""InferenceBackend ABC — every runtime plugs here."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from .types import (
    BackendCapabilities,
    DecodeRequest,
    GenerateRequest,
    GenerateResult,
    HealthStatus,
    PrefillRequest,
    PrefillResult,
    TokenChunk,
)

if TYPE_CHECKING:
    from ..execution.execution_context import ExecutionContext


class InferenceBackend(ABC):
    """Hardware-agnostic inference backend contract."""

    name: str
    capabilities: BackendCapabilities

    @abstractmethod
    async def health(self) -> HealthStatus:
        raise NotImplementedError

    @abstractmethod
    async def prefill(self, req: PrefillRequest, ctx: ExecutionContext) -> PrefillResult:
        raise NotImplementedError

    @abstractmethod
    async def decode(
        self, req: DecodeRequest, ctx: ExecutionContext
    ) -> AsyncIterator[TokenChunk]:
        raise NotImplementedError
        yield  # pragma: no cover — make this an async generator ABC marker

    @abstractmethod
    async def generate(
        self, req: GenerateRequest, ctx: ExecutionContext
    ) -> GenerateResult:
        raise NotImplementedError

    @abstractmethod
    async def cancel(self, session_id: str) -> None:
        raise NotImplementedError

    def supports_phase_split(self) -> bool:
        return bool(self.capabilities.prefill_decode_split)
