"""Cascade engine contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .types import ExecutionPlan, GenerateResult, InferenceRequest

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
