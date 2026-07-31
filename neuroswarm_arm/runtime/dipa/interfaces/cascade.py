"""Cascade engine contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from .types import ExecutionPlan, GenerateResult, InferenceRequest, TokenChunk

if TYPE_CHECKING:
    from ..execution.execution_context import ExecutionContext


class ICascadeEngine(ABC):
    @abstractmethod
    async def run(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan,
        ctx: ExecutionContext,
    ) -> GenerateResult:
        raise NotImplementedError

    async def run_stream(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan,
        ctx: ExecutionContext,
    ) -> AsyncIterator[TokenChunk]:
        """Optional streaming speculative accept path. Default: empty."""
        if False:  # pragma: no cover — make this an async generator
            yield TokenChunk(text="", finished=True)
        return
        yield  # pragma: no cover
