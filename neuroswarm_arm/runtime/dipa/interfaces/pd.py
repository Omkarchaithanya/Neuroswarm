"""PD orchestration protocols — never import engine concretes above DIPA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

from .types import (
    DecodeRequest,
    GenerateResult,
    InferenceRequest,
    KVTransferMode,
    PrefillRequest,
    PrefillResult,
    TokenChunk,
)

if TYPE_CHECKING:
    from ..execution.execution_context import ExecutionContext


@dataclass(slots=True)
class PromptChunk:
    index: int
    total: int
    messages: list[dict[str, str]]
    approx_tokens: int = 0


@dataclass(slots=True)
class DecodeHandle:
    """Opaque handoff from prefill → decode (no engine internals)."""

    messages: list[dict[str, str]]
    transfer_mode: KVTransferMode = KVTransferMode.RECOMPUTE
    kv_handle: str | None = None
    bootstrap_room: str = ""
    radix_node_id: str = ""
    prefix_tokens: int = 0
    prefix_hit_tokens: int = 0
    recompute_tokens: int = 0
    token_ids: list[int] = field(default_factory=list)
    prefill_backend: str = ""
    decode_backend: str = ""
    session_id: str = ""
    quant: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class IPrefillRuntime(ABC):
    @abstractmethod
    async def prefill(
        self, req: PrefillRequest, ctx: ExecutionContext
    ) -> PrefillResult:
        raise NotImplementedError


class IDecodeRuntime(ABC):
    @abstractmethod
    async def decode(
        self, req: DecodeRequest, ctx: ExecutionContext
    ) -> AsyncIterator[TokenChunk]:
        raise NotImplementedError
        yield  # pragma: no cover

    @abstractmethod
    async def generate_from_handle(
        self,
        handle: DecodeHandle,
        *,
        max_tokens: int,
        temperature: float,
        ctx: ExecutionContext,
    ) -> GenerateResult:
        raise NotImplementedError


class IKVTransfer(ABC):
    @abstractmethod
    def resolve_mode(
        self,
        *,
        prefill_backend: str,
        decode_backend: str,
        requested: KVTransferMode | None = None,
    ) -> KVTransferMode:
        raise NotImplementedError

    @abstractmethod
    async def handoff(
        self,
        prefill: PrefillResult | Sequence[PrefillResult],
        *,
        messages: list[dict[str, str]],
        decode_backend: str,
        session_id: str = "",
        quant: str = "",
    ) -> DecodeHandle:
        raise NotImplementedError


class IPrefixCache(ABC):
    @abstractmethod
    def lookup(self, prefix_key: str) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def record_hit(self, prefix_key: str, hit_tokens: int, total_tokens: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def warm(
        self, prefix_text: str, *, backend: str = "", session_id: str = ""
    ) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> Mapping[str, Any]:
        raise NotImplementedError


class IChunkPlanner(ABC):
    @abstractmethod
    def plan(self, req: InferenceRequest, *, chunk_size: int) -> list[PromptChunk]:
        raise NotImplementedError
