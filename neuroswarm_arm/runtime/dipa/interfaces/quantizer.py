"""AQR quantization connector — DIPA asks, never owns policy tables."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from .types import InferenceRequest, WorkloadClass


class IQuantConnector(ABC):
    """Port to Adaptive Quantization Router (Layer 3)."""

    @abstractmethod
    def choose(
        self,
        req: InferenceRequest,
        workload: WorkloadClass,
        *,
        constraints: Mapping[str, Any] | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def available(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def is_supported(self, quant: str) -> bool:
        raise NotImplementedError
