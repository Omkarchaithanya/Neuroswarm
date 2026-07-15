"""AWPP warm-up connector — DIPA asks, never owns prediction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from .types import ExecutionPlan, InferenceRequest


class IWarmConnector(ABC):
    """Port to Agentic Workload Pre-warm Predictor (Layer 4)."""

    @abstractmethod
    async def ensure_warm(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan,
        *,
        hints: Mapping[str, Any] | None = None,
    ) -> bool:
        """Return True if model/session considered warm."""
        raise NotImplementedError

    @abstractmethod
    async def prefetch(self, model: str, session_id: str = "") -> None:
        raise NotImplementedError

    @abstractmethod
    def is_warm(self, model: str) -> bool:
        raise NotImplementedError
