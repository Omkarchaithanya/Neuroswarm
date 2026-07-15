"""DIPA runtime kernel contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from .types import InferenceRequest, InferenceResponse


class IRuntime(ABC):
    """Public DIPA kernel surface used by HAOE / gateway."""

    @abstractmethod
    def infer(self, req: InferenceRequest) -> InferenceResponse:
        raise NotImplementedError

    @abstractmethod
    def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> Mapping[str, Any]:
        raise NotImplementedError
