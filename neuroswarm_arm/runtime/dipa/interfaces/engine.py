"""IInferenceEngine — ARMORA-stable inference contract (no backend leakage)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from typing import Any, Mapping


class IInferenceEngine(ABC):
    """Public inference surface for ARMORA / HAOE. Zero llama.cpp types."""

    @abstractmethod
    def load_model(self, model_ref: str, *, options: Mapping[str, Any] | None = None) -> str:
        """Load or attach model; return opaque handle id."""

    @abstractmethod
    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "cascade",
        max_tokens: int = 1024,
        temperature: float = 0.2,
        session_id: str = "",
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        """Blocking generate → dict with text/usage/metrics."""

    @abstractmethod
    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "cascade",
        max_tokens: int = 1024,
        temperature: float = 0.2,
        session_id: str = "",
        **kwargs: Any,
    ) -> Iterator[Mapping[str, Any]]:
        """Token stream as dict chunks."""

    @abstractmethod
    async def astream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "cascade",
        max_tokens: int = 1024,
        temperature: float = 0.2,
        session_id: str = "",
        **kwargs: Any,
    ) -> AsyncIterator[Mapping[str, Any]]:
        """Async token stream."""
        yield {}  # pragma: no cover

    @abstractmethod
    def warmup(self, *, model: str | None = None) -> Mapping[str, Any]:
        """Warm pools / backends; return status."""

    @abstractmethod
    def metrics(self) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> None:
        raise NotImplementedError
